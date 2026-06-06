#!/usr/bin/env python3
"""
sig_confluence_3.py — sinyal ailesi "confluence_3"

Çoklu-indikatör KONFLUANS:
  SuperTrend yönü  +  MACD histogram işareti  +  RSI orta-bölge konumu
  ÜÇÜ DE aynı yönde hizalanınca gir.

Long  (pos=+1):  ST==+1  AND  macd_hist>0  AND  RSI > rsi_mid (momentum yukarı, ama aşırı değil)
Short (pos=-1):  ST==-1  AND  macd_hist<0  AND  RSI < (100-rsi_mid)

RSI "orta-bölge dışı değil" yorumu: aşırı uçlardan kaçın (geç kalmış girişi engelle)
  -> RSI long için rsi_mid..rsi_hi aralığında, short için (100-rsi_hi)..(100-rsi_mid).

Causal: pos[i] yalnız i ve öncesini kullanır; giriş harness'ta i+1 açılışında.
"""
import json
import numpy as np
from signal_lab import evaluate, report, supertrend, rsi, macd


def make_sig(st_p=10, st_m=3.0, rsi_mid=50.0, rsi_hi=70.0,
             macd_fast=12, macd_slow=26, macd_sig=9):
    def sig(df):
        n = len(df)
        pos = np.zeros(n)
        st = supertrend(df, st_p, st_m)
        c = df['close'].to_numpy(float)
        r = rsi(c, 14)
        _, _, hist = macd(c, macd_fast, macd_slow, macd_sig)
        rsi_lo_short = 100.0 - rsi_hi
        rsi_mid_short = 100.0 - rsi_mid
        for i in range(200, n):
            # LONG konfluans: 3 onay aynı yön
            if (st[i] == 1 and hist[i] > 0 and rsi_mid < r[i] < rsi_hi):
                pos[i] = 1
            # SHORT konfluans: 3 onay aynı yön
            elif (st[i] == -1 and hist[i] < 0 and rsi_lo_short < r[i] < rsi_mid_short):
                pos[i] = -1
        return pos
    return sig


if __name__ == "__main__":
    # Küçük süpürme: RSI orta-bölge eşikleri + ST hassasiyeti + SL/TP
    configs = [
        dict(label="A st10/3 rsi50-70 sl1.5 tp2.0", st_p=10, st_m=3.0, rsi_mid=50, rsi_hi=70, sl_atr=1.5, tp_r=2.0),
        dict(label="B st10/3 rsi45-75 sl1.5 tp2.0", st_p=10, st_m=3.0, rsi_mid=45, rsi_hi=75, sl_atr=1.5, tp_r=2.0),
        dict(label="C st10/3 rsi50-70 sl1.5 tp1.5", st_p=10, st_m=3.0, rsi_mid=50, rsi_hi=70, sl_atr=1.5, tp_r=1.5),
        dict(label="D st10/3 rsi50-65 sl2.0 tp2.5", st_p=10, st_m=3.0, rsi_mid=50, rsi_hi=65, sl_atr=2.0, tp_r=2.5),
        dict(label="E st7/2.5 rsi50-70 sl1.5 tp2.0", st_p=7,  st_m=2.5, rsi_mid=50, rsi_hi=70, sl_atr=1.5, tp_r=2.0),
        dict(label="F st12/3 rsi48-72 sl1.5 tp1.8", st_p=12, st_m=3.0, rsi_mid=48, rsi_hi=72, sl_atr=1.5, tp_r=1.8),
    ]

    results = []
    print("=" * 80)
    print("  confluence_3 SÜPÜRME (mktdata 4h, 20 coin)")
    print("=" * 80)
    for cfg in configs:
        sl_atr = cfg.pop("sl_atr"); tp_r = cfg.pop("tp_r"); label = cfg.pop("label")
        fn = make_sig(**cfg)
        res = evaluate(fn, data="mktdata", tf="4h", sl_atr=sl_atr, tp_r=tp_r, label=label)
        report(res)
        res["_sl_atr"] = sl_atr; res["_tp_r"] = tp_r
        results.append(res)

    # En iyi OOS-robust: robust olanlar arasında test avg_r en yüksek; yoksa pool avg_r
    robusts = [r for r in results if r["robust"]]
    pool_for_best = robusts if robusts else results
    best = max(pool_for_best, key=lambda r: r["test"].get("avg_r", -9))
    print("\n" + "=" * 80)
    print(f"  EN İYİ: {best['label']}  robust={best['robust']}")
    print("=" * 80)
    print(json.dumps({
        "label": best["label"], "robust": best["robust"],
        "pool": best["pool"], "train": best["train"], "test": best["test"],
        "pos_coins": best["pos_coins"], "tot_coins": best["tot_coins"],
        "freq_yr": best["freq_yr"], "sl_atr": best["_sl_atr"], "tp_r": best["_tp_r"],
    }, indent=2))
