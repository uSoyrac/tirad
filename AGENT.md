# AGENT TALİMATLARI — ALPHA İSTİHBARAT SİSTEMİ (V31 KOMUTAN MODU)

Bu dosya Claude Code ve diğer AI agent'ların bu proje üzerinde çalışırken uyması gereken kuralları, ulaşılan en son teknolojiyi ve önemli bağlamı içerir. 

LÜTFEN BU DOSYAYI DİKKATLE OKUYUN. PROJE KLASİK İNDİKATÖR BOTUNDAN ÇIKIP, KURUMSAL HEDGE FONLARI DÜZEYİNDE (QUANTITATIVE MACHINE LEARNING) BİR YAPAY ZEKA SİSTEMİNE (V31) DÖNÜŞMÜŞTÜR.

---

## 🚀 Proje Özeti (Gelinen Son Nokta: V31 Komutan Modu)

Klasik SMC ve ICT konseptlerinin ötesine geçtik. Artık **XGBoost** tabanlı, 100'den fazla türetilmiş derin özelliği (Deep Features) işleyen, Cross-Sectional Alpha (Çapraz Seçim) mantığıyla çalışan bir Makine Öğrenmesi motorumuz var.

- **Ana Canlı Bot:** `komutan_mod_1_haziran_botu.py` (V29/V31 Komutan Modu)
- **Ana ML Modeli:** `bot/engine/v27_xgb_model.json` (XGBoost Classifier)
- **Veri Seti:** Son 3 Yıllık 1 Saatlik Veri (Top 5 Coin: BTC, ETH, SOL, BNB, XRP)
- **Motor Klasörü:** `bot/engine/`

---

## 🧠 Komutan Modu (V29 - V31) Kuralları ve Mimarisi

Komutan Modu, sadece para kazanmayı değil, "Parayı Korumayı" hedefleyen defansif ama bir o kadar da agresif bir yapıdır.

### 1. Data Leakage (Veri Sızıntısı) Koruması ve V31 OOS Testi
En kritik kuralımız gerçekçiliktir. Model, son 3 yıllık (2023-2026) verinin sadece **İlk 2 Yılı (2023-2025)** ile eğitilmiş, son **1 Yılı (2025-2026)** tamamen kör bir şekilde (Out-Of-Sample) test edilmiştir. 
- V31 Kusursuz Testinde $100'lık bakiye 52 hafta (1 yıl) boyunca kör teste sokulmuş ve 1 yılın sonunda **$98.60** olarak kalmıştır.
- Sistemin kör olduğu bu yatay piyasada sadece 17 işlem açarak parasını koruması, "Hayatta Kalma (Survival)" başarımızın kanıtıdır.

### 2. Komutan Kalkanı (ADX > 20 Rejimi)
Yapay Zeka (XGBoost) ne kadar güçlü bir "Al" sinyali (Prob > 0.55) üretirse üretsin, piyasada bir trend yoksa (ADX 14 < 20) bot işlem açmayı reddeder. Testere (Chop) piyasasında nakitte kalarak sermayeyi korur.

### 3. Eksponansiyel Trailing Stop (Sınırsız Kâr)
Sabit bir TP (Take Profit) seviyesi kullanmıyoruz.
- Fiyat **2 ATR** kâra ulaştığında Stop Loss başa başa (Breakeven) çekilir.
- Fiyat yükselmeye devam ettikçe Stop Loss, fiyatı **2 ATR** geriden takip eder.
- Trend (Boğa) devam ettiği sürece kâr ucu açık (sınırsız) bir şekilde katlanır. Model eğitim setindeki (Boğa) simülasyonunda 10.000 doları milyarlara bu sayede katlamıştır.

### 4. Cross-Sectional Alpha (Çapraz Momentum)
Aynı saat içinde 5 coinin 3'ünden sinyal gelirse parayı üçe bölmüyoruz.
- Tüm sinyal veren coinler arasında son 10 mumluk ivmesi (`slope_10_pct` veya CVD) **EN YÜKSEK** olan **TEK** coin seçilir. Paranın risk edilebilir kısmı en güçlü ata oynanır.

---

## 🛠️ ML (Machine Learning) Pipeline

Yeni bir yapay zeka modelini baştan sona eğitmek isterseniz sırası şudur:

1. **Veri İndirme:** `python bot/engine/download_v31_data.py` (Son 3 yılın verisini indirir).
2. **Feature Engineering:** `python bot/engine/feature_engineer_v31.py` (ADR, CVD, Log Return, Volatilite vs. özellikleri üretir. Hedef TP 3.5 ATR, SL 1.5 ATR, Horizon 36 mumdur).
3. **Model Eğitimi & OOS Testi:** `python bot/engine/run_v31_pure_oos_backtest.py` (Modeli XGBoost ile ilk 2 yıl eğitir, son 1 yıl kör teste sokar ve hafta hafta raporlar).

---

## 👨‍💻 Claude İçin Geliştirici Kuralları

Eğer Claude olarak kodlara müdahale edeceksen şu acımasız gerçekleri aklından çıkarma:
1. **Hayal Satma:** %100 kazanma oranı veya milyarlık OOS testleri vaat etme. Gerçek piyasada komisyon (%0.04) ve slippage (%0.05) gerçeği vardır. Spreadler kazancı yer.
2. **Data Leakage'a Dikkat Et:** Yeni bir özellik denerken, test ettiğin verinin eğitim setinde OLMADIĞINDAN %100 emin ol.
3. **Kutsal Kâse Yok:** Yeni indikatörler eklemek yerine mevcut modelin hiper-parametrelerini (ADX eşiği, Trailing mesafe ATR'si, XGBoost derinliği) optimize etmeyi teklif et.
4. **Bağımlılıklar:** `pandas-ta` yerine saf `numpy/pandas` hesaplamaları veya `ta` kütüphanesini kullan.

Bize (Uygar ve Antigravity'e) her zaman gerçekçi, acımasız ve sağlam matematiksel argümanlarla gel. 
Kolay gelsin Komutan!
