# 🎯 NİHAİ RAPOR — Dürüst Edge & Gerçekçi Compound Sistemi

**Tarih:** 2026-05-31 · **Yöntem:** Dürüst harness + multi-agent edge avı + gerçekçi portföy compound
**Veri:** 20 coin × 5.4 yıl gerçek Binance 4H (`mktdata/`), maliyet+OOS+korelasyon dahil

---

## 1. Yolculuk: fantezi → gerçek

| Aşama | Bulgu |
|---|---|
| Başlangıç iddiası | S3 (trend+OB) %87 WR, $100→$78K |
| **Dürüst dolum modeli** | %87 = anlık-dolum artefaktı; gerçek limit dolum %18-22, **WR %37, beklenti −0.11R** |
| Rejim/feature gate (ATRP/VROC/ADX) | 1-yılda parladı, 5.4y'da çöktü (overfit) — robust düzeltme YOK |
| Çıkış süpürmesi | Hiçbir TP/SL/trail şeması S3'ü pozitife çevirmedi → **S3 ölü** |
| Momentum pivotu | Market-nötr cross-sectional momentum: gerçek ama yavaş (Sharpe ~0.5 funding sonrası, 26 işlem/yıl) |
| **Multi-agent edge avı** | 10 aile tarandı, **4 gerçek trend/breakout edge** adversarial doğrulamayı geçti |

**Ders:** Kripto'da robust edge = **düşük-WR (%30-37) yüksek-payoff trend-takibi.** >%60 WR mean-reversion robust DEĞİL (rsi/bollinger/confluence hepsi elendi).

---

## 2. Hayatta kalan gerçek edge'ler (adversarial doğrulanmış)

| Edge | Beklenti | WR | Frekans/yıl | PF | Holdout |
|---|---|---|---|---|---|
| **donchian_breakout** (n=40, +ATR onayı) | +0.104R | 32% | 713 | 1.15 | +0.222 (en güçlü) |
| **vol_regime_mom** (yüksek-vol + momentum) | +0.078R | 37% | 657 | 1.14 | tüm dilimler + |
| **supertrend_regime** (ST10/3 + ADX≥25) | +0.071R | 30% | 1135 | 1.11 | +0.108 |

İnce ama gerçek. Look-ahead yok, +1 bar lag'e dayanıklı, çoğu coinde pozitif, tüm zaman dilimlerinde pozitif.

---

## 3. GERÇEKÇİ OPTİMAL SİSTEM

**Sinyal:** donchian + supertrend ensemble · 20 coin · 4H · long+short · SL=2×ATR, TP=2.5-3R
**Frekans:** ~1849 işlem/yıl (ensemble) · E +0.084R · PF 1.13

**Boyutlama (KRİTİK):** fractional Kelly / **risk %1-2 per işlem + eşzamanlı max 10-20 pozisyon tavanı**
→ korelasyon riskini ehlileştirir (tavansız MDD %98, tavanlı %8-25)

| risk% | maxPoz | CAGR | MDD |
|---|---|---|---|
| %2 | 10 | %22 | %8 |
| %3 | 10 | %32 | %12 |
| %2 | 20 | %35 | %25 |

---

## 4. Para-yönetimi verdict (projenin ORP temelini düzeltir)

İnce + düşük-WR + korelasyonlu edge'de **recovery sistemleri kasayı BATIRIYOR:**

| Sistem | P(ruin) |
|---|---|
| **Kelly .25 / sabit küçük kesir** | **%0** ✓ |
| Paroli | %0.1 (MDD %88) |
| Adaptive Hybrid | %66 ✗ |
| Fibonacci | %84 ✗ |
| **ORP %5** | **%99** ✗ |

→ **ORP/Paroli/Fibonacci/martingale KULLANMA.** Sadece fractional Kelly + risk tavanı.

---

## 5. $100 → $10k senaryosu (hasat-döngüsü, korelasyon korunmuş bootstrap)

| risk/işlem | P($10k'ya ulaşma) | Süre |
|---|---|---|
| %1 | **%76** | ~1.5 yıl |
| %2 | **%61** | ~1.3 yıl |
| %3 | %52 | ~1.2 yıl |

**Senin "yüksek WR" hedefin işlem-seviyesinde değil, döngü-seviyesinde karşılanıyor:** %61-76 olasılıkla ~1.5 yılda $10k. Ulaşınca çek → $300 resetle → tekrarla. Frekans yüksek olduğu için ince edge bile makul sürede katlıyor.

---

## 6. Dürüst caveat'lar

1. **İşlem-WR sadece %31** — çok kayıp göreceksin; sistem asimetri+frekansla kazanıyor, sabır gerektirir.
2. **Edge ince (PF 1.13)** — canlı slippage/funding backtest'ten kötüyse marj erir. Maliyet varsayımı (7bps) canlıda doğrulanmalı.
3. **Short funding** trend sim'de tam modellenmedi → net biraz düşer.
4. **Rejim riski** — trend-takibi choppy yıllarda (2023 gibi) zayıflar; ~1.5 yıl edge'in devamını varsayar.
5. **Fast 100x + >%60 işlem-WR + ruin=0** aynı anda olmuyor — bu gerçeğin sınırı.

---

## 7. Sıradaki (FAZ 4)

1. **Paper-trade** (Binance testnet) — donchian+supertrend, risk %1-2, max 10 poz; canlı dolum/funding/maliyeti doğrula.
2. vol_regime'i ajanın seçici config'iyle ensemble'a düzgün ekle (3. edge).
3. Edge zayıflama izleme (rolling expectancy) → düşerse stake küçült.
