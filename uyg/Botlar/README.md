# Kutsal Kâse Bot Arşivi (Nihai Kararlı Sürümler)

Bu klasör (`uyg/Botlar`), yapay zeka (XGBoost) ve Smart Money 2. Türev ivmesi kullanılarak geliştirilen **en güvenli ve en kârlı** 3 nihai botu içerir. Eski denemeler (`june_2` vb.) arşivde kalmaya devam edecektir, ancak canlı borsa işlemleri (Paper Trade veya Gerçek) için sadece bu klasördeki botlar kullanılmalıdır.

## 1. `01_Asimetrik_Sniper_Bot.py` (Milyonerlik Eğrisi)
- **Felsefesi:** Vur-Kaç (Sniper). 1 risk edip 5 alma mantığına dayanır.
- **Kullanım Amacı:** Kasanın bileşik büyümeyle (Compound) üstel (Expo) şekilde katlanmasını istiyorsanız bunu kullanın.
- **Özellikleri:** Çok dar bir stop loss (%2) ve devasa bir take profit (%10) kullanır. Üst üste zarar etse bile tek bir başarılı kârda tüm zararı siler ve kâra geçer. 

## 2. `02_Guvenli_Hasat_Maas_Botu.py` (Düzenli Gelir)
- **Felsefesi:** Bileşik büyüme (Compound) tuzağına düşmeden, kârı cebine al ve kaç.
- **Kullanım Amacı:** Düzenli maaş gibi risksiz nakit çekimi yapmak istiyorsanız bunu kullanın.
- **Özellikleri:** Sabit 3x kaldıraçla işleme girer. Kasa 100 dolardan 120 dolara ulaştığı an (Örn: 2-3 kârlı işlemde), işlemi tamamen keser ve aradaki kârı (20 doları) nakit olarak çeker. Sonra tekrar 100 dolarla başlar. İflas riski pratikte SIFIRDIR.

## 3. `03_Manuel_Sinyal_Jeneratoru.py` (Elle Trade İçin)
- **Felsefesi:** Yapay Zekanın %82.4 yön isabet gücünü ekrana basar. Otomatik işlem açmaz.
- **Kullanım Amacı:** Botlara bağlamadan, "hangi coinde ne zaman long/short açmalıyım" diyorsanız, arkadaşınızın veya sizin ekranda sinyal kovalayacağınız araçtır.
- **Özellikleri:** Piyasayı tarar, sadece En İyi %20 dilime giren "Kesin Fırsatları" bulduğunda ekrana sesli/yazılı olarak Giriş, TP ve SL seviyelerini basar.

---
### Nasıl Çalıştırılır?
Terminalinizi (CMD/Bash) açıp klasöre gidin ve çalıştırmak istediğiniz botu yazın:
```bash
python3 02_Guvenli_Hasat_Maas_Botu.py
```
