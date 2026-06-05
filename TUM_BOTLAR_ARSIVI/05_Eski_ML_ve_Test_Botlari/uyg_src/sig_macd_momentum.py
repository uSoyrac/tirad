#!/usr/bin/env python3
"""
sig_macd_momentum.py — sinyal ailesi: "macd_momentum"

Mantik:
  macd(close) histogrami sifiri YUKARI keserse LONG, ASAGI keserse SHORT.
  ema200 trend filtresi: sadece trendin YONUNDE islem ac (long ise close>ema200, short ise close<ema200).
  Seyreklik/kalite icin hist esigi (atr-normalize) veya EMA onayi eklenebilir.

Causal: pos[i] yalnizca i ve oncesini kullanir. Giris i+1 aciliminda (harness).
"""
import json
import numpy as np
from signal_lab import evaluate, report, macd, ema, atr


def make_sig(hist_thr_atr=0.0, slow=26, fast=12, sig=9, use_ema200=True):
    """hist_thr_atr: hist'in atr'ye orani cinsinden minimum cross genligi (seyreklik filtresi)."""
    def sig_fn(df):
        c = df["close"].to_numpy(float)
        n = len(c)
        pos = np.zeros(n)
        _, _, hist = macd(c, fast=fast, slow=slow, sig=sig)
        e200 = ema(c, 200)
        a = atr(df, 14)
        for i in range(200, n):
            if not (np.isfinite(hist[i]) and np.isfinite(hist[i-1]) and np.isfinite(e200[i])):
                continue
            ai = a[i] if a[i] > 0 else c[i] * 0.01
            thr = hist_thr_atr * ai
            cross_up = hist[i-1] <= 0 and hist[i] > thr
            cross_dn = hist[i-1] >= 0 and hist[i] < -thr
            if cross_up:
                if (not use_ema200) or c[i] > e200[i]:
                    pos[i] = 1
            elif cross_dn:
                if (not use_ema200) or c[i] < e200[i]:
                    pos[i] = -1
        return pos
    return sig_fn


CONFIGS = [
    # (label, sig_kwargs, sl_atr, tp_r)
    ("c1 base ema200, thr0",       dict(hist_thr_atr=0.0),  1.5, 2.0),
    ("c2 ema200, thr0.05",         dict(hist_thr_atr=0.05), 1.5, 2.0),
    ("c3 ema200, thr0.1",          dict(hist_thr_atr=0.10), 1.5, 2.0),
    ("c4 ema200, thr0.05 wide tp", dict(hist_thr_atr=0.05), 2.0, 3.0),
    ("c5 ema200, thr0.1 tight",    dict(hist_thr_atr=0.10), 1.0, 2.0),
    ("c6 no ema200 filter, thr0.1",dict(hist_thr_atr=0.10, use_ema200=False), 1.5, 2.0),
]


def main():
    results = []
    for label, kw, sl, tp in CONFIGS:
        res = evaluate(make_sig(**kw), data="mktdata", tf="4h",
                       sl_atr=sl, tp_r=tp, label=label)
        report(res)
        res["_meta"] = dict(label=label, kw=kw, sl_atr=sl, tp_r=tp)
        results.append(res)

    robust = [r for r in results if r["robust"]]
    pool_robust = [r for r in robust if r["pool"]["n"] >= 100]
    cand = pool_robust or robust or results
    best = max(cand, key=lambda r: (r["robust"], r["test"].get("avg_r", -9)))
    print("\n=== BEST ===")
    report(best)
    print(json.dumps({k: best[k] for k in ("pool", "train", "test", "pos_coins",
                                           "tot_coins", "freq_yr", "robust")}, default=str))
    print("META:", best["_meta"])


if __name__ == "__main__":
    main()
