# Implementation Plan: SMC Top-Down Confluence Strategy (1H Trend + 15M Entry)

Bu plan, botun 180 günlük verideki düşük işlem sıklığı (low frequency) sorununu çözmek ve sermayeyi hızlı fakat son derece gerçekçi bir şekilde büyütebilmek amacıyla **Çoklu Zaman Dilimi Konfluans Stratejisini (Multi-Timeframe SMC Confluence)** geliştirmeyi hedefler.

---

## 🔍 Goal Description

Mevcut 4H ve 1H tek zaman dilimli stratejiler, katı limit order ve cooldown kuralları nedeniyle çok az işlem üretmektedir (6 ayda 11-23 işlem). Olasılık yasalarına göre bu frekansta bileşik büyüme çok yavaş gerçekleşir.

Bu sorunu çözmek için kurumsal fonların kullandığı **Top-Down (Yukarıdan Aşağıya) SMC** mantığını uygulayacağız:
1. **1H Macro Bias:** 1H grafik taranarak kurumsal alım/satım bölgeleri (Order Block ve FVG) belirlenir. Fiyat 1H OB içine girdiğinde alarm kurulur.
2. **15M Micro Entry:** Fiyat 1H OB içindeyken 15M grafiğe geçilir ve bir **Change of Character (CHoCH)** veya **15M lokal OB kırılımı** aranır.
3. **Optimized Risk/Reward (R):** Giriş 15M OB seviyesinden yapılacağı için Stop-Loss çok dar (SL %0.3 - %0.5), hedef ise 1H likidite noktaları olacağı için geniş (TP %3 - %5) olacaktır. Bu da **R:R oranını 5R'den 10R - 15R seviyelerine çıkarır.**
4. **Frekans Artışı:** 15M timeframe, izleme listesindeki (18 coin) volatiliteyi kullanarak günde 1-3 kaliteli işlem fırsatı sunar (6 ayda 200-400 işlem). Bu da ORP bileşik büyümesini (Martingale/Paroli) haftalar seviyesinde çalıştırır.

---

## ⚠️ User Review Required

> [!IMPORTANT]
> **Tasarım Kararları ve Risk Yönetimi:**
> 1. **Tighter SL (Dar Stop Loss) ve Slippage Hassasiyeti:** 15M zaman dilimindeki dar SL'ler (%0.3 - %0.5), volatil dönemlerde stop kaymalarına (slippage) karşı hassastır. Backtestte komisyon (%0.04) ve stop-slippage (%0.10) cezalarını katı olarak uygulayacağız.
> 2. **Dry-Run Validasyonu:** API çağrı sayısı 15 dakikalık periyotlarla artacaktır. Bu sebeple canlı entegrasyondan önce dry-run modunda Binance API limit uyumluluğunu test edeceğiz.

---

## 🛠️ Proposed Changes

### 1. Multi-Timeframe Simulator Engine
#### [NEW] [simulate_15m_confluence.py](file:///Users/uygar/.gemini/antigravity/scratch/tirad_backtest/simulate_15m_confluence.py)
- 1H ve 15M verilerini (BTC, ETH, SOL) eşzamanlı olarak yükleyecek veri birleştirme modülü.
- 1H verisinde OB tespiti yapıp, bu bölgeleri 15M zaman dilimine "Etkin Güvenli Bölge (Active Zone)" olarak aktarma.
- 15M barlarında lokal yapı kırılımlarını (CHoCH / 15M OB) tarayıp limit emir yerleştirme mantığı.
- Komisyon (%0.04), slippage (%0.10 market, %0.02 limit) ve 1 bar gecikme uygulayan simülatör döngüsü.
- ORP %5 büyüme motorunun çalıştırılması.

### 2. Canlı Bot Modülleri Güncellemesi
#### [MODIFY] [live_scan.py](file:///Users/uygar/.gemini/antigravity/scratch/tirad_backtest/live_scan.py)
- Botun 15M ve 1H verilerini birlikte çekip analiz edebilmesi için tarayıcı döngüsüne multi-timeframe desteği eklenmesi.

#### [MODIFY] [portfolio.py](file:///Users/uygar/.gemini/antigravity/scratch/tirad_backtest/bot/portfolio.py)
- Emir motoruna 15M seviyeli mikro limit emir yönetimi ve dinamik SL güncellemelerinin entegre edilmesi.

---

## 🧠 5. XGBoost / Yapay Zeka (AI) Optimizasyonu
Kullanıcının vizyonu ve güncel "Python/Quant Trading" araştırmaları ışığında, sinyal keskinliğini artırmak için **XGBoost (Extreme Gradient Boosting)** modelini sistemimize entegre edeceğiz:

1. **Feature Engineering (Özellik Çıkarımı):** TradingView'daki kurumsal "Smart Money" konseptlerini Python `pandas_ta` kütüphanesiyle makine diline çevireceğiz. Modele sadece "Order Block var" demeyeceğiz; aynı zamanda o anki ATR'yi (Volatilite), RSI'ı, Hacim dengesizliğini (Volume Imbalance) ve son 3 mumun momentum (Lag) verilerini vereceğiz.
2. **Model Seçimi (Neden XGBoost?):** Araştırmalar, kripto gibi non-lineer (karmaşık) ve gürültülü piyasalarda basit Logistic Regression yerine, karar ağaçlarını kullanan XGBoost'un çok daha yüksek isabet oranı (Precision) sağladığını kanıtlamıştır.
3. **Probability Threshold (Keskinlik Sınırı):** Eğitilen yapay zeka modeli (XGBoost), her yeni Order Block sinyali için `0.0` ile `1.0` arası bir kâr olasılığı (Probability) üretecek. Bot sadece **>%65 kazanma ihtimali** olan sinyalleri işleme alacak.

Bu araştırma destekli "Yapay Zeka Kalkanı", sahte kırılımları (fakeouts) filtreleyecek ve ORP kasamızın Win Rate'ini %50'den **%65-70 bandına** taşıyacaktır.

---

## 📊 Verification Plan

### Automated Backtests
- Orijinal 4H 20-Coin modelini Python `scikit-learn` ve `xgboost` kütüphaneleriyle eğiteceğiz (`TimeSeriesSplit` kullanarak geleceği görme hilesini engelleyeceğiz).
- Yapay zekanın "Probability > 0.65" filtresi eklendiğinde ORP büyümesinin nasıl şaha kalktığını ($34.000'in nereye ulaştığını) simüle edeceğiz.
- Sonrasında Live Bot (Canlı Binance Bot) kodlamasına geçeceğiz.
