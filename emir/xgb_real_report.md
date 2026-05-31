# EMIR — XGBoost GERÇEK Veriyle Eğitim Raporu
_Üretim: 2026-05-31T06:12:26.432113Z (GitHub Actions, canlı internet)_
_Eğitim periyodu: son 6 ay · 4H · BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT_

## Veri Çıkarımı (gerçek score_slice_v2)
- **BTCUSDT** (binance): 1080 mum, 25 sinyal
- **ETHUSDT** (binance): 1080 mum, 41 sinyal
- **SOLUSDT** (binance): 1080 mum, 22 sinyal
- **BNBUSDT** (binance): 1080 mum, 23 sinyal
- **XRPUSDT** (binance): 1080 mum, 8 sinyal

Toplam gerçek sinyal: **119**
Ham (filtresiz) WR: **%29.4** (CI %22.0–%38.1)

## XGBoost — Gerçek Hold-out Sonucu (eşik 0.60)
- En iyi parametreler: `{'colsample_bytree': 0.8, 'learning_rate': 0.1, 'max_depth': 3, 'n_estimators': 50, 'subsample': 1.0}`
- Hold-out işlem: 24
- Eşiği geçen (alınan): 6  (seçicilik %25)
- **GERÇEK Win Rate: %83.3**  (5/6)
- %95 Güven Aralığı: %43.6 – %97.0

## Yorum
- Bu WR **gerçek piyasa verisinden** geldi; mock değil.
- Mock'taki %75/%76 ile karşılaştır: aradaki fark = eski beynin yanılsaması.
- ⚠️ Gerçek WR <0.60 ya da CI alt sınırı <0.50 → edge zayıf/kanıtsız.

_Model: emir/optimal_xgb_real.json · Dataset: emir/ml_dataset_real.csv_
