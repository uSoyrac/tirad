#!/usr/bin/env python3
"""
tv_isotropic.py — ISOTROPIC VOL-NORMALIZED MULTI-SCALE CONSENSUS (FILTER)
═══════════════════════════════════════════════════════════════════════
Hipotez: baseline donchian+supertrend GİRİŞ sinyalini, sadece çok-ölçekli
trend-açısı uzlaşısı (consensus) yeterince güçlü ve hizalı iken al.

sigma  = rolling realized vol (log-return std, 20-bar)
angle_N= atan( (log(close)-log(close[N])) / (sigma * N) )   for N in {7,19,47}
consensus = aynı işaretli ölçek sayısı (0..3)
mean_angle = ölçeklerin ortalama açısı (rad)

FİLTRE: baseline pos[i] (+1/-1) yalnız şu durumda korunur:
    consensus(işaret==sign(pos[i])) >= cons_min  VE  |mean_angle| >= ang_min
aksi halde pos[i]=0 (flat).

KURAL (leak-free): tüm feature shift(1) → i barında karar yalnız i-1 ve
öncesini kullanır (close[i] hariç; angle hesabı close serisini kullanır ama
filtre dizisi shift(1) ile bir bar geciktirilir). Giriş harness'ta i+1 açılışı.

ÖLÇÜM: baseline vs filtreli — N, MDD, Calmar, whipsaw(flip/trade), CAGR.
walk-forward OOS (ilk60/son40), per-coin, +1 bar gecikme leak testi,
permutation-null (consensus etiketini shuffle → edge kaybolmalı).
"""
import json, numpy as np, pandas as pd
import warnings; warnings.filterwarnings("ignore")
from signal_lab import load_all, simulate, metrics, BARS_PER_YEAR, atr
import sig_donchian_breakout as D, sig_supertrend_regime as S

# baseline ensemble bileşenleri (memory'deki doğrulanmış edge)
STRATS = [
    ("donchian",   D.make_sig(40, "atr", 0.25, 0.0), 2.0, 2.5),
    ("supertrend", S.make_sig(10, 3, 25),            2.0, 3.0),
]
SCALES = (7, 19, 47)
VOL_WIN = 20


# ── isotropic multi-scale consensus feature ──
def consensus_features(df, scales=SCALES, vol_win=VOL_WIN):
    """Returns (consensus_signed_count[+/-], mean_angle) — HER İKİSİ shift(1) ile
    leak-free. consensus_signed: pozitif=long uzlaşı sayısı, negatif=short uzlaşı."""
    c = df["close"].to_numpy(float)
    logc = np.log(c)
    lr = np.diff(logc, prepend=logc[0])
    sigma = pd.Series(lr).rolling(vol_win).std().to_numpy()
    sigma = np.where(sigma > 0, sigma, np.nan)
    n = len(c)
    angles = np.zeros((len(scales), n))
    for k, N in enumerate(scales):
        disp = logc - np.roll(logc, N)        # log(close)-log(close[N])
        disp[:N] = 0.0
        denom = sigma * N
        ang = np.arctan(disp / np.where(denom > 0, denom, np.nan))
        angles[k] = ang
    sign = np.sign(angles)                     # -1/0/+1 her ölçek
    # uzlaşı: aynı işaretli ölçek sayısı, baskın işaretle
    pos_cnt = (sign > 0).sum(axis=0)
    neg_cnt = (sign < 0).sum(axis=0)
    signed_consensus = np.where(pos_cnt >= neg_cnt, pos_cnt, -neg_cnt)
    mean_angle = np.nanmean(angles, axis=0)
    # SHIFT(1): kararı bir bar geciktir (kapalı bar)
    signed_consensus = pd.Series(signed_consensus).shift(1).to_numpy()
    mean_angle = pd.Series(mean_angle).shift(1).to_numpy()
    return signed_consensus, mean_angle


def apply_filter(df, pos, cons_min=2, ang_min=0.0, extra_lag=0, permute=False, seed=0):
    """pos (+1/-1/0) -> filtreli pos. extra_lag: leak testi için ek gecikme.
    permute: consensus/mean_angle çiftini shuffle (null)."""
    sc, ma = consensus_features(df)
    if extra_lag:
        sc = pd.Series(sc).shift(extra_lag).to_numpy()
        ma = pd.Series(ma).shift(extra_lag).to_numpy()
    if permute:
        rng = np.random.default_rng(seed)
        perm = rng.permutation(len(sc))
        sc = sc[perm]; ma = ma[perm]
    out = np.zeros(len(pos))
    for i in range(len(pos)):
        d = pos[i]
        if d == 0:
            continue
        s = sc[i]; a = ma[i]
        if not (np.isfinite(s) and np.isfinite(a)):
            continue
        # işaret hizalı VE consensus yeterli VE |açı| yeterli
        aligned_cnt = s if (s * d > 0) else 0   # d yönünde uzlaşı sayısı
        if abs(aligned_cnt) >= cons_min and abs(a) >= ang_min and a * d > 0:
            out[i] = d
    return out


# ── whipsaw: ardışık trade yön değişimi oranı ──
def whipsaw(trades):
    if len(trades) < 2:
        return 0.0
    dirs = [t["dir"] for t in sorted(trades, key=lambda x: x["entry_ts"])]
    flips = sum(1 for i in range(1, len(dirs)) if dirs[i] != dirs[i - 1])
    return flips / len(dirs)


# ── portföy compound (eşzamanlı-risk tavanlı, portfolio_sim ile aynı mantık) ──
def portfolio_run(trades, risk=0.02, max_concurrent=20, start=100.0):
    events = []
    for k, t in enumerate(trades):
        events.append((t["entry_ts"], "open", k))
        events.append((t["exit_ts"], "close", k))
    events.sort(key=lambda e: (e[0], 0 if e[1] == "close" else 1))
    eq = start; peak = start; mdd = 0.0; open_risk = {}
    for ts, typ, k in events:
        if typ == "open":
            if len(open_risk) >= max_concurrent:
                continue
            open_risk[k] = eq * risk
        else:
            if k in open_risk:
                eq += open_risk.pop(k) * trades[k]["r_mult"]
                if eq <= 1: eq = 0.0
                peak = max(peak, eq)
                if peak > 0: mdd = max(mdd, (peak - eq) / peak)
        if eq <= 0: break
    return eq, mdd * 100


def build_stream(filt=None, **fkw):
    """filt: None=baseline, ya da apply_filter argümanları (cons_min,ang_min,...)."""
    dfs = load_all("mktdata", "4h")
    tr = []
    span = 0
    for name, sig, sl, tp in STRATS:
        for c, df in dfs.items():
            span = max(span, len(df))
            pos = sig(df)
            if filt is not None:
                pos = apply_filter(df, pos, **fkw)
            for t in simulate(df, pos, sl_atr=sl, tp_r=tp):
                t["coin"] = c; t["strat"] = name; tr.append(t)
    tr.sort(key=lambda x: x["entry_ts"])
    return tr, span


def summarize(tr, span, label):
    m = metrics(tr)
    if m["n"] == 0:
        print(f"[{label}] N=0 (filtre her şeyi kapattı)")
        return {"label": label, "n": 0}
    eq, mdd = portfolio_run(tr)
    x = eq / 100; cagr = (x ** (1 / 5.4) - 1) * 100 if x > 0 else -100
    calmar = cagr / mdd if mdd > 0 else float("inf")
    ws = whipsaw(tr)
    # OOS
    tr_s = sorted(tr, key=lambda x: x["exit_ts"])
    sp = int(len(tr_s) * 0.6)
    tr_m = metrics(tr_s[:sp]); te_m = metrics(tr_s[sp:])
    # per-coin
    coins = sorted(set(t["coin"] for t in tr))
    pcpos = 0
    for c in coins:
        cm = metrics([t for t in tr if t["coin"] == c])
        if cm.get("avg_r", -9) > 0: pcpos += 1
    fq = m["n"] / (span / BARS_PER_YEAR)
    print(f"[{label}] N={m['n']} freq={fq:.0f} WR={m['wr']:.1f}% E={m['avg_r']:+.3f}R "
          f"PF={m['pf']:.2f} | MDD={mdd:.1f}% CAGR={cagr:.0f}% Calmar={calmar:.2f} "
          f"whipsaw={ws:.3f} | OOS tr={tr_m.get('avg_r',0):+.3f} te={te_m.get('avg_r',0):+.3f} "
          f"pc+={pcpos}/{len(coins)}")
    return {"label": label, "n": m["n"], "freq": fq, "wr": m["wr"], "avg_r": m["avg_r"],
            "pf": m["pf"], "mdd": mdd, "cagr": cagr, "calmar": calmar, "whipsaw": ws,
            "oos_train": tr_m.get("avg_r", 0), "oos_test": te_m.get("avg_r", 0),
            "pc_pos": pcpos, "pc_tot": len(coins)}


def main():
    print("=" * 100)
    print("  ISOTROPIC MULTI-SCALE CONSENSUS FİLTRESİ — baseline donchian+supertrend")
    print("  scales=7/19/47, vol=20bar realized, hepsi shift(1) leak-free")
    print("=" * 100)
    res = {}

    base_tr, span = build_stream(filt=None)
    res["baseline"] = summarize(base_tr, span, "BASELINE")

    print("\n-- consensus filtre varyantları (default param, in-sample sweep yok) --")
    # tek default varyant + birkaç eşik (overfit'ten kaçın: az nokta, mantıklı default)
    for cm, am, tag in [(2, 0.0, "cons>=2"),
                        (3, 0.0, "cons>=3 (tüm ölçek hizalı)"),
                        (2, 0.30, "cons>=2 & |ang|>=0.30"),
                        (3, 0.30, "cons>=3 & |ang|>=0.30")]:
        tr, sp = build_stream(filt=True, cons_min=cm, ang_min=am)
        res[tag] = summarize(tr, sp, tag)

    print("\n-- LEAK TESTİ (+1 bar ek gecikme, edge kaybolmamalı) --")
    tr, sp = build_stream(filt=True, cons_min=2, ang_min=0.0, extra_lag=1)
    res["lag+1"] = summarize(tr, sp, "cons>=2 lag+1")

    print("\n-- PERMUTATION NULL (consensus shuffle, edge çökmeli) --")
    nulls = []
    for s in range(5):
        tr, sp = build_stream(filt=True, cons_min=2, ang_min=0.0, permute=True, seed=s)
        m = metrics(tr)
        if m["n"]: nulls.append(m["avg_r"])
    if nulls:
        print(f"  null avg_r (5 shuffle): mean={np.mean(nulls):+.3f} "
              f"[{min(nulls):+.3f}..{max(nulls):+.3f}]  baseline E={res['baseline']['avg_r']:+.3f}")
        res["null_mean_avg_r"] = float(np.mean(nulls))

    json.dump(res, open("/tmp/tv_isotropic_res.json", "w"), indent=2)
    print("\n✅ /tmp/tv_isotropic_res.json")
    return res


if __name__ == "__main__":
    main()
