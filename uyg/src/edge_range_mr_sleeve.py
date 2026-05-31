#!/usr/bin/env python3
"""
edge_range_mr_sleeve.py — RANGE MEAN-REVERSION SLEEVE (regime-gated, uncorrelated)
═══════════════════════════════════════════════════════════════════════════════
CEPHE: range_mr_sleeve.

HİPOTEZ: Saf mean-reversion (her bar RSI/Bollinger counter-trend) kripto 4H'da
para kaybediyor (trend-dominant piyasa). AMA edge yalnız YATAY (range) rejimde
saklı olabilir: düşük ADX (trendsiz) + düşük volatilite percentile (volp) iken
fiyat bant kenarlarından ortalamaya döner. Bu cephede SADECE range rejiminde,
dar-stop / dar-hedef counter-trend işlem açıyoruz.

GATE (rejim filtresi, hepsi CAUSAL):
  adx(df)[0][i] < adx_max        (trendsiz)
  volp[i]       < volp_max       (düşük-vol rejim; ATR% 200-bar rolling percentile)

ENTRY (counter-trend, range içinde):
  mode="rsi2": RSI(2) < lo -> LONG ; RSI(2) > hi -> SHORT (side ile long-only seçilebilir)
  mode="bb":   low<=alt-bant & close içeri döndü -> LONG ; üst simetrik -> SHORT

EXIT: harness (SL=sl_atr*ATR, TP=tp_r*risk, flip, seri sonu). Dar stop/hedef.

ÖLÇÜM — DÜRÜST:
  1) havuz + tek 60/40 test split + per-coin + frekans.
  2) WALK-FORWARD OOS (folds=4): havuzu zamana göre sırala, son %60'ı 4 dilime böl,
     her dilim beklentisini ayrı raporla → zaman-stabil mi? ASIL METRİK BU.
     Model FIT EDİLMİYOR (saf kural) → overfit kaynağı yalnız SWEEP SELECTION;
     bu yüzden ailenin medyanı da raporlanır (cherry-pick kontrolü).
  3) KORELASYON: trend ensemble (donchian+supertrend) yönüyle korelasyon düşük mü?

KURAL: tek-split iyileşmeye GÜVENME. Sadece WF-OOS robust + zaman-stabil +
per-coin ≥%60 sayılır. Gerçek lift yoksa robust=False, dürüst not.
CAUSAL: pos[i] yalnız i ve öncesini kullanır; giriş i+1 açılışında (harness).

HIZ: tüm taban indikatörler (ADX, RSI2, volp, bollinger, ATR, trend-proxy) coin
başına BİR KEZ hesaplanır ve cache'lenir; sinyaller vektörel maske ile üretilir.
"""
import json, sys, warnings
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")
from signal_lab import (load_all, simulate, metrics, atr, adx, ema,
                        donchian, supertrend, BARS_PER_YEAR)

WARMUP = 200


def _flush(*a):
    print(*a); sys.stdout.flush()


# ── vektörel rolling percentile (ATR% 200-bar): x[i] kendi penceresinde percentile ──
def rolling_pctile(x, win=200):
    s = pd.Series(x)
    # her noktanın kendi geçmiş 200-pencere içindeki rank'i (<=). raw numpy, hızlı.
    def f(a):
        return (a[-1] >= a).mean()
    # numpy stride yerine pandas rolling+raw=True (lambda numpy üzerinde) — apply'dan ~10x hızlı
    return s.rolling(win).apply(f, raw=True).to_numpy()


def rsi_n(s, n):
    s = pd.Series(s); d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs = up/(dn+1e-12); return (100 - 100/(1+rs)).to_numpy()


# ── coin başına TABAN array cache (config'ten bağımsız) ──
def build_cache(dfs):
    cache = {}
    for c, df in dfs.items():
        cc = df["close"].to_numpy(float)
        a = atr(df, 14)
        ad = adx(df, 14)[0]
        atrp = a / (cc + 1e-9)
        volp = rolling_pctile(atrp, 200)
        r2 = rsi_n(cc, 2)
        bb = {}
        for n, k in [(20, 2.0), (20, 2.5)]:
            m = pd.Series(cc).rolling(n).mean().to_numpy()
            sd = pd.Series(cc).rolling(n).std().to_numpy()
            bb[(n, k)] = (m, m + k*sd, m - k*sd)
        # trend ensemble proxy yönü (korelasyon için)
        h40, l40 = donchian(df, 40); st = supertrend(df, 10, 3.0)
        tp = np.zeros(len(df))
        up_prev = np.roll(h40, 1); dn_prev = np.roll(l40, 1)
        long_brk = cc > up_prev; short_brk = cc < dn_prev
        tp[long_brk & (st == 1)] = 1; tp[short_brk & (st == -1)] = -1
        tp[:WARMUP] = 0
        cache[c] = {"close": cc, "high": df["high"].to_numpy(float),
                    "low": df["low"].to_numpy(float), "adx": ad, "volp": volp,
                    "rsi2": r2, "bb": bb, "trend_pos": tp, "n": len(df)}
    return cache


def regime(cd, adx_max, volp_max):
    m = (cd["adx"] < adx_max) & (cd["volp"] < volp_max)
    return np.where(np.isfinite(cd["adx"]) & np.isfinite(cd["volp"]), m, False)


# ── vektörel sinyal üreticileri (cache kullanır) ──
def sig_rsi2(cd, adx_max, volp_max, lo, hi, side="both"):
    m = regime(cd, adx_max, volp_max)
    r = cd["rsi2"]; pos = np.zeros(cd["n"])
    longs = m & (r < lo); shorts = m & (r > hi)
    pos[longs] = 1
    if side != "long":
        pos[shorts] = -1
    pos[:WARMUP] = 0
    return pos


def sig_bb(cd, adx_max, volp_max, n, k, side="both"):
    m = regime(cd, adx_max, volp_max)
    c = cd["close"]; hi_p = cd["high"]; lo_p = cd["low"]
    mid, up, lo = cd["bb"][(n, k)]
    up_p = np.roll(up, 1); lo_p_b = np.roll(lo, 1)
    hi_prev = np.roll(hi_p, 1); low_prev = np.roll(lo_p, 1)
    long_in = m & (low_prev <= lo_p_b) & (c > lo) & np.isfinite(lo)
    short_in = m & (hi_prev >= up_p) & (c < up) & np.isfinite(up)
    pos = np.zeros(cd["n"])
    pos[long_in] = 1
    if side != "long":
        pos[short_in] = -1
    pos[:WARMUP] = 0
    return pos


# ── WALK-FORWARD OOS: havuzu zamana göre 4 dilime böl ──
def wf_oos(trades, folds=4, oos_frac=0.6):
    if not trades:
        return {"oos_e": 0.0, "oos_n": 0, "fold_e": [], "fold_n": [],
                "stable": False, "pos_folds": 0, "wr": 0.0}
    tr = sorted(trades, key=lambda x: x["exit_ts"])
    n = len(tr); start = int(n*(1-oos_frac)); oos = tr[start:]
    b = np.linspace(0, len(oos), folds+1).astype(int)
    fold_e = []; fold_n = []
    for k in range(folds):
        seg = oos[b[k]:b[k+1]]
        if seg:
            rr = np.array([t["r_mult"] for t in seg])
            fold_e.append(float(rr.mean())); fold_n.append(len(seg))
        else:
            fold_e.append(0.0); fold_n.append(0)
    r_oos = np.array([t["r_mult"] for t in oos])
    pos_folds = sum(1 for e in fold_e if e > 0)
    return {"oos_e": float(r_oos.mean()), "oos_n": len(oos),
            "fold_e": [round(x, 3) for x in fold_e], "fold_n": fold_n,
            "stable": pos_folds >= folds-1, "pos_folds": pos_folds,
            "wr": float((r_oos > 0).mean()*100)}


def eval_cfg(cache, make_pos, sl_atr, tp_r):
    pool = []; per_coin = {}; span = 0
    for c, cd in cache.items():
        pos = make_pos(cd)
        # simulate harness'ı df ister; minimal df-benzeri sağlamak yerine gerçek df gerek.
        tr = simulate(DFS[c], pos, sl_atr=sl_atr, tp_r=tp_r)
        for t in tr:
            t["coin"] = c
        per_coin[c] = metrics(tr); pool += tr; span = max(span, cd["n"])
    m = metrics(pool)
    ps = sorted(pool, key=lambda x: x["exit_ts"]); split = int(len(ps)*0.6)
    te = metrics(ps[split:])
    pos_coins = sum(1 for cm in per_coin.values() if cm.get("avg_r", -9) > 0)
    wf = wf_oos(pool, 4, 0.6)
    freq = m["n"]/(span/BARS_PER_YEAR) if span else 0
    return {"pool": m, "test": te, "pos_coins": pos_coins, "tot": len(per_coin),
            "freq": freq, "wf": wf}


def sleeve_corr(cache, make_pos):
    cors = []
    for c, cd in cache.items():
        ps = make_pos(cd)[WARMUP:]; pt = cd["trend_pos"][WARMUP:]
        if ps.std() < 1e-9 or pt.std() < 1e-9:
            continue
        cors.append(float(np.corrcoef(ps, pt)[0, 1]))
    return float(np.mean(cors)) if cors else 0.0


DFS = None


def tight_probe(cache):
    """İKİNCİL PROBE: gate'i EN SIKI extreme'e it (ADX<12-14, volp<0.3-0.4, RSI2<5/>95).
    Soru: en saf range rejiminde edge BELİRİYOR mu, ZAMAN-STABİL mi?
    Bulgu (dürüst): pool beklentisi hâlâ ~negatif; WF-OOS ancak en sıkı (ADX<12,
    volp<0.3, lo5/hi95) köşesinde marjinal +'ya dönüyor AMA folds=[-,-,+,+] →
    pozitiflik yalnız son 2 dilimden (2024-25 toparlanma), zaman-stabil DEĞİL,
    N küçük (~282). Cherry-pick artefaktı; durable edge değil."""
    _flush("\n" + "-"*82)
    _flush("  İKİNCİL PROBE — EN SIKI range gate (overfit kontrolü):")
    best = None
    for adx_max in [12, 14]:
        for volp_max in [0.3, 0.4]:
            for lo, hi in [(10, 90), (5, 95)]:
                for sl, tp in [(1.0, 1.0), (1.5, 0.75), (1.5, 1.25)]:
                    mk = (lambda cd, a=adx_max, v=volp_max, lo=lo, hi=hi:
                          sig_rsi2(cd, a, v, lo, hi, "both"))
                    r = eval_cfg(cache, mk, sl, tp)
                    wf = r["wf"]
                    rec = dict(adx=adx_max, volp=volp_max, lo=lo, hi=hi, sl=sl, tp=tp,
                               n=r["pool"]["n"], poolE=round(r["pool"]["avg_r"], 3),
                               wf=round(wf["oos_e"], 3), folds=wf["fold_e"],
                               pos_folds=wf["pos_folds"], pc=r["pos_coins"])
                    if best is None or wf["oos_e"] > best["wf"]:
                        best = rec
    _flush(f"  en iyi tighter-gate: adx<{best['adx']} volp<{best['volp']} "
           f"lo{best['lo']}/hi{best['hi']} sl{best['sl']} tp{best['tp']}")
    _flush(f"    N={best['n']} poolE={best['poolE']:+.3f} WF-OOS={best['wf']:+.3f} "
           f"folds={best['folds']} pos_folds={best['pos_folds']}/4 pc={best['pc']}/20")
    stable = best["pos_folds"] >= 3 and best["poolE"] > 0
    _flush(f"    → durable/zaman-stabil mi? {'EVET' if stable else 'HAYIR (artefakt)'}")
    return best


def main():
    global DFS
    DFS = load_all("mktdata", "4h")
    _flush("="*82)
    _flush("  RANGE MEAN-REVERSION SLEEVE — regime-gated (ADX<x & volp<y) counter-trend")
    _flush("  baseline (mevcut trend meta-label v2 WF-OOS): +0.165R")
    _flush("="*82)
    _flush("  cache hazırlanıyor (taban indikatörler, coin başına 1 kez)...")
    cache = build_cache(DFS)
    _flush(f"  cache OK ({len(cache)} coin). sweep başlıyor.\n")

    configs = []
    # RSI(2) — both ve long-only; gate × eşik × dar stop/hedef
    for side in ["both", "long"]:
        for adx_max in [16, 18, 20]:
            for volp_max in [0.4, 0.5]:
                for lo, hi in [(10, 90), (5, 95), (15, 85)]:
                    for sl, tp in [(1.0, 1.0), (1.25, 1.25), (1.5, 1.0), (1.0, 1.5)]:
                        configs.append(dict(mode="rsi2", side=side, adx_max=adx_max,
                                            volp_max=volp_max, lo=lo, hi=hi, sl=sl, tp=tp))
    # Bollinger bounce
    for side in ["both", "long"]:
        for adx_max in [18, 20]:
            for volp_max in [0.5]:
                for n, k in [(20, 2.0), (20, 2.5)]:
                    for sl, tp in [(1.0, 1.0), (1.25, 1.5), (1.5, 1.0)]:
                        configs.append(dict(mode="bb", side=side, adx_max=adx_max,
                                            volp_max=volp_max, n=n, k=k, sl=sl, tp=tp))

    results = []
    for cfg in configs:
        if cfg["mode"] == "rsi2":
            mk = (lambda cd, cfg=cfg: sig_rsi2(cd, cfg["adx_max"], cfg["volp_max"],
                                               cfg["lo"], cfg["hi"], cfg["side"]))
            label = (f"rsi2[{cfg['side'][:1]}] adx<{cfg['adx_max']} volp<{cfg['volp_max']} "
                     f"lo{cfg['lo']}/hi{cfg['hi']} sl{cfg['sl']} tp{cfg['tp']}")
        else:
            mk = (lambda cd, cfg=cfg: sig_bb(cd, cfg["adx_max"], cfg["volp_max"],
                                             cfg["n"], cfg["k"], cfg["side"]))
            label = (f"bb[{cfg['side'][:1]}]   adx<{cfg['adx_max']} volp<{cfg['volp_max']} "
                     f"n{cfg['n']} k{cfg['k']} sl{cfg['sl']} tp{cfg['tp']}")
        r = eval_cfg(cache, mk, cfg["sl"], cfg["tp"])
        r["label"] = label; r["cfg"] = cfg; r["mk"] = mk
        results.append(r)
        wf = r["wf"]
        _flush(f"[{label}] N={r['pool']['n']:4d} f/yr={r['freq']:4.0f} "
               f"WR={r['pool']['wr']:4.1f}% poolE={r['pool']['avg_r']:+.3f} "
               f"| WF-OOS={wf['oos_e']:+.3f}(n{wf['oos_n']}) folds={wf['fold_e']} "
               f"pc={r['pos_coins']}/{r['tot']} {'STABLE' if wf['stable'] else '-'}")

    def is_robust(r):
        return (r["wf"]["oos_e"] > 0 and r["wf"]["stable"]
                and r["pos_coins"] >= 0.6*r["tot"] and r["pool"]["n"] >= 100)

    robusts = [r for r in results if is_robust(r)]
    pool = robusts if robusts else results
    best = max(pool, key=lambda r: (is_robust(r), r["wf"]["oos_e"], r["pos_coins"]))

    # cherry-pick kontrolü: tüm ailenin WF-OOS dağılımı
    all_wf = np.array([r["wf"]["oos_e"] for r in results])
    rob_all = [r for r in results if is_robust(r)]

    _flush("\n" + "="*82)
    _flush(f"  TARANAN config: {len(results)} | robust olan: {len(rob_all)} | "
           f"WF-OOS medyan: {np.median(all_wf):+.3f} | %75: {np.percentile(all_wf,75):+.3f}")
    _flush("  EN İYİ (WF-OOS odaklı):")
    wf = best["wf"]
    _flush(f"  {best['label']}")
    _flush(f"  pool: N={best['pool']['n']} WR={best['pool']['wr']:.1f}% "
           f"E={best['pool']['avg_r']:+.3f}R PF={best['pool']['pf']:.2f} freq/yr={best['freq']:.0f}")
    _flush(f"  WF-OOS: E={wf['oos_e']:+.3f}R (n={wf['oos_n']}) WR={wf['wr']:.1f}% "
           f"folds={wf['fold_e']} (n={wf['fold_n']}) pos_folds={wf['pos_folds']}/4")
    _flush(f"  per-coin+: {best['pos_coins']}/{best['tot']}  robust={is_robust(best)}")

    corr = sleeve_corr(cache, best["mk"])
    _flush(f"  trend-ensemble yön korelasyonu: {corr:+.3f} "
           f"({'düşük/uncorrelated' if abs(corr) < 0.3 else 'korele'})")

    tp_best = tight_probe(cache)

    out = {
        "label": best["label"], "meta": best["cfg"],
        "pool_n": int(best["pool"]["n"]), "pool_e": round(best["pool"]["avg_r"], 4),
        "pool_wr": round(best["pool"]["wr"], 1), "freq_yr": round(best["freq"], 1),
        "wf_oos_e": round(wf["oos_e"], 4), "wf_oos_n": int(wf["oos_n"]),
        "wf_folds": wf["fold_e"], "wf_pos_folds": int(wf["pos_folds"]),
        "wf_stable": bool(wf["stable"]), "pos_coins": int(best["pos_coins"]),
        "tot_coins": int(best["tot"]), "trend_corr": round(corr, 3),
        "n_configs": len(results), "n_robust": len(rob_all),
        "family_median_wf": round(float(np.median(all_wf)), 4),
        "robust": bool(is_robust(best)),
    }
    _flush("\nBEST_JSON:" + json.dumps(out))
    return out


if __name__ == "__main__":
    main()
