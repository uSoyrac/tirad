# 06 — HAZIR BOTLAR & RAPORLAR (3-kollu compound operasyonu)

Tek zekâ-çekirdeği (combo edge) → 3 kol → compound motoru. Kâr-al-çık → bankroll'a ekle →
yeniden-deploy = geometrik büyüme. Tüm botlar + son-8-ay sonuçları + tasarım burada.

## 3 KOL

| Kol | Bot dosyası | Piyasa / Firma | Edge |
|---|---|---|---|
| **Prop Crypto** | `bot_hyro.py` + `hyro_executor.py` | HyroTrader (Bybit perp, TR-OK, algo+testnet) | combo (DSR/PBO-gerçek, OOS ~1.85) |
| **Prop Hisse** | `equity_signal.py` | Trade The Pool (TR-OK, Signal Stack/manuel) | US tek-hisse momentum (OOS 1.66) |
| **Binance (kendi $)** | `hyro_executor.py --kelly` + `compound_engine.py` | Binance (kendi sermaye, max büyüme) | combo + compound |
| **Trend kolu (ops.)** | `TREND_BOTU_NOTU.md` (live_bot.py) | Binance — opportunistic trend | Donchian+ST+ADX≥30 (rejim-bağımlı) |
| FX-carry (diversif.) | `fx_carry_signal.py` | forex/FundingPips (manuel) | FX carry (modest 0.9) |

**Paylaşılan beyin:** `compound_engine.py` — fractional-Kelly (canlı equity'de compound) +
kill-switch (firma-farkında) + conviction-ölçekli risk. Tüm kollar kullanır.

## SON-8-AY SONUÇLARI (gerçek getiriler, survivorship haircut ×0.6, dürüst)
Detay: `raporlar/report_8month.md`. ⚠️ tek-yol simülasyon, 2025-26 cömert rejim → gerçekçi taban.

| Kol | Challenge | Funded | İçerde kâr-al | 8-ay net/büyüme |
|---|---|---|---|---|
| Prop HyroTrader (crypto) | 2 | 1 (sonra patladı) | 0× | **−$118** |
| Prop Trade The Pool (hisse) | 1 | 1 | 0× | **−$53** |
| Binance compound (¼-Kelly) | — | — | — | **$1000 → $1,061 (+%6)** |

**Dürüst okuma:** bu 8-ay penceresinde funded olduk ama payout eşiğine (crypto +%5 / hisse +%8.6)
ulaşmadan ya patladık ya pencere bitti → net hafif-negatif; Binance +%6. Haircut'sız/full-OOS
rakamları çok daha yüksekti (combo ¼-Kelly +%98, prop pass ~%65) — gerçek ikisinin arasında,
rejime bağlı. **Funded olmak ≠ para çekmek; forward kanıt şart.**

## DOĞRULANMIŞ EDGE HİYERARŞİSİ (ne işe yarar, ne yaramaz)
- ✅ Crypto combo (cross-sectional momentum + funding) — OOS 1.85, DSR 1.00/PBO 0.01. Ana edge.
- ✅ US hisse momentum — OOS 1.66, crypto'ya ortogonal. En kolay prop geçişi (~%63-66 TTP).
- ⚠️ FX carry — modest (0.9), düşük-turnover; diversifikasyon sinyali.
- ⚠️ Trend (Donchian/ST/HH-LL) — rejim-bağımlı (trend-yılları +, chop −). ADX≥30 ile OOS +0.08;
  combo'yu YERİNE geçmez, YANINDA opportunistic. Detay: raporlar/trend_*.md
- ❌ Futures (TSMOM): edge yok. ❌ Forex-ex-carry: edge yok. ❌ ML yön-tahmini: 4× yazı-tura.

## GÜVENLİK / DİSİPLİN
- Anahtarlar yalnız env (asla repo). Canlı emir öncesi kullanıcı onayı + testnet-önce.
- ≤¼-Kelly tavanı (f* survivorship-şişkin). Compound DD'yi büyütür → kill-switch şart.
- Compound COMBO'yu büyütür (gerçek edge), TREND'i değil (rejim-bağımlı → mirage'ı büyütmek ruin).
- Bölge: HyroTrader/Trade The Pool TR-OK; Breakout/FundingPips TR-yasaklı.

## DASHBOARD (tirad.45.143.11.97.nip.io)
/sinyal (crypto) · /hisse (hisse, challenge-hazır) · /forex (FX carry) · /bybit (testnet) ·
/saglik · /arastirma (haftalık re-research) · /rapor · /piyasa

Detaylı çalıştırma/bakım: **AGENT.md**.
