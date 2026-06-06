#!/usr/bin/env python3
"""
sig_ema_ribbon_pullback.py — sinyal ailesi: "ema_ribbon_pullback"

Fikir: EMA ribbon trend filtresi + trend-yönünde pullback girişi.
  ema(f) > ema(m) > ema(s)  → uptrend (ribbon dizili)
  fiyat ema(m)'e geri çekilip (low <= ema_m) yukarı dönünce (close > ema_m
  ve close > prev close) → LONG.
  Tersi (ema_f<ema_m<ema_s, high >= ema_m, close<ema_m, close<prev) → SHORT.

Causal: pos[i] yalnız i ve öncesini kullanır. Giriş harness'ta i+1 açılışında.
"""
import json
import numpy as np
from signal_lab import evaluate, report, ema


def make_sig(f, m, s):
    def sig(df):
        c = df["close"].to_numpy(float)
        l = df["low"].to_numpy(float)
        h = df["high"].to_numpy(float)
        ef, em, es = ema(c, f), ema(c, m), ema(c, s)
        pos = np.zeros(len(c))
        for i in range(s + 5, len(c)):
            up = ef[i] > em[i] > es[i]
            dn = ef[i] < em[i] < es[i]
            # pullback to mid EMA + reversal back in trend direction
            if up and l[i] <= em[i] and c[i] > em[i] and c[i] > c[i-1]:
                pos[i] = 1
            elif dn and h[i] >= em[i] and c[i] < em[i] and c[i] < c[i-1]:
                pos[i] = -1
        return pos
    return sig


# küçük süpürme: ribbon periyotları + (sl_atr, tp_r)
CONFIGS = [
    # (f, m, s, sl_atr, tp_r)
    (8, 21, 55, 1.5, 2.0),
    (8, 21, 55, 1.5, 1.5),
    (8, 21, 55, 2.0, 3.0),
    (5, 13, 34, 1.5, 2.0),
    (13, 34, 89, 1.5, 2.0),
    (8, 21, 55, 1.0, 1.5),
]


def main():
    results = []
    print("=" * 80)
    print("  ema_ribbon_pullback süpürme (mktdata 4h, long+short, maliyet sonrası)")
    print("=" * 80)
    for (f, m, s, sl, tp) in CONFIGS:
        lbl = f"ribbon({f},{m},{s}) sl={sl} tp={tp}"
        res = evaluate(make_sig(f, m, s), data="mktdata", tf="4h",
                       sl_atr=sl, tp_r=tp, label=lbl)
        report(res)
        res["_cfg"] = (f, m, s, sl, tp)
        results.append(res)

    # robust olanlar arasından en iyi test avg_r; yoksa en iyi pool avg_r
    robusts = [r for r in results if r["robust"]]
    pool_pos = robusts if robusts else results
    best = max(pool_pos, key=lambda r: r["test"].get("avg_r", -9))
    print("\n" + "=" * 80)
    print(f"  SEÇİLEN: [{best['label']}]  robust={best['robust']}")
    print("=" * 80)
    print(json.dumps({k: best[k] for k in
                      ("label", "pool", "train", "test", "pos_coins",
                       "tot_coins", "freq_yr", "robust")}, indent=2))
    return best


if __name__ == "__main__":
    main()
