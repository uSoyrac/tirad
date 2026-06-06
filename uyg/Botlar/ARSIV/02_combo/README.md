# 02 — COMBO ★ (kripto trend + funding)

## Strateji
İki ortogonal kripto kolu inverse-vol ağırlıkla birleştirir:
1. **Trend** — 20 coin Top-3 cross-sectional momentum
2. **Funding** — yüksek-funding short / düşük-funding long, market-nötr

`01_xasset`'in kripto-only çekirdeği. İnternet yoksa (ABD verisi alınamazsa) bu yedektir.

## Güncel test sonuçları (OOS 2025-26)
| Metrik | Değer |
|---|---|
| OOS Sharpe | **1.74** (walk-forward optimize ~2.25) |
| OOS CAGR | ~37% |
| OOS MaxDD | −14% |
| Kol korelasyonu | −0.06 (gerçek çeşitlendirme) |
| Ağırlık | trend 0.39 / funding 0.61 |
| Overfitting kapısı | DSR 0.99, PBO 0.03 (geçti) |

## Çalıştırma
```bash
quantlab/.venv/bin/python uyg/Botlar/ARSIV/02_combo/calistir.py
```

## ⚠️ Dürüst sınırlar
PAPER-TRADE adayı; survivorship-capped (kripto bugünün hayatta kalanları). `01_xasset`
ABD kolu eklenince bunu geçer (Sharpe 1.85→2.40). Funding kolu rejim/borsa-bağımlı
(binance'te çalışıyor, bybit'te zayıf).
