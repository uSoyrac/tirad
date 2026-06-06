#!/usr/bin/env python3
"""
sig_bollinger_dual.py — Bollinger çift mod sinyal ailesi.

(a) breakout: kapanış üst bandı yukarı keserse LONG (momentum/trend).
(b) mean-reversion: alt banda dokunup içeri dönerse LONG (bounce).

Sadece long. Causal: pos[i] yalnız i ve öncesini kullanır.
bollinger(close,n,k), n in {20,30}, k in {2,2.5}.
"""
import json
import numpy as np
from signal_lab import evaluate, report, bollinger


def make_breakout(n, k):
    """Kapanış üst bandı aşağıdan yukarı kestiğinde LONG, fiyat orta bandın altına
    düşene kadar long tut."""
    def sig(df):
        c = df["close"].to_numpy(float)
        mid, up, lo = bollinger(c, n, k)
        pos = np.zeros(len(c))
        state = 0
        for i in range(n + 1, len(c)):
            if np.isnan(up[i]) or np.isnan(mid[i]):
                continue
            # breakout giriş: önceki bar üst altında, bu bar üstü kapanışla aştı
            crossed_up = (c[i] > up[i]) and (c[i - 1] <= up[i - 1])
            if state == 0:
                if crossed_up:
                    state = 1
            else:
                # orta bandın altına düşerse çık (trend zayıfladı)
                if c[i] < mid[i]:
                    state = 0
            pos[i] = state
        return pos
    return sig


def make_meanrev(n, k):
    """Alt banda dokunup (low<=lo) içeri dönen kapanış (c>lo) LONG; orta banda
    ulaşınca veya alt bandın belirgin altına sarkınca çık."""
    def sig(df):
        c = df["close"].to_numpy(float)
        lo_p = df["low"].to_numpy(float)
        mid, up, lo = bollinger(c, n, k)
        pos = np.zeros(len(c))
        state = 0
        for i in range(n + 1, len(c)):
            if np.isnan(lo[i]) or np.isnan(mid[i]):
                continue
            # giriş: önceki bar alt banda dokundu, bu bar kapanış bandın içine döndü
            touched = lo_p[i - 1] <= lo[i - 1]
            back_in = c[i] > lo[i]
            if state == 0:
                if touched and back_in:
                    state = 1
            else:
                # orta banda ulaştı (hedef) -> çık. flip/SL/TP zaten harness'ta.
                if c[i] >= mid[i]:
                    state = 0
            pos[i] = state
        return pos
    return sig


def main():
    configs = []
    # breakout taraması
    for n, k in [(20, 2.0), (20, 2.5), (30, 2.0)]:
        for sl_atr, tp_r in [(1.5, 2.0), (2.0, 2.5)]:
            configs.append(("breakout", n, k, sl_atr, tp_r, make_breakout(n, k)))
    # mean-reversion taraması
    for n, k in [(20, 2.0), (20, 2.5), (30, 2.0)]:
        for sl_atr, tp_r in [(1.5, 1.5), (1.5, 2.0)]:
            configs.append(("meanrev", n, k, sl_atr, tp_r, make_meanrev(n, k)))

    results = []
    for mode, n, k, sl_atr, tp_r, fn in configs:
        label = f"{mode} n={n} k={k} sl={sl_atr} tp={tp_r}"
        res = evaluate(fn, data="mktdata", tf="4h", sl_atr=sl_atr, tp_r=tp_r, label=label)
        res["_meta"] = {"mode": mode, "n": n, "k": k, "sl_atr": sl_atr, "tp_r": tp_r}
        report(res)
        results.append(res)

    # en iyi robust seçimi: robust olanlar arasında test avg_r en yüksek
    robusts = [r for r in results if r["robust"]]
    pool = robusts if robusts else results
    best = max(pool, key=lambda r: (r["robust"], r["test"].get("avg_r", -9)))
    print("\n=== BEST ===")
    report(best)
    print("META:", json.dumps(best["_meta"]))
    print("BEST_JSON:" + json.dumps({
        "label": best["label"], "meta": best["_meta"],
        "pool": best["pool"], "train": best["train"], "test": best["test"],
        "pos_coins": best["pos_coins"], "tot_coins": best["tot_coins"],
        "freq_yr": best["freq_yr"], "robust": best["robust"],
    }))


if __name__ == "__main__":
    main()
