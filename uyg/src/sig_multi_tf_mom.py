#!/usr/bin/env python3
"""
sig_multi_tf_mom.py — sinyal ailesi: multi_tf_mom (çok-zamanlı momentum proxy)

Fikir: 4H veride uzun-vade momentum (roc ~90 gün ≈ 540 bar) ve kısa-vade
momentum (roc ~14 gün ≈ 84 bar) AYNI yönde ise o yönde gir; ayrışınca flat.
Trend-hizalama filtresi. Causal: pos[i] yalnız i ve öncesini kullanır.
"""
import json
import numpy as np
from signal_lab import evaluate, report, roc


def make_sig(long_bars, short_bars, thr):
    """Uzun ve kısa momentum aynı yönde + |momentum| eşik üstü ise hizalı gir."""
    def sig(df):
        c = df["close"].to_numpy(float)
        n = len(c)
        ml = roc(c, long_bars)    # uzun-vade momentum
        ms = roc(c, short_bars)   # kısa-vade momentum
        pos = np.zeros(n)
        start = long_bars + 5
        for i in range(start, n):
            l, s = ml[i], ms[i]
            if l > thr and s > thr:
                pos[i] = 1
            elif l < -thr and s < -thr:
                pos[i] = -1
            # ayrışma/zayıf momentum -> flat (0)
        return pos
    return sig


CONFIGS = [
    # (long_bars, short_bars, thr, sl_atr, tp_r)
    dict(long_bars=540, short_bars=84,  thr=0.0,  sl_atr=1.5, tp_r=2.0),  # baz: işaret hizası
    dict(long_bars=540, short_bars=84,  thr=0.03, sl_atr=1.5, tp_r=2.0),  # eşikli
    dict(long_bars=540, short_bars=84,  thr=0.05, sl_atr=2.0, tp_r=2.5),  # daha geniş stop/tp
    dict(long_bars=360, short_bars=60,  thr=0.03, sl_atr=1.5, tp_r=2.0),  # daha kısa lookback
    dict(long_bars=720, short_bars=120, thr=0.05, sl_atr=2.0, tp_r=3.0),  # daha uzun lookback
    dict(long_bars=540, short_bars=42,  thr=0.03, sl_atr=1.5, tp_r=2.5),  # çok kısa hızlı bacak
]


def main():
    results = []
    for cfg in CONFIGS:
        lb, sb, thr, sl, tp = cfg["long_bars"], cfg["short_bars"], cfg["thr"], cfg["sl_atr"], cfg["tp_r"]
        label = f"L{lb}_S{sb}_thr{thr}_sl{sl}_tp{tp}"
        sig = make_sig(lb, sb, thr)
        res = evaluate(sig, data="mktdata", tf="4h", sl_atr=sl, tp_r=tp, label=label)
        res["_cfg"] = cfg
        report(res)
        results.append(res)

    # En iyi OOS-ROBUST seçimi: önce robust olanlar, sonra test avg_r'ye göre
    robusts = [r for r in results if r["robust"]]
    pool_ranked = sorted(results, key=lambda r: (r["robust"], r["test"].get("avg_r", -9)), reverse=True)
    best = pool_ranked[0]
    print("\n=== EN İYİ ===")
    report(best)
    print("BEST_CFG:", json.dumps(best["_cfg"]))
    print("ANY_ROBUST:", len(robusts) > 0)
    return best


if __name__ == "__main__":
    main()
