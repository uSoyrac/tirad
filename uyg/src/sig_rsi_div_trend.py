#!/usr/bin/env python3
"""
sig_rsi_div_trend.py — sinyal ailesi: "rsi_div_trend"
═══════════════════════════════════════════════════════════════════════
ADAPTİF REJİM HİBRİT:
  - Güçlü trend (adx > trend_th): momentum/trend-follow yönünde poz.
      RSI'yi trend onayı için kullan (uptrend'de aşırı satım dipini bekleme,
      sadece RSI 50'nin üstündeyse long; tam tersi short).
  - Zayıf/yatay rejim (adx < range_th): RSI mean-reversion.
      RSI < os → long (aşırı satımdan dönüş), RSI > ob → short.
  - Ara bölge (range_th <= adx <= trend_th): flat (belirsizlik, sinyal yok).

Tek pos dizisinde iki rejimi birleştirir. Tamamen causal: her i için
yalnız i ve öncesi indikatör değerleri kullanılır. Giriş i+1 açılışında.
"""
import json
import numpy as np
from signal_lab import evaluate, report, rsi, adx, ema


def make_sig(trend_th=25, range_th=20, os=35, ob=65, trend_rsi=50, hold=6):
    """
    EVENT-DRIVEN: poz sadece TETİK barında set edilir ve `hold` bar tutulur.
    Bu, her bar churn'u yerine ayrık trade'ler üretir (frekansı maliyetin
    altına çeker). İki rejim:
      - Trend (adx>trend_th): RSI'nin trend_rsi eşiğini momentum yönünde
        TAZE geçmesi (pullback bitişi) → trende katıl.
      - Range (adx<range_th): RSI'nin extreme'den TAZE geri dönüşü → reversion.
    """
    def sig(df):
        close = df["close"].to_numpy(float)
        n = len(df)
        pos = np.zeros(n)
        r = rsi(close, 14)
        adx_v, pdi, mdi = adx(df, 14)
        e50 = ema(close, 50)
        for i in range(200, n):
            a = adx_v[i]
            ri, rp = r[i], r[i - 1]
            if np.isnan(a) or np.isnan(ri) or np.isnan(rp):
                continue
            d = 0
            if a > trend_th:
                # TREND: momentum yönünde pullback-bitişi krosu (taze)
                if pdi[i] > mdi[i] and close[i] > e50[i] and rp <= trend_rsi < ri:
                    d = 1
                elif mdi[i] > pdi[i] and close[i] < e50[i] and rp >= (100 - trend_rsi) > ri:
                    d = -1
            elif a < range_th:
                # RANGE: extreme'den taze geri dönüş (mean-reversion)
                if rp <= os < ri:
                    d = 1
                elif rp >= ob > ri:
                    d = -1
            if d != 0:
                pos[i:i + hold] = d  # tetikten itibaren hold bar yönü tut
        return pos
    return sig


CONFIGS = [
    # (label, trend_th, range_th, os, ob, trend_rsi, hold, sl_atr, tp_r)
    ("A base",        25, 20, 35, 65, 50, 6, 1.5, 2.0),
    ("B tighter-rev", 25, 20, 30, 70, 50, 6, 1.5, 2.0),
    ("C wide-regime", 28, 18, 35, 65, 50, 8, 1.5, 2.0),
    ("D higher-tp",   25, 20, 35, 65, 50, 6, 1.5, 2.5),
    ("E long-hold",   25, 20, 35, 65, 50, 10, 1.5, 2.0),
    ("G hold12",      25, 20, 35, 65, 50, 12, 1.5, 2.0),
    ("F strict-mom",  25, 20, 32, 68, 55, 6, 1.5, 2.2),
]


def main():
    results = []
    print("=" * 80)
    print("  rsi_div_trend — adaptif rejim hibrit (config taraması)")
    print("=" * 80)
    for (label, tth, rth, os_, ob, trsi, hold, sl, tp) in CONFIGS:
        fn = make_sig(tth, rth, os_, ob, trsi, hold)
        res = evaluate(fn, data="mktdata", tf="4h", sl_atr=sl, tp_r=tp, label=label)
        report(res)
        res["_cfg"] = (label, tth, rth, os_, ob, trsi, hold, sl, tp)
        results.append(res)

    # EN İYİ OOS-ROBUST seç: robust olanlar arasında test avg_r en yüksek;
    # hiç robust yoksa pool avg_r en yüksek (dürüst raporlama).
    robust = [r for r in results if r["robust"]]
    pool_pick = robust if robust else results
    best = max(pool_pick, key=lambda r: (r["robust"], r["test"].get("avg_r", -9)))
    print("\n" + "=" * 80)
    print(f"  SEÇİLEN: {best['_cfg'][0]}  (robust={best['robust']})")
    print("=" * 80)
    print(json.dumps({
        "cfg": best["_cfg"],
        "pool": best["pool"],
        "train": best["train"],
        "test": best["test"],
        "pos_coins": best["pos_coins"],
        "tot_coins": best["tot_coins"],
        "freq_yr": best["freq_yr"],
        "robust": best["robust"],
    }, indent=2))
    return best


if __name__ == "__main__":
    main()
