# 01 — XASSET ★★ (3-kollu çapraz-varlık) — EN İYİ SİSTEM

## Strateji
Üç ORTOGONAL kolu inverse-vol ağırlıkla (train'de fit, OOS'ta uygula) birleştirir:
1. **Kripto-trend** — 20 coin arası en güçlü momentum Top-3 (cross-sectional, 60-bar ROC)
2. **Kripto-funding** — yüksek-funding short / düşük-funding long, dolar-nötr (market-neutral)
3. **ABD-momentum** — likit ABD hisseleri arası momentum Top-5 (gerçek breadth, 90-gün)

Edge = **yapısal çeşitlendirme**, yeni sinyal değil. Kollar düşük korelasyonlu
(−0.09..+0.18) → √N breadth Sharpe'ı yükseltir ve drawdown'ı düşürür.

## Güncel test sonuçları (OOS 2025-26, dürüst, maliyetler dahil)
| Metrik | Değer |
|---|---|
| OOS Sharpe | **2.40** |
| OOS CAGR | ~35% |
| OOS MaxDD | **−7%** |
| Kol korelasyonları | crypto-trend↔funding −0.07, ↔ABD +0.18, funding↔ABD −0.09 |
| Ağırlıklar (inverse-vol) | trend 0.25 / funding 0.37 / ABD 0.39 |
| Overfitting kapısı | **Deflated Sharpe 0.99, PBO 0.03** (geçti) |

Karşılaştırma: 2-kollu kripto-only combo 1.85 / MaxDD −12% → 3-kol 2.40 / −7%.

## Çalıştırma
```bash
quantlab/.venv/bin/python uyg/Botlar/ARSIV/01_xasset/calistir.py
```
Çıktı: OOS özeti + kol korelasyonları + **şu an her üç koldan tutulacak pozisyonlar.**
Gereksinim: `quantlab` paketi + yerel veri (`uyg/src/mktdata`, `funddata`) + ABD kolu için
`yfinance` + internet (offline → kripto-2-kol'a düşer).

## ⚠️ Dürüst sınırlar
- **PAPER-TRADE adayı, canlı sermaye DEĞİL.** İlk iş ileriye-dönük doğrulama (`05_paper`).
- **Survivorship-capped** (kripto + ABD bugünün hayatta kalanları; literatür ~%15-22/yıl
  şişirme) → işaret/dayanıklılık güvenilir, mutlak büyüklük iyimser olabilir.
- 620 ortak-işlem-günü örneklemi (2023-03+); ABD funding-analog 4. kol = gelecek iş.
