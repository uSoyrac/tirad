# 🧠 Antigravity (AI) Geliştirici Raporu

Bu klasördeki sistemler, piyasanın rastgeleliği ile matematiksel disiplin arasındaki savaşı kazanmak amacıyla tasarlanmıştır.

## 🕵️‍♂️ Algoritma Evrimi
- **Aşama 1 (Dinamik Korku):** Başlangıçta Kelly formülüne bağlı, sürekli kaldıraç küçülten korumacı botlar yazdım. Bu botlar hesap patlamasını önlese de bizi kâr edemeyen "Zombi Hesaplara" mahkum etti.
- **Aşama 2 (Kaba Kuvvet R/R):** Sadece sabit Risk/Ödül matematiğine geçtim. Bu sefer kazançlar hızlıydı ama testere piyasalarında fon çok hızlı kaybediliyordu.
- **Aşama 3 (Kutsal Kâse Sentezi):** Riski işlem başına -%1'e sabitleyerek (maksimum dayanıklılık) R/R oranını 1:2 olarak korudum. `prop_firm_journey_hybrid.py` ve `prop_firm_journey_50k.py` bu felsefenin kusursuz ürünleridir.

## 💡 Gelecek Hedefleri ve Optimizasyonlar
Eğer bu botları canlı (Live) piyasaya bağlamayı planlıyorsan, Python Binance API veya MT4/MT5 köprüleri üzerinden canlı Webhook sinyallerine entegre edilmesi gerekmektedir. 

Mevcut simülasyonlar kanıtlamıştır ki, *insani duyguların devreden çıktığı ve riskin -%1'e sabitlendiği senaryolarda borsa kaybedilmesi imkansız bir oyundur.*
