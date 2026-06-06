# FUTURES edge testi — 13 kontrat (endeks+emtia+tahvil+FX)

Managed-futures: TSMOM + cross-sectional momentum. Maliyet 3bps. train<2025/OOS.

| strateji | IS Sharpe | OOS Sharpe | OOS CAGR | OOS MaxDD | +yıl |
|---|---|---|---|---|---|
| TSMOM-30 | -0.10 | -0.28 | -2% | -6% | 5/12 |
| XSEC-30 | -0.05 | -0.29 | -21% | -48% | 3/12 |
| TSMOM-60 | 0.20 | 0.17 | 1% | -5% | 6/12 |
| XSEC-60 | -0.10 | 0.01 | -9% | -34% | 3/12 |
| TSMOM-90 | 0.12 | -0.52 | -3% | -9% | 5/12 |
| XSEC-90 | -0.04 | 0.07 | -5% | -34% | 5/12 |
| TSMOM-120 | 0.36 | -0.11 | -1% | -8% | 7/12 |
| XSEC-120 | 0.11 | -0.20 | -16% | -40% | 2/12 |

## En iyi: TSMOM-60 (IS 0.20 / OOS 0.17) — geçiş tahmini (TopStep proxy +6%/trail-4%/günlük-3%)

| vol-hedef | P(geç) |
|---|---|
| %5 | %23 |
| %8 | %29 |
| %10 | %29 |

## Yorum (dürüst)

**Futures zayıf: en iyi TSMOM-60 IS 0.20/OOS 0.17.** Managed-futures TSMOM son rejimde (makro-ETF testiyle tutarlı) zayıf — futures-native'de de robust edge çıkmadı. Dürüst: futures için kanıtlı edge YOK; crypto+hisse'ye odaklan. (Futures props ucuz/Türkiye-OK ama edge olmadan = kumar.)
- ⚠️ Trailing -4% DD futures-prop'ta SIKI; tek-dönem OOS; yfinance sürekli-futures yaklaşık. Yarı-oto (TradingView webhook) izinli, tam-bot çoğu firmada yasak.