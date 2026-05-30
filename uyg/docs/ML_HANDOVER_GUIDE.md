# Makine Öğrenmesi (ML) Geliştirme ve Devir Rehberi

Bu doküman, sistemin Yapay Zeka (XGBoost) modülünün başka bir AI asistanı (örneğin Claude, GPT-4 vb.) tarafından nasıl alınıp, optimize edilip, tekrar sisteme entegre edilebileceğini açıklayan **Açık Sistem Rehberidir**.

## 🧠 ML Mimarisi Nasıl Çalışıyor?

Botumuzun beyni `ilk_bot/optimal_xgb_model.json` dosyasıdır. Bu model, piyasadaki standart SMC (Order Block) sinyallerinin içindeki gürültüyü (noise) filtrelemek üzere eğitilmiştir.

### Özellik Seti (Features)
Model şu 6 girdi ile eğitilmiştir ve Canlı Bot bu 6 veriyi bekler:
1. `comp_score` (Float): Fiyat hareketinin sıkışma ve netlik skoru (4.5 - 10.0 arası)
2. `is_bullish` (Integer): Trend yönü (1 = Bullish, 0 = Bearish)
3. `atr_pct` (Float): Volatilite yüzdesi (`ATR / Close * 100`)
4. `rsi` (Float): Momentum
5. `macd_hist_norm` (Float): Normalize edilmiş MACD Histogram gücü
6. `vol_ratio` (Float): Hacmin son 20 mum ortalamasına oranı

---

## 🛠️ Başka Bir AI İle Modeli Geliştirme (Workflow)

Eğer Claude veya başka bir asistan ile modeli daha da iyileştirmek istersen şu adımları izlemelisin:

### Adım 1: Veri Çıkarımını İyileştirme
* Dosya: `uyg/src/vectorized_dataset_builder.py`
* **Claude'a Verilecek Komut:** *"Mevcut feature'lara ek olarak Bollinger Bandı Daralması (Squeeze) ve On-Balance Volume (OBV) ekleyelim. Bu dosyayı güncelle ve 12 aylık CSV veri setini yeniden üret."*

### Adım 2: Model Mimarisi ve Optimizasyon
* Dosya: `uyg/src/optimize_xgboost.py`
* Mevcut sistem **Precision (Keskinlik)** hedefine göre Grid Search yapmaktadır.
* **Claude'a Verilecek Komut:** *"XGBoost yerine LightGBM deneyelim veya Optuna kütüphanesi kullanarak parametre aramasını Bayesyen (Bayesian Optimization) yöntemine geçirelim. optimize_xgboost.py dosyasını Optuna kullanacak şekilde baştan yaz."*

### Adım 3: Entegrasyon (Paslaşma)
* Yeni AI asistanı optimizasyon scriptini çalıştırıp yeni bir `optimal_xgb_model.json` ürettiğinde, bu dosya otomatik olarak `ilk_bot/` klasörüne kopyalanmalıdır.
* `ilk_bot/live_scanner_30days.py` dosyası hiçbir koda dokunmadan direkt olarak bu yeni beyni kullanmaya başlayacaktır.

---

## ⚠️ Dikkat Edilmesi Gereken Kritik Kurallar (AI Asistanlarına Not)

> **DIKKAT (CRITICAL):**
> Yeni bir AI asistanı (Claude) modeli güncellerken şu kuralları ASLA esnetmemelidir:
> 1. **Probability Eşiği:** Modelin canlı bota onay vermesi için gereken olasılık (predict_proba) sınırı **%60 (0.60)** olarak kalmalıdır. Bunu %50'ye düşürmek, piyasa gürültüsünü içeri alır ve ORP'yi patlatır.
> 2. **Overfitting (Ezberleme):** Optimizasyon yaparken Karar Ağacı (Tree) derinliğini `max_depth = 2 veya 3` sınırında tutun. Ağaç derinleşirse model test setinde %90 başarılara ulaşır ancak canlı piyasada yanılır.

Bu sistem **sürekli gelişime (Continuous Improvement)** açık bir şekilde tasarlanmıştır. İstediğin AI ile dilediğin indikatörü ekleyip, "Paslaşarak" sistemi mükemmele ulaştırabilirsin.
