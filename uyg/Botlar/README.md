# 🤖 Algoritmik Trading Botları ve Prop Firm Simülatörleri

Bu klasör, Smart Money (Akıllı Para) sinyallerini kullanarak Prop Firması (FTMO, Funding Pips vb.) kural ve limitlerine göre uyarlanmış özel simülasyon botlarını içerir.

## 🚀 Kutsal Kâse (Holy Grail) Botları
Borsa mühendisliğimizin ulaştığı nihai nokta olan "Hibrid (Dayanıklılık + Sabit R/R)" botlarıdır.
* **`prop_firm_journey_hybrid.py`**: 5.000$'lık hesaplar için optimize edilmiş nihai bot. İşlem başına %1 risk alır, zombi sendromuna yakalanmaz. 36$ yatırımla 1.5 yılda 3.600$+ kazandırmıştır.
* **`prop_firm_journey_50k.py`**: Hibrid botun 50.000$'lık hesap versiyonu. Son 6 aylık piyasada simüle edilmiş ve 289$ yatırımla 6.600$+ nakit kazandırmıştır. Hesabı patlatmadan aylarca elde tutabilme özelliğine sahiptir.

## 🧪 Deneysel ve Temel Simülatörler
Geliştirme sürecimizde test edilen ve borsanın matematiksel gerçeklerini ortaya çıkaran diğer botlarımız:
* **`prop_firm_journey_5k.py`**: 5K'lık zorlu (%3 Günlük DD limitli) sınav için geliştirildi. Kelly formülü ile kaldıracı 0.8x'e sabitleyerek güvenli liman stratejisi uygular.
* **`prop_firm_journey_5k_standard.py`**: 5K'lık standart (%5 Günlük DD limitli) sınav için geliştirildi. Kelly kaldıracını 1.5x'te serbest bıraktığı için dalgalı piyasada çabuk patlama riski taşır.
* **`prop_firm_journey_rr.py`**: Kelly'nin tamamen devre dışı bırakıldığı, tamamen sabit R/R (Risk: -%2, Kazanç: +%4) uygulayan en agresif test botudur.

## 💡 Kurulum ve Çalıştırma
Botlar doğrudan terminal üzerinden çalıştırılabilir:
```bash
source venv/bin/activate
python uyg/Botlar/prop_firm_journey_hybrid.py
```
> Tüm botlar geçmiş (Walk-forward) AI tahminleriyle çalıştığı için sinyal verisine ihtiyaç duyar.
