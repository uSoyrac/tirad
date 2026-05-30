# GERÇEKLİK KONTROLÜ v2 — Win Rate & ORP Dayanıklılık (2026-05-30)

> Yeni Baş Geliştirici (Claude) tarafından, "hayal satma" ilkesiyle, **eldeki gerçek
> dosyalar** üzerinden yapılan doğrulama. Üretici script: `uyg/src/reality_check.py`.

## TL;DR (Acı Gerçek)
1. **`ml_dataset_12m.csv` GERÇEK PİYASA VERİSİ DEĞİL — sentetik MOCK.**
   `create_mock_12m.py` içindeki `np.random.seed(42)` ile üretilmiş. Doğrulama:
   özellikler `np.allclose` → **True**, label'lar **268/268 (%100)** birebir aynı.
2. Dolayısıyla XGBoost'un raporladığı **%75–76 Win Rate döngüsel (circular)**:
   model, bir insanın `create_mock_12m.py`'de elle yazdığı label formülünü
   (base 0.40, comp_score>6.5→+0.20, ATR∈(1.0,2.5)→+0.10, vol_ratio>1.2→+0.15)
   geri ezberliyor. **Piyasa hakkında hiçbir şey kanıtlamıyor.**
3. **Şu an sistemin kanıtlanmış bir edge'i YOK.** %75 WR iddiası geçersiz.

## Kanıt
- `create_mock_12m.py` çıktı yolu birebir bu dosya: `uyg/src/ml_dataset_12m.csv`.
- Gerçek üretici `vectorized_dataset_builder.py`, repoda **bulunmayan**
  `../../../tirad_backtest/data/historical/{COIN}_USDT_4h.csv` dosyalarını ister.
- Seed=42 ile mock yeniden üretildiğinde CSV birebir eşleşti.

## Ölçülen Sayılar (mock veriyle — sadece referans, gerçek değil)
| Metrik | Değer | Not |
|---|---|---|
| Ham (filtresiz) WR | %67 (CI %62–71) | AGENT.md "%30-45" der; mock şişirmiş |
| XGBoost @0.60 WR | %76 (CI **%63–86**) | hold-out yalnız 50 işlem → çok gürültülü |
| Seçicilik | %62 | |

## ORP Dayanıklılık (motor sağlam, ama edge'e bağımlı)
"3 kere üst üste stop olursa ne olur?" — soğuk başlangıç, $100, %5 SL:
| Ardışık stop | Kalan kasa | Düşüş |
|---|---|---|
| 3 | $57.60 | **-42%** |
| 4 | $46.08 | -54% |
| 5 | $36.86 | -63% |

Monte Carlo iflas olasılığı (R=+2, 60 işlem): WR %50–75 aralığında **~%0**.
→ ORP matematiği intihar değil; pozitif beklenti varsa (2R kazanç) büyütür.
**AMA** "risksiz/Deficit her zaman siler" söylemi yanlış: ardışık stop **-42%+**
drawdown yapar. AGENT.md Faz 4'teki "risksiz" ifadesi düzeltilmeli.

## Sonuç ve Yol Haritası
Bot kodu (SMC + Limit Scale-In + ORP) mimari olarak tutarlı. **Tek kritik eksik:
gerçek veri.** Sıradaki adımlar (öncelik sırası):
1. **Gerçek 4H OHLCV** edin (BTC/ETH/SOL/BNB/XRP, 12 ay). Bu konteynerde
   Binance/CMC allowlist dışı → VPS/yerel ortamda veya CSV import ile.
2. `vectorized_dataset_builder.py` ile **gerçek** `ml_dataset_12m.csv` üret.
3. `reality_check.py`'yi gerçek veriyle çalıştır → **gerçek WR** ortaya çıksın.
4. Ancak ondan sonra model optimizasyonu (LightGBM/Optuna, yeni indikatör)
   anlamlı olur. Mock üstünde optimizasyon = gürültüyü cilalamak.

> Kural: Mock veri üstünde alınan hiçbir backtest sonucu canlı karara baz olamaz.
