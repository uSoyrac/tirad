# 05 — PAPER (ileriye-dönük paper-trade defteri)

## Ne işe yarar
Combo'yu (ve genişletilince xasset'i) **ileriye-dönük, survivorship-free, SIFIR riskle**
doğrular. Backtest Sharpe'ın canlı-veride tutup tutmadığını parayı riske atmadan gösterir.
Her çalıştırmada: güncel hedef pozisyonlar + OOS-başından bugüne paper NAV + paper emirleri
yazar ve ledger'ı (`quantlab/reports_out/paper_book.json`) güncel-tutar.

## Güncel durum (kanonik combo defteri)
| Metrik | Değer |
|---|---|
| Paper NAV | $10.000 → ~$15.500 (516 günlük kayıt) |
| OOS Sharpe (defter) | 1.74 (backtest ile birebir = faithful) |
| MaxDD | −13.5% |

## Çalıştırma
```bash
quantlab/.venv/bin/python uyg/Botlar/ARSIV/05_paper/calistir.py
```
Yeni barlar geldikçe tekrar çalıştır → NAV uzar, forward track-record birikir.

## Bu CANLI değil
CANLI EMİR YOK. Bu, canlı sermayeden ÖNCEKİ disiplinli kapı. Gerçek forward kayıt için:
(1) taze bar çek (ccxt/yfinance), (2) zamanla (cron/4h). İstenirse `bot_xasset`'e genişletilir.
