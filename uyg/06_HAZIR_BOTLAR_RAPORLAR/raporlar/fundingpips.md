# FundingPips-yerli edge araştırması (kendi enstrümanları)

Evren: 18 enstrüman (G10 FX + indeks + metal), günlük, maliyet 3bps/turnover. Train<2025 / OOS 2025-26. Aynı dürüst boru hattı.

## Aday stratejiler — IS vs OOS Sharpe (overfit kontrolü)

| strateji | IS Sharpe | OOS Sharpe | OOS CAGR | OOS MaxDD |
|---|---|---|---|---|
| TSMOM-30 | -0.79 | 0.01 | -0% | -5% |
| XSEC-30-k3 | -0.86 | 0.33 | 5% | -27% |
| TSMOM-60 | -0.64 | 0.62 | 2% | -4% |
| XSEC-60-k3 | -1.03 | 0.72 | 17% | -27% |
| TSMOM-90 | -0.34 | 0.64 | 2% | -4% |
| XSEC-90-k3 | -0.88 | 0.79 | 20% | -22% |
| TSMOM-120 | -0.27 | -0.13 | -1% | -7% |
| XSEC-120-k3 | -1.09 | 0.76 | 19% | -23% |

## En iyi OOS aday: **XSEC-90-k3** (OOS Sharpe 0.79) — yıl-bazı

| yıl | Sharpe | getiri |
|---|---|---|
| 2015 | -0.83 | -11% |
| 2016 | 0.65 | +11% |
| 2017 | -2.10 | -19% |
| 2018 | -1.53 | -19% |
| 2019 | -2.08 | -24% |
| 2020 | -0.57 | -18% |
| 2021 | -0.45 | -7% |
| 2022 | -1.22 | -26% |
| 2023 | -1.73 | -21% |
| 2024 | -0.57 | -9% |
| 2025 | 1.13 | +20% |
| 2026 | 0.52 | +5% |

## Yorum (dürüst)

**FundingPips enstrümanlarında price-only momentum/trend OOS'ta zayıf (en iyi XSEC-90-k3 Sharpe 0.79 < 0.8).** Bu, kendi LEVER #1 makro-TSMOM negatif bulgumuzla TUTARLI — FX/indeks trend son rejimde zor. Dürüst sonuç: bu basit edge'lerle FundingPips'i geçmeyi BEKLEME. Denenecek sonraki (veri gerektirir): FX CARRY (faiz-farkı, swap ile — funding-carry'mizin gerçek analoğu), daha kısa vade/intraday, ya da mean-reversion. Edge KANITLANMADAN challenge alma.