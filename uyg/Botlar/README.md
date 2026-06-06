# 🤖 Algoritmik Trading Botları ve Fon Yönetim Simülatörleri

Bu klasör, Smart Money (Akıllı Para) sinyallerini kullanarak hem Bireysel Kasa Katlama (Bileşik Getiri) hem de Kurumsal Prop Firması kural ve limitlerine göre uyarlanmış 11 farklı optimal botu içermektedir.

## 💼 KİŞİSEL FON & BİLEŞİK GETİRİ BOTLARI
Bu botlar, prop firmalarının limitlerinden bağımsız, kendi kişisel kasanızı bileşik getiriyle veya düzenli maaş ödemesiyle büyütmek için tasarlanmıştır.

1. **`01_Asimetrik_Sniper_Bot.py`**: Yüksek kazanç hedefleyen tam otonom sniper bot. Kelly formülüyle agresif girişler yapar.
2. **`02_Guvenli_Hasat_Maas_Botu.py`**: Hesabı riske atmadan her ay düzenli nakit (maaş) çekmeyi hedefleyen daha defansif bir yapı.
3. **`03_Manuel_Sinyal_Jeneratoru.py`**: İşlemlere bizzat kendiniz girmek istiyorsanız, modelin sinyallerini okunaklı formatta basan asistan.
4. **`04_Optimal_Sniper_Harvest.py`**: Hem agresif Sniper gücünü hem de kâr çekimini (Harvest) birleştiren en dengeli bileşik getiri botu.
5. **`05_Dinamik_Kelly_Hasat_Botu.py`**: Kaybedince riski azaltan, kazanınca artıran, tamamen kendini korumaya odaklanmış dinamik sistem.

## 🏢 PROP FİRMASI (KURUMSAL) SINAV & YÖNETİM BOTLARI
Bu botlar, FTMO, Funding Pips gibi kurumsal firmaların acımasız kurallarına (-%5 Günlük, -%10 Max DD) göre hayatta kalıp nakit sızdırmak için yazılmıştır.

6. **`06_Prop_Firm_5K_Kaplumbaga.py`**: 5K'lık zorlu (-%3 Günlük limitli) sınavlar için Kelly kaldıracını 0.8x'te kilitleyip yavaş ama güvenli ilerleyen strateji.
7. **`07_Prop_Firm_5K_Yuksek_Kaldirac.py`**: Standart 5K (-%5 limit) hesabı 1.5x Kelly kaldıracı ile zorlayan agresif sistem.
8. **`08_Prop_Firm_5K_Agresif_RR.py`**: Dinamik kaldıracı tamamen iptal edip katı Sabit R/R (-%2 Kayıp / +%4 Kazanç) uygulayan sistem.
9. **`09_Prop_Firm_5K_Kutsal_Kase_Hibrid.py`** 👑: **(Nihai 5K Botu)** -%1 Sabit Risk alarak zombi sendromunu önleyen ve hesabın patlamasını imkansız hale getiren Hibrid sistem.
10. **`10_Prop_Firm_50K_Son_6_Ay.py`** 💎: **(Nihai 50K Botu)** Hibrid botun 50.000$'lık versiyonu. Son 6 aylık piyasada elenmeden hayatta kalan versiyondur.

## 🚀 CANLI PİYASA (LIVE MARKET) ENTEGRASYONU
Simülasyonlardan çıkıp gerçek parayla işlem yapmak için tasarlanan canlı üretim motoru.

11. **`11_Live_MT5_Execution_Bot.py`** ⚡: MetaTrader 5 altyapısı kullanan Prop Firmalarına (gerçek hesaplara) API üzerinden bağlanır. Canlı equity'yi okur, tam %1 risk alacak lot miktarını milimetrik hesaplar ve Hibrid stratejiyi borsaya otomatik emir olarak gönderir. Vur-Kaç hedefine (örn: $2500) ulaştığında kendini kilitleyerek işlemleri durdurur.

## 💡 Kurulum ve Çalıştırma
Botlar doğrudan terminal üzerinden çalıştırılabilir:
```bash
source venv/bin/activate
python uyg/Botlar/09_Prop_Firm_5K_Kutsal_Kase_Hibrid.py
```
> Tüm botlar geçmiş (Walk-forward) AI tahminleriyle çalıştığı için sinyal verisine ihtiyaç duyar. Canlı bot (MT5) ise aktif internet ve terminal bağlantısı gerektirir.
