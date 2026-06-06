#!/usr/bin/env python3
"""
ensemble_build.py — Hayatta kalan 3 trend/breakout edge'ini birleştir.
donchian + vol_regime + supertrend × 20 coin → tek kronolojik trade akışı.
Çıktı: per-strateji + ensemble metrikleri, sabit-kesir equity/MDD, /tmp/ensemble_trades.json
"""
import json, numpy as np
import warnings; warnings.filterwarnings("ignore")
from signal_lab import load_all, simulate, metrics, BARS_PER_YEAR
import sig_donchian_breakout as D, sig_vol_regime_mom as V, sig_supertrend_regime as S

STRATS = [
    ("donchian",   D.make_sig(40, "atr", 0.25, 0.0),                                   2.0, 2.5),
    ("volregime",  V.make_sig(kind="atrp", w=100, mode="high_vol_trend", hi_thr=0.70, mom_n=10), 1.5, 2.0),
    ("supertrend", S.make_sig(10, 3, 25),                                              2.0, 3.0),
]

def fixed_frac_equity(trades, risk=0.02, start=100.0):
    eq = start; curve = [start]
    for t in trades:
        eq += eq * risk * t["r_mult"]
        if eq <= 1: eq = 0.0; curve.append(0); break
        curve.append(eq)
    a = np.array(curve); peak = np.maximum.accumulate(a); peak = np.where(peak == 0, 1, peak)
    mdd = float(abs(((a - peak)/peak).min())*100)
    return eq, mdd

def main():
    dfs = load_all("mktdata", "4h")
    span = max(len(df) for df in dfs.values())
    all_tr = []
    print("="*84); print("  ENSEMBLE — 3 hayatta kalan edge × 20 coin"); print("="*84)
    print(f"  {'strateji':12}{'N':>6}{'freq/yr':>8}{'WR%':>7}{'E(R)':>8}{'PF':>6}{'sumR':>9}")
    for name, sig, sl, tp in STRATS:
        st = []
        for c, df in dfs.items():
            tr = simulate(df, sig(df), sl_atr=sl, tp_r=tp)
            for t in tr: t["coin"] = c; t["strat"] = name
            st += tr
        m = metrics(st); fq = m["n"]/(span/BARS_PER_YEAR)
        print(f"  {name:12}{m['n']:>6}{fq:>8.0f}{m['wr']:>7.1f}{m['avg_r']:>+8.3f}{m['pf']:>6.2f}{m['sum_r']:>+9.1f}")
        all_tr += st
    all_tr.sort(key=lambda x: x["exit_ts"])
    m = metrics(all_tr); fq = m["n"]/(span/BARS_PER_YEAR)
    print("  " + "-"*82)
    print(f"  {'ENSEMBLE':12}{m['n']:>6}{fq:>8.0f}{m['wr']:>7.1f}{m['avg_r']:>+8.3f}{m['pf']:>6.2f}{m['sum_r']:>+9.1f}")
    # zaman-yarısı
    h = len(all_tr)//2; m1 = metrics(all_tr[:h]); m2 = metrics(all_tr[h:])
    print(f"  zaman: ilk½ E={m1['avg_r']:+.3f} (N{m1['n']})  son½ E={m2['avg_r']:+.3f} (N{m2['n']})")
    # sabit-kesir equity (risk %1/2/3)
    print(f"\n  Sabit-kesir compound (5.4y, tüm akış kronolojik):")
    for risk in [0.01, 0.02, 0.03, 0.05]:
        eq, mdd = fixed_frac_equity(all_tr, risk=risk)
        print(f"    risk %{risk*100:.0f}/işlem → bitiş ${eq:>12,.0f} ({eq/100:.0f}x)  MDD %{mdd:.1f}")
    json.dump([{"r_mult": t["r_mult"], "exit_ts": t["exit_ts"], "coin": t["coin"],
               "strat": t["strat"], "dir": t["dir"]} for t in all_tr],
              open("/tmp/ensemble_trades.json", "w"))
    print(f"\n  ✅ {len(all_tr)} trade → /tmp/ensemble_trades.json  (freq ~{fq:.0f}/yıl)")

if __name__ == "__main__":
    main()
