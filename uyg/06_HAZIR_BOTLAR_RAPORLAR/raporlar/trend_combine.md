# YÖNSEL TREND sleeve combo'ya eklenince (ADX≥30, risk-frac 0.005)

trend_dir sleeve tek-başına: OOS Sharpe 0.66. Korelasyon (full):

```
                crypto_trend  crypto_funding  trend_dir
crypto_trend            1.00           -0.07       0.28
crypto_funding         -0.07            1.00      -0.04
trend_dir               0.28           -0.04       1.00
```

## Kombine kitap — OOS (2025-26)

| Kitap | ağırlık | OOS Sharpe | CAGR | MaxDD |
|---|---|---|---|---|
| combo (trend+funding) | {'crypto_trend': 0.4, 'crypto_funding': 0.6} | 1.85 | 37% | -12% |
| combo + YÖNSEL-trend | {'crypto_trend': 0.26, 'crypto_funding': 0.38, 'trend_dir': 0.36} | 1.37 | 22% | -15% |

## Yıl-bazı (combo vs combo+trend, Sharpe)

| yıl | combo | combo+trend |
|---|---|---|
| 2023 | 1.18 | 0.79 |
| 2024 | 0.92 | -0.19 |
| 2025 | 2.18 | 1.23 |
| 2026 | 0.91 | 1.70 |

## Yorum (dürüst)

**Trend sleeve BOZDU: OOS Sharpe 1.85→1.37.** Chop-varyansı çeşitlendirme faydasını aşıyor — combo nötr kalması daha iyi. Trend getirisi cazip ama risk-ayarlı olarak kombine kitaba zarar veriyor. Eklenmemeli.
- risk-frac 0.005 ile; yıl-bazı tablo trend-yıl katkısı vs chop-yıl bedelini gösterir. Tek-dönem; DSR/PBO + maliyet sonrası nihai karar.