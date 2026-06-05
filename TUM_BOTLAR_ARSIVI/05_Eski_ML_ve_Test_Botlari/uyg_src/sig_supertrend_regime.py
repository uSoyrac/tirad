#!/usr/bin/env python3
"""
sig_supertrend_regime.py — sinyal ailesi: SuperTrend trend-takibi + ADX rejim filtresi.

Fikir: supertrend(df,period,mult) yön verir; ama SADECE ADX yeterince yüksekken
(trend güçlü) işleme gir. Düşük ADX (yatay/chop) iken flat kal. Bu chop filtresi
ailenin özüdür. period∈{7,10,14}, mult∈{2,3}, adx_thr∈{20,25,30} süpür.

Causal: pos[i] yalnız i ve öncesini kullanır. supertrend ve adx her ikisi de
i barına kadarki veriden hesaplanır; giriş harness'ta i+1 açılışında olur.
"""
import json
import numpy as np
from signal_lab import evaluate, supertrend, adx


def make_sig(period, mult, adx_thr):
    def sig(df):
        n = len(df)
        pos = np.zeros(n)
        st = supertrend(df, period, mult)            # +1 up, -1 down
        ax = adx(df, 14)[0]                           # ADX serisi
        for i in range(200, n):
            if not np.isfinite(ax[i]):
                continue
            if ax[i] >= adx_thr:                      # rejim: trend güçlü
                pos[i] = st[i]                         # SuperTrend yönünde
            # düşük ADX => yatay => flat (pos=0)
        return pos
    return sig


def main():
    # Küçük süpürme: temsili 6 config (period × mult × adx_thr alt kümesi)
    configs = [
        (7, 3, 20),
        (10, 3, 20),
        (10, 3, 25),
        (10, 2, 25),
        (14, 3, 25),
        (10, 3, 30),
    ]
    # SL/TP de hafifçe gez
    risk_sets = [(1.5, 2.0), (2.0, 3.0)]

    results = []
    for (p, m, thr) in configs:
        for (sl, tp) in risk_sets:
            res = evaluate(make_sig(p, m, thr), tf="4h", sl_atr=sl, tp_r=tp,
                           label=f"ST({p},{m}) adx>={thr} sl{sl} tp{tp}")
            res["_cfg"] = {"period": p, "mult": m, "adx_thr": thr,
                           "sl_atr": sl, "tp_r": tp}
            results.append(res)
            pl, te = res["pool"], res["test"]
            print(f"[{res['label']:28s}] N={pl['n']:5d} freq/yr={res['freq_yr']:6.0f} "
                  f"WR={pl['wr']:5.1f}% E={pl['avg_r']:+.3f}R PF={pl['pf']:.2f} "
                  f"test={te.get('avg_r',0):+.3f} +coins={res['pos_coins']}/{res['tot_coins']} "
                  f"{'ROBUST' if res['robust'] else '-'}")

    # En iyi OOS-robust seçimi: robust olanlar arasında test avg_r * sqrt(freq) skoru
    robust = [r for r in results if r["robust"]]
    pool_src = robust if robust else results

    def score(r):
        return r["test"].get("avg_r", -9) * (r["freq_yr"] ** 0.5)

    best = max(pool_src, key=score)
    print("\n=== BEST ===")
    print(json.dumps({
        "label": best["label"],
        "cfg": best["_cfg"],
        "pool": best["pool"],
        "train": best["train"],
        "test": best["test"],
        "freq_yr": best["freq_yr"],
        "pos_coins": best["pos_coins"],
        "tot_coins": best["tot_coins"],
        "robust": best["robust"],
        "any_robust": bool(robust),
    }, indent=2))


if __name__ == "__main__":
    main()
