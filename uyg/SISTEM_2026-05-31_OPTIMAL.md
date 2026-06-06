# 🎯 TIRAD — 31 MAYIS 2026 OPTİMAL SİSTEM & AI HANDOFF

> **Amaç:** Bu doküman, başka bir AI ajanının (veya geliştiricinin) bu projede **hatasız,
> sızıntısız, gerçekçi** testler yapabilmesi ve doğrulanmış sistemi anında devralabilmesi
> içindir. Tüm bulgular ~30 titiz, walk-forward, leak-free testin sonucudur. Hayal yok.

---

## 0. ALTIN KURALLAR (önce bunları oku — hatasız test için)

1. **VERİ YOLU:** Tüm motorlar `uyg/src/`'den çalışır. Veri `uyg/src/mktdata/` (4H, 20 coin, 5.4y gerçek Binance), `microdata/` (işlem sayısı+taker-buy), `funddata/` (funding). `cd /Users/uygar/trade/uyg/src` ile başla.
2. **BAĞIMLILIK:** `pip3 install ccxt yfinance scikit-learn statsmodels` (sistem python3'e kurulu). `live_scan.py` import için ccxt şart.
3. **SIZINTI (EN KRİTİK HATA):** Bot replay'inde meta-modeli **SADECE OOS-öncesi veriyle eğit** (`entry_ts < pencere_başı`). Tüm-veriyle eğitilmiş `meta_model*.pkl` ile replay = **look-ahead, sonuçları 3-4x şişirir.** Temiz sayı **walk-forward `wf_lift`**'ten gelir.
4. **PERFORMANS:** `live_scan.volume_profile` optimize edildi (vov hesabı için). `score_slice_v2` ~27ms/bar.
5. **Hiçbir sonuca güvenme** geçmediyse: walk-forward OOS + per-coin (≥%60 pozitif) + zaman-stabilite. In-sample/tek-split WR yalan söyler.

---

## 1. DOĞRULANMIŞ OPTİMAL SİSTEM (production)

**Evren:** Top-5 (BTC, ETH, SOL, BNB, XRP) · **TF: 4H** (1H batırır −%59/yıl, 1D çok seyrek; 4H sweet spot) · long+short · Binance futures.

**Karar zinciri (her 4H kapanışı):**
1. **Tetik:** Donchian(40) kırılımı **VE** SuperTrend(10,3) aynı yönde (çelişirse → yok).
2. **Rejim:** Sadece **BTC ana trendi (EMA200) yönünde** işlem (MDD %27→%9'a düşürür).
3. **Kalite (meta-label):** HistGradientBoosting, 19 feature (FEATURES_V2 + vov), olasılık ≥ 0.35 değilse → **işlem yapma** (sinyallerin ~%70'i elenir).
4. **Giriş:** sonraki bar açılışı. **Çıkış:** SL=2×ATR, TP=2.75R.
5. **Boyut:** fractional Kelly / vol-scaling (çekirdek) — recovery/martingale ASLA.

**Kod dosyaları:**
- `signal_lab.py` — ortak harness (indikatörler + simulate + evaluate, OOS).
- `meta_features_v2.py` — FEATURES_V2 (19 feature, vov dahil), build_v2, wf_lift.
- `bot_v2.py` — entegre bot (precompute, candidate, replay).
- `train_meta_v2.py` → `meta_model_v2.pkl`.
- `monthly_sim.py`, `stats_table.py` — leak-free ay-ay / detaylı tablo.
- **`live_bot.py` — PRODUCTION BOT (paper/testnet/live).** Tüm zincir: rejim-gate + agreement + BTC-hizalama + meta + seans filtresi + Kelly + SL/TP + SQLite. Anahtarlar SADECE env'den. Çalıştırma: `BOT_MODE=paper python3 live_bot.py --loop`.
- `regime_timing.py`, `sniper_sim.py` — rejim dedektörü (Motor1) + sniper.
- `mm_compare.py` — 12 para-yönetimi sistemi MC kıyası. `equity_milestones.py`, `bull_compare.py`, `tf_compare.py` — kıyas raporları.

**SEANS ETKİSİ (2. küçük gerçek kazanç, vov'dan sonra):** `time_test.py` → saat-içi etki gerçek: 16:00 UTC (+0.130R, US seansı) ve 00:00 (+0.104R) iyi; 08-12 UTC (ölü saat, +0.01R) zayıf. hour feature +0.007R lift. Bota DEAD_HOURS={8,12} olarak eklendi. Edge: +0.198→~+0.21R.

---

## 2. GERÇEK PERFORMANS (leak-free, son 12 ay favori dönem)

| Metrik | Değer |
|---|---|
| İşlem | 174 (~170/yıl) |
| WR | %37 (yön ML doğruluğu sadece %52 = ~yazı-tura) |
| Beklenti | +0.10R (tam-döngü, funding sonrası ~+0.075R) / +0.335R (son yıl) |
| Kazanan/Kaybeden | +2.70R / −1.04R (edge = ASİMETRİ, yön değil) |
| $100 sonucu (muhafazakar %0.75 risk) | $148-158 |
| $100 (orta %1.5 risk) | $226 |
| MaxDD | %10 (muhafazakar) / %20 (orta) |
| Ort. tutma | 144 saat (~6 gün) |
| Per-coin | BNB en güçlü (+0.62R), XRP en zayıf (+0.04R), 5/5 pozitif |

**Gerçekçi CAGR: ~%20-30** (favori yılda daha yüksek). Bu perakende dünya-klasmanı; AMA "$100→$10k aylarda" değil, yıllar.

---

## 3. PARA-YÖNETİMİ VERDICT (mm_compare.py — 12 sistem MC)

| Sistem | Medyan | P(iflas) | Not |
|---|---|---|---|
| Optimal-f (Vince) | 61x | %1.7 | en kârlı AMA MDD %89, pervasız |
| **half-Kelly** | 25x | **%0** | en iyi denge |
| vol-scaling | 8.7x | %0 | iyi risk-ayarlı |
| Kelly | 7x | %0 | güvenli |
| **ORP/recovery** | **$0** | **%72.5** | İFLAS |
| **Labouchère** | **$0** | **%78** | İFLAS |
| Fibonacci/D'Alembert/Oscar | — | %5-7.5 | ruin riskli |

**KURAL:** Kelly ailesi (Kelly/half-Kelly/Optimal-f) kazanır; "kaybedince büyüt" (ORP/Fibonacci/Labouchère/D'Alembert/Oscar) **batırır** (33'e varan kayıp serileri). Recovery sistemleri YASAK.

---

## 4. NE ÇALIŞMADI (test edildi, dürüstçe elendi — tekrar deneme)

- **S3 (OB+EMA+SuperTrend):** OB-midpoint limit %87 WR = **anlık-dolum fantezisi**; gerçek dolum %18-22, dürüst WR %37 breakeven.
- **Yön tahmini:** ML tüm veriyle (fiyat+hacim+funding+order-flow) yönü **%52** bilir (yazı-tura). Tavan bu.
- **Feature/veri eklemeleri:** funding, on-chain (stablecoin), order-flow (trade count+taker buy), OTT/Squeeze/Fibonacci/MSB → **HİÇBİRİ OOS lift vermedi**, sadece **vov** (+0.03R) işe yaradı.
- **Pairs/StatArb (cointegration):** %65 WR ama OOS −%995 (ilişkiler kırılıyor, fat-tail).
- **Mean-reversion (RSI/range):** kripto trend rejiminde para kaybettirir.
- **1H TF:** maliyet/gürültü edge'i yutar (−0.062R).
- **Quantum/RL/HFT/Market-making:** altyapı yok / overfit / bizim problemimiz değil.
- **Haber (GDELT):** bu ortamdan rate-limit (test edilemedi; beklenti düşük — fiyatlanmış).

---

## 5. VERİ ÇEKME (gerçek, anahtarsız public)

```python
import ccxt; ex=ccxt.binance({'enableRateLimit':True})
ex.fetch_ohlcv('BTC/USDT','4h',since=...)        # OHLCV — tam geçmiş
# microstructure (trade count+taker): fapi.binance.com/fapi/v1/klines alan [8],[9]
# funding: ex.fetch_funding_rate_history (tam geçmiş); OI/long-short sadece ~30 gün
```
Mevcut fetcher'lar: `fetch_multiyear.py`, `fetch_microstructure.py`, `fetch_funding.py`.

---

## 5.5. AL-TUT (BUY&HOLD) & BIST KIYASI (bull_compare.py / BIST testi)

- **Al-tut boğada sistemi EZER:** eşit-ağırlık top-5 5.4y = 15.5x (MaxDD %80); SOL 51x (MaxDD %97). Bizim sistem ~3-5x (MaxDD %10-28). Ama al-tut ayıda −%52/−%94, coin/zaman seçmek gerekir (yön=%52). Sistem = risk-ayarlı her-rejim.
- **BIST top-5 (günlük, long-only):** WR %53, +0.958R görünür AMA bu ENFLASYON nominal trendi (TL ~%85 düştü → 24x TL ≈ 3x USD); al-tut yine sistemi yeniyor; açığa satış kısıtlı. Aynı beta-vs-alfa + enflasyon yanılsaması.
- **DERS:** Kalıcı yükselen piyasada tutmak > aktif sistem. Sistemin değeri yüksek getiri değil, düşük-DD + her-rejim. Hangi piyasa/TF olursa olsun "hızlı-büyük" yok.

## 5.6. AGRESİF/PİYANGO MODU (aggressive_sim.py, lottery_3week.py)

Küçük stake + yüksek risk = +EV piyango AMA %75-95 deneme-ruin. $100→$10k/3hafta ≈ %3-5 olasılık (en iyi config), EV pozitif ama tek seferde değil. ML/Kelly değil; sadece risk duruşu. Rejim-gate lottery'yi marjinal iyileştirir (24%→26%), güvenilir yapmaz.

## 6. SIRADAKI (yapılacak)

1. **Forward paper-trade** (Binance testnet, YENİ kısıtlı anahtar, withdrawal kapalı) — backtest'in +0.10R'si canlıda tutuyor mu.
2. Freqtrade entegrasyonu (deploy framework).
3. İki mod: çekirdek (half-Kelly/vol-scaling, MDD≤%30) + agresif piyango sleeve (küçük stake, +EV, %80-90 döngü-ruin).

> **Felsefe:** Edge ince (+0.10R), yön ~rastgele (%52). Para ASİMETRİ × FREKANS × KELLY × DİSİPLİN ile gelir, yüksek-WR ile değil. "Sihirli indikatör/ML/kombinasyon" YOK — ~30 testle kanıtlandı. Gerçek olanı çalıştırmak, sahteyi aramaktan değerlidir.
