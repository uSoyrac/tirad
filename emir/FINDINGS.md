# EMIR — Gerçek Veri Bulguları (2026-05-30)

> Veri GitHub Actions runner'ında **canlı** çekildi (Binance US-IP'den engelli →
> otomatik **Bybit** fallback). Son 3 ay · 4H · BTC/ETH/SOL/BNB/XRP · 543 mum/coin.
> Tam sonuç: `emir/results_real.md`. Üretici: `emir/fetch_and_backtest.py` + CI.

## Acı Gerçek (özet)
| Metrik | Gerçek |
|---|---|
| İşlem | 100 |
| Win Rate (fee'li) | **%34** |
| Beklenti | **−0.21 R/işlem** |
| Toplam | −21 R |
| Max ardışık kayıp | **8** |
| ORP $100 → | **$0 (−%100, iflas)** |
| Sabit %4 → | $25.42 (−%74.6) |

## Üç Kanıtlanmış Sonuç
1. **XGBoost beyni sahte veriyle eğitilmiş** (önceki rapor: seed=42 mock,
   label 268/268 eşleşme). %75 WR döngüsel/geçersiz.
2. **Ham SMC sinyali gerçek veride −EV.** Bu clean-room baseline'da WR %34,
   beklenti −0.21R. (Not: bu, tam `score_slice_v2` motoru DEĞİL; AI filtresi YOK.)
3. **ORP "risksiz" DEĞİL.** Gerçekte 8 ardışık kayıp geldi; deficit recovery +
   %20 cap bu seride kasayı **$0'a** götürdü. AGENT.md Faz 4'teki "risksiz / her
   zaman siler" ifadesi YANLIŞ — düzeltilmeli.

## Ne KANITLAMAZ (dürüstlük sınırı)
- Bu, takımın tam SMC+XGBoost sisteminin değil, **kuralların temiz baseline'ının**
  testidir. XGBoost olasılık filtresi (>0.60) burada UYGULANMADI.
- Yani "sistem çöp" demiyoruz; "ham sinyal + mock-eğitimli beyin + mevcut ORP =
  gerçek veride kanıtlanmış edge YOK ve para yönetimi iflas ettirebilir" diyoruz.

## Sıradaki Adımlar (öncelik)
1. **Tam motoru CI'da koştur:** ta/ccxt'yi CI'da kur, `score_slice_v2` +
   `vectorized_dataset_builder.py`'yi GERÇEK veriyle besle → gerçek feature/label.
2. **XGBoost'u gerçek veriyle yeniden eğit** (mock'u çöpe at). 0.60 eşiği + WR'yi
   gerçek hold-out'ta ölç.
3. **ORP'ye devre kesici (circuit breaker):** N ardışık kayıpta risk'i base'e
   sabitle / döngüyü dondur. `dd_scaling=True` + recovery_factor>1.0 etkisini ölç.
4. Ancak edge gerçek veride pozitif çıkarsa canlıya yaklaş.
