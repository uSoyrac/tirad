# 03 — FUNDING (market-nötr funding-pozisyonlama)

## Strateji
Cross-sectional, dolar-nötr: yüksek-funding (aşırı-kalabalık long) coinleri SHORT,
düşük/negatif-funding coinleri LONG. Günlük rebalance. Fiyat momentum'una ORTOGONAL —
trend'in kanadığı 2025-26 chop'unda kazandı; bu yüzden combo/xasset'te Sharpe yükseltir.

## Güncel test sonuçları (OOS 2025-26)
| Metrik | Değer |
|---|---|
| OOS Sharpe | **1.31** |
| OOS CAGR | ~33% |
| OOS MaxDD | −15% |
| Dekompozisyon | funding-harvest +%61, fiyat-P&L +%244 (fiyat-pozisyonlama domine, saf carry değil) |

## Çalıştırma
```bash
quantlab/.venv/bin/python uyg/Botlar/ARSIV/03_funding/calistir.py
```

## ⚠️ Dürüst sınırlar
Getiriyi fiyat-pozisyonlama domine eder (saf carry değil — saf delta-nötr harvest OOS'ta
NEGATİF çıktı, carry çürümüş). Rejim/borsa-bağımlı. Tek başına değil, **combo/xasset'te
ortogonal kol olarak** değerli. Paper adayı; survivorship-capped.
