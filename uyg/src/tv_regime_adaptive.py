#!/usr/bin/env python3
"""
tv_regime_adaptive.py — REGIME-ADAPTIVE SUPERTREST (AlgoPoint)
═══════════════════════════════════════════════════════════════════════
4-yönlü karşılaştırma, AYNI 4H veri, leak-free, walk-forward OOS:
  A = sabit-çarpan donchian+supertrend baseline (portfolio_sim.STRATS)
  B = A + BTC-rejim-gate (binary): yeni giriş yalnız BTC trend-rejimi sağlıklıyken
  C = adaptif-çarpan supertrend (rejim skoruyla dinamik mult) + donchian(sabit)
  B+C = gate AÇIK iken adaptif-çarpan supertrend + donchian

HEDEF METRİK: Calmar (CAGR/MDD) ve whipsaw (flip/trade). CAGR'ı bozmadan
MDD↓ → Calmar↑ ve whipsaw↓ aranıyor.

Rejim skoru (0-1, hepsi causal shift(1)):
  regime = 0.30*adx_norm + 0.30*vol_ratio + 0.25*efficiency + 0.15*consistency
Adaptif ATR çarpanı:
  regime>=0.7 → 2.0..2.9 (dar); 0.4-0.7 → 2.9..4.1; <0.4 → 4.1..5.0 (geniş→az whipsaw)
"""
import json, numpy as np, pandas as pd
import warnings; warnings.filterwarnings("ignore")
from signal_lab import load_all, simulate, metrics, atr, adx, supertrend, BARS_PER_YEAR
from portfolio_sim import portfolio_run
import sig_donchian_breakout as D, sig_supertrend_regime as S

SPAN_Y = 5.4  # ~5.4 yıl (ADA 2021-01 → 2026-05)

# ──────────────────────────────────────────────────────────────────────
#  Rejim skoru — hepsi causal (i barına kadar), portfolio'da giriş i+1
# ──────────────────────────────────────────────────────────────────────
def kaufman_er(close, n=20):
    c = np.asarray(close, float)
    direction = np.abs(c - np.roll(c, n))
    diff = np.abs(np.diff(c, prepend=c[0]))
    volatility = pd.Series(diff).rolling(n).sum().to_numpy()
    er = direction / (volatility + 1e-12)
    er[:n] = np.nan
    return np.clip(er, 0, 1)

def regime_score(df, st_dir):
    """0-1 rejim skoru. st_dir = supertrend yönü (consistency için)."""
    c = df["close"].to_numpy(float)
    n = len(c)
    # adx_norm
    ax = adx(df, 14)[0]
    adx_norm = np.clip((ax - 15) / (35 - 15), 0, 1)
    # vol_ratio: ATR(10)/ATR(50) — normalize edilir (rolling median ile ölçek)
    a_s = atr(df, 10); a_l = atr(df, 50)
    raw = a_s / (a_l + 1e-12)            # ~1 civarı; >1 expansion
    vr_med = pd.Series(raw).rolling(100, min_periods=20).median().to_numpy()
    vol_ratio = np.clip((raw - vr_med) / (vr_med + 1e-12) + 0.5, 0, 1)
    # efficiency: Kaufman ER
    eff = kaufman_er(c, 20)
    # consistency: son 20 barda supertrend yönünde kapanan bar oranı
    up_close = (np.sign(np.diff(c, prepend=c[0])) == st_dir).astype(float)
    consistency = pd.Series(up_close).rolling(20).mean().to_numpy()
    reg = (0.30 * adx_norm + 0.30 * vol_ratio + 0.25 * eff + 0.15 * consistency)
    reg = np.nan_to_num(reg, nan=0.5)
    # CAUSAL: skoru 1 bar kaydır (i'de yalnız i-1'e kadarki bilgi)
    reg = np.roll(reg, 1); reg[0] = 0.5
    return reg

def adaptive_mult(reg):
    """regime>=0.7 → 2.0..2.9; 0.4-0.7 → 2.9..4.1; <0.4 → 4.1..5.0."""
    m = np.empty_like(reg)
    hi = reg >= 0.7
    mid = (reg >= 0.4) & (reg < 0.7)
    lo = reg < 0.4
    # yüksek rejim: dar (skor 0.7→1.0 ⇒ 2.9→2.0)
    m[hi] = 2.9 - (reg[hi] - 0.7) / (1.0 - 0.7) * (2.9 - 2.0)
    # orta: 0.4→0.7 ⇒ 4.1→2.9
    m[mid] = 4.1 - (reg[mid] - 0.4) / (0.7 - 0.4) * (4.1 - 2.9)
    # düşük: 0.0→0.4 ⇒ 5.0→4.1
    m[lo] = 5.0 - (reg[lo] - 0.0) / (0.4 - 0.0) * (5.0 - 4.1)
    return m

def supertrend_adaptive(df, period, mult_arr, adx_thr):
    """Per-bar değişken çarpanlı SuperTrend yönü + ADX rejim gate (S.make_sig mantığı)."""
    h = df["high"].to_numpy(float); l = df["low"].to_numpy(float); c = df["close"].to_numpy(float)
    a = atr(df, period); hl2 = (h + l) / 2
    up = hl2 - mult_arr * a; dn = hl2 + mult_arr * a
    dir_ = np.ones(len(c))
    for i in range(1, len(c)):
        up[i] = max(up[i], up[i-1]) if c[i-1] > up[i-1] else up[i]
        dn[i] = min(dn[i], dn[i-1]) if c[i-1] < dn[i-1] else dn[i]
        if c[i] > dn[i-1]: dir_[i] = 1
        elif c[i] < up[i-1]: dir_[i] = -1
        else: dir_[i] = dir_[i-1]
    return dir_

def make_sig_adaptive_supertrend(period=10, adx_thr=25):
    """Adaptif çarpanlı supertrend + ADX>=thr gate. C kolu."""
    def sig(df):
        n = len(df)
        # önce sabit-çarpan st_dir ile rejim skoru (consistency için)
        st0 = supertrend(df, period, 3.0)
        reg = regime_score(df, st0)
        mult_arr = adaptive_mult(reg)
        st = supertrend_adaptive(df, period, mult_arr, adx_thr)
        ax = adx(df, 14)[0]
        pos = np.zeros(n)
        for i in range(200, n):
            if not np.isfinite(ax[i]): continue
            if ax[i] >= adx_thr:
                pos[i] = st[i]
        return pos
    return sig

# ──────────────────────────────────────────────────────────────────────
#  BTC rejim gate (binary, causal) — B kolu
# ──────────────────────────────────────────────────────────────────────
def btc_regime_gate(dfs):
    """BTC trend-rejimi sağlıklı mı? Binary, causal. supertrend(BTC) yönü +1
    VE ADX(BTC)>=20 iken gate=AÇIK. Çıktı: ts->bool dict (giriş bu ts'de açılabilir)."""
    btc = dfs["BTC"]
    st = supertrend(btc, 10, 3.0)
    ax = adx(btc, 14)[0]
    gate = (st > 0) & (ax >= 20)
    gate = np.nan_to_num(gate.astype(float), nan=0.0).astype(bool)
    # CAUSAL: gate'i 1 bar kaydır (giriş i+1'de, karar i'de → i-1 bilgisi güvenli)
    gate = np.roll(gate, 1); gate[0] = False
    ts = [str(t) for t in btc.index]
    return dict(zip(ts, gate))

def apply_gate(trades, gate_map):
    """entry_ts BTC gate açık olan trade'leri tut. BTC ts ızgarasına en yakın <= eşle."""
    btc_ts = sorted(gate_map.keys())
    btc_arr = np.array([pd.Timestamp(t).value for t in btc_ts])
    keep = []
    for t in trades:
        ev = pd.Timestamp(t["entry_ts"]).value
        idx = np.searchsorted(btc_arr, ev, side="right") - 1
        if idx >= 0 and gate_map[btc_ts[idx]]:
            keep.append(t)
    return keep

# ──────────────────────────────────────────────────────────────────────
#  Stream üretimi
# ──────────────────────────────────────────────────────────────────────
DONCH = D.make_sig(40, "atr", 0.25, 0.0)
SUPER_FIXED = S.make_sig(10, 3, 25)
SUPER_ADAPT = make_sig_adaptive_supertrend(10, 25)

def build_stream(dfs, supertrend_sig):
    """donchian(sabit) + supertrend(verilen sinyal). portfolio_sim.build_stream ile aynı yapı."""
    tr = []
    strats = [("donchian", DONCH, 2.0, 2.5), ("supertrend", supertrend_sig, 2.0, 3.0)]
    for name, sig, sl, tp in strats:
        for c, df in dfs.items():
            for t in simulate(df, sig(df), sl_atr=sl, tp_r=tp):
                t["coin"] = c; t["strat"] = name; tr.append(t)
    tr.sort(key=lambda x: x["entry_ts"])
    return tr

def whipsaw_per_coin(dfs, supertrend_sig):
    """Whipsaw = sinyal flip (yön değişimi) sayısı / trade sayısı. Düşük = iyi.
    Hem donchian hem supertrend kolu için toplam flip / toplam trade."""
    total_flips = 0; total_trades = 0
    for name, sig in [("donchian", DONCH), ("supertrend", supertrend_sig)]:
        for c, df in dfs.items():
            p = sig(df)
            nz = p[p != 0]
            flips = int(np.sum(nz[1:] != nz[:-1])) if len(nz) > 1 else 0
            tr = simulate(df, p, sl_atr=2.0, tp_r=(2.5 if name == "donchian" else 3.0))
            total_flips += flips; total_trades += len(tr)
    return total_flips, total_trades

# ──────────────────────────────────────────────────────────────────────
def eval_arm(label, trades, dfs):
    m = metrics(trades)
    fq = m["n"] / (max(len(d) for d in dfs.values()) / BARS_PER_YEAR)
    out = {"label": label, "n": m["n"], "wr": m["wr"], "avg_r": m["avg_r"],
           "pf": m["pf"], "freq_yr": fq}
    # walk-forward OOS: ilk %60 train / son %40 test (exit_ts'e göre sıralı)
    srt = sorted(trades, key=lambda x: x["exit_ts"])
    split = int(len(srt) * 0.6)
    out["train_avgr"] = metrics(srt[:split]).get("avg_r", 0)
    out["test_avgr"] = metrics(srt[split:]).get("avg_r", 0)
    # portföy MDD/CAGR/Calmar — birkaç sizing
    rows = []
    for risk in [0.01, 0.02]:
        for mc in [10, 20]:
            eq, mdd, _ = portfolio_run(trades, risk=risk, max_concurrent=mc)
            x = eq / 100; cagr = (x ** (1 / SPAN_Y) - 1) * 100 if x > 0 else -100
            calmar = cagr / mdd if mdd > 0 else float("inf")
            rows.append({"risk": risk, "mc": mc, "end$": eq, "mult": x,
                         "mdd": mdd, "cagr": cagr, "calmar": calmar})
    out["portfolio"] = rows
    return out

def fmt(o):
    s = (f"  [{o['label']:8s}] N={o['n']:5d} freq/yr={o['freq_yr']:6.1f} WR={o['wr']:5.1f}% "
         f"E={o['avg_r']:+.3f}R PF={o['pf']:.2f} | OOS train={o['train_avgr']:+.3f} "
         f"test={o['test_avgr']:+.3f}\n")
    for r in o["portfolio"]:
        s += (f"        risk{r['risk']*100:.0f}% mc{r['mc']:<2d} end=${r['end$']:>12,.0f} "
              f"({r['mult']:>7.1f}x) MDD={r['mdd']:5.1f}% CAGR={r['cagr']:6.1f}% "
              f"Calmar={r['calmar']:.3f}\n")
    return s

def main():
    dfs = load_all("mktdata", "4h")
    print("=" * 90)
    print("  REGIME-ADAPTIVE SUPERTREND — 4-yönlü (A / B / C / B+C), aynı 4H veri, leak-free")
    print(f"  coins={len(dfs)} span~{SPAN_Y}y  cost~7bps/taraf  HEDEF: Calmar↑ + whipsaw↓ (CAGR korunarak)")
    print("=" * 90)

    gate_map = btc_regime_gate(dfs)
    gate_open_frac = np.mean(list(gate_map.values()))
    print(f"  BTC-gate açık bar oranı: {gate_open_frac*100:.1f}%\n")

    # streams
    stream_fixed = build_stream(dfs, SUPER_FIXED)   # A baz akış
    stream_adapt = build_stream(dfs, SUPER_ADAPT)   # C baz akış

    A = eval_arm("A", stream_fixed, dfs)
    B = eval_arm("B", apply_gate(stream_fixed, gate_map), dfs)
    C = eval_arm("C", stream_adapt, dfs)
    BC = eval_arm("B+C", apply_gate(stream_adapt, gate_map), dfs)

    for o in (A, B, C, BC):
        print(fmt(o))

    # whipsaw
    print("  WHIPSAW (flip/trade, düşük=iyi):")
    wf_fixed = whipsaw_per_coin(dfs, SUPER_FIXED)
    wf_adapt = whipsaw_per_coin(dfs, SUPER_ADAPT)
    print(f"    A/B (sabit-çarpan supertrend+donchian): flips={wf_fixed[0]} trades={wf_fixed[1]} "
          f"ratio={wf_fixed[0]/max(wf_fixed[1],1):.3f}")
    print(f"    C/B+C (adaptif-çarpan supertrend+donchian): flips={wf_adapt[0]} trades={wf_adapt[1]} "
          f"ratio={wf_adapt[0]/max(wf_adapt[1],1):.3f}")

    # özet karşılaştırma: risk2%/mc20 satırı (en agresif compound)
    def pick(o):
        return [r for r in o["portfolio"] if r["risk"] == 0.02 and r["mc"] == 20][0]
    print("\n  ÖZET (risk2% mc20):")
    print(f"    {'arm':5s}{'MDD%':>8}{'CAGR%':>9}{'Calmar':>9}{'E[R]':>8}{'N':>7}")
    for o in (A, B, C, BC):
        r = pick(o)
        print(f"    {o['label']:5s}{r['mdd']:>8.1f}{r['cagr']:>9.1f}{r['calmar']:>9.3f}"
              f"{o['avg_r']:>8.3f}{o['n']:>7d}")

    json.dump({"A": A, "B": B, "C": C, "BC": BC,
               "whipsaw_fixed": wf_fixed, "whipsaw_adapt": wf_adapt,
               "gate_open_frac": float(gate_open_frac)},
              open("/tmp/tv_regime_adaptive.json", "w"), indent=2)
    print("\n  ✅ /tmp/tv_regime_adaptive.json")

if __name__ == "__main__":
    main()
