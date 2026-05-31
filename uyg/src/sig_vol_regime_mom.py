#!/usr/bin/env python3
"""
sig_vol_regime_mom.py — sinyal ailesi: "vol_regime_mom"
═══════════════════════════════════════════════════════════════════
Volatilite-rejimi + momentum.
  - Rejim ölçüsü: ATR% (atr/close) VEYA Bollinger-bandwidth (bb genişliği/orta).
    Bu ölçünün ROLLING PERCENTILE'ı (geçmiş W bar) ile rejim belirlenir — causal.
  - "expansion" modu: düşük-vol sıkışma sonrası genişleme breakout (rejim percentile
     düşük eşiğin ALTINDAYDI ve şimdi yükseliyor) → momentum yönünde işlem.
  - "high_vol_trend" modu: rejim percentile yüksek eşiğin ÜSTÜNDE (yüksek-vol trend)
     → momentum yönünde işlem.
  - Yön: roc(close, N) işareti.
Tüm hesaplar yalnız i ve öncesini kullanır (look-ahead yok). Giriş harness'ta i+1.
"""
import json
import numpy as np
from signal_lab import evaluate, report, atr, roc, bollinger


def _regime_series(df, kind, w):
    """Causal rolling-percentile [0..1] of the vol measure over window w."""
    close = df["close"].to_numpy(float)
    if kind == "atrp":
        a = atr(df, 14)
        measure = a / (close + 1e-12)
    else:  # bbw = Bollinger bandwidth
        m, up, lo = bollinger(close, 20, 2.0)
        measure = (up - lo) / (np.abs(m) + 1e-12)
    n = len(measure)
    pct = np.full(n, np.nan)
    import pandas as pd
    s = pd.Series(measure)
    # rolling rank of last element within window (causal): fraction of past <= current
    pct = s.rolling(w).apply(lambda x: (x[:-1] <= x[-1]).mean() if len(x) > 1 else np.nan,
                             raw=True).to_numpy()
    return measure, pct


def make_sig(kind="atrp", w=100, mode="high_vol_trend", lo_thr=0.30, hi_thr=0.70,
             mom_n=10, warmup=200):
    def sig(df):
        n = len(df)
        pos = np.zeros(n)
        close = df["close"].to_numpy(float)
        measure, pct = _regime_series(df, kind, w)
        r = roc(close, mom_n)
        for i in range(warmup, n):
            p = pct[i]
            if np.isnan(p):
                continue
            direction = 0
            if r[i] > 0:
                direction = 1
            elif r[i] < 0:
                direction = -1
            if direction == 0:
                continue
            if mode == "high_vol_trend":
                if p >= hi_thr:
                    pos[i] = direction
            elif mode == "expansion":
                # şu an rejim genişliyor: percentile düşük değil ama bir önceki bar düşüktü
                pprev = pct[i-1] if i > 0 else np.nan
                if (not np.isnan(pprev)) and pprev <= lo_thr and p > lo_thr:
                    pos[i] = direction
            elif mode == "low_vol":
                if p <= lo_thr:
                    pos[i] = direction
        return pos
    return sig


CONFIGS = [
    # (kind, w, mode, lo, hi, mom_n, sl_atr, tp_r)
    dict(kind="atrp", w=100, mode="high_vol_trend", hi_thr=0.70, mom_n=10, sl_atr=1.5, tp_r=2.0),
    dict(kind="atrp", w=100, mode="high_vol_trend", hi_thr=0.60, mom_n=14, sl_atr=2.0, tp_r=2.5),
    dict(kind="bbw",  w=120, mode="high_vol_trend", hi_thr=0.65, mom_n=12, sl_atr=1.5, tp_r=2.5),
    dict(kind="atrp", w=100, mode="expansion", lo_thr=0.25, mom_n=8, sl_atr=2.0, tp_r=2.0),
    dict(kind="bbw",  w=120, mode="expansion", lo_thr=0.30, mom_n=10, sl_atr=2.0, tp_r=3.0),
    dict(kind="atrp", w=80,  mode="low_vol", lo_thr=0.35, mom_n=12, sl_atr=1.5, tp_r=2.0),
]


def main():
    results = []
    for cfg0 in CONFIGS:
        cfg = dict(cfg0)
        sl_atr = cfg.pop("sl_atr"); tp_r = cfg.pop("tp_r")
        label = f"{cfg['kind']}|{cfg['mode']}|w{cfg['w']}|mom{cfg['mom_n']}|sl{sl_atr}|tp{tp_r}"
        sig = make_sig(**cfg)
        res = evaluate(sig, data="mktdata", tf="4h", sl_atr=sl_atr, tp_r=tp_r, label=label)
        report(res)
        res["_cfg"] = dict(cfg, sl_atr=sl_atr, tp_r=tp_r)
        results.append(res)

    # pick best OOS-robust by test avg_r, tie-break pool avg_r
    robusts = [r for r in results if r["robust"]]
    pool_for_pick = robusts if robusts else results
    best = max(pool_for_pick, key=lambda r: (r["test"].get("avg_r", -9), r["pool"].get("avg_r", -9)))
    print("\n" + "=" * 80)
    print("BEST:", best["label"], "robust=", best["robust"])
    print(json.dumps({"label": best["label"], "cfg": best["_cfg"],
                      "pool": best["pool"], "train": best["train"], "test": best["test"],
                      "freq_yr": best["freq_yr"], "pos_coins": best["pos_coins"],
                      "tot_coins": best["tot_coins"], "robust": best["robust"]}, default=str))
    return best


if __name__ == "__main__":
    main()
