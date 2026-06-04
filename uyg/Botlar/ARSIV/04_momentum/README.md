# 04 — MOMENTUM (cross-sectional Top-3)

## Strateji
Her bar 20 coin arasından en güçlü momentumlu (60-bar ROC) ve trend-sinyali veren EN İYİ
3 coini tutar. Sermaye 3 slota eşit bölünür, ATR-stop ile yönetilir. Bake-off'ta en yüksek
DOĞRU-KARAR oranlı (+EV) strateji.

## Güncel test sonuçları (OOS 2025-26)
| Metrik | Değer |
|---|---|
| OOS Sharpe | 1.12 (WF-opt 1.86) |
| Win-rate | **%41.8** (bake-off'ta en yüksek) |
| Beklenti | +$69.95 / işlem |
| OOS CAGR | ~35% |
| OOS MaxDD | −30% |
| Risk-of-ruin | %11.6 |

Not: tek başına en yüksek win-rate ama MaxDD yüksek; random alt-evrende kırılgan (combo
daha sağlam). En iyi rolü: xasset/combo içinde kol.

## Çalıştırma
```bash
quantlab/.venv/bin/python uyg/Botlar/ARSIV/04_momentum/calistir.py
```

## ⚠️ Dürüst sınırlar
PAPER-TRADE adayı; survivorship-capped. Tek-kol MaxDD −30% yüksek → çeşitlendirilmiş
kullanım (xasset) tercih edilir. WF-optimizasyonu yardımcı oluyor (1.12→1.86, ROC30/top-1).
