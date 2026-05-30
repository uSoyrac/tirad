# TIRAD - AI Quantitative Crypto Trading Bot

Bu klasör (`uyg`), bir kullanıcının ve yapay zeka ajanının (Antigravity) birlikte "Sıfırdan" kurgulayıp kusursuzlaştırdığı eksiksiz bir algoritmik ticaret projesidir. Projenin çıkış noktası, Blackjack oyunundaki "Kart Sayma" prensibinin kripto vadeli işlemlere uyarlanmasıydı.

## Klasör Yapısı
*   `/AGENT.md` -> Projenin beyni. Hangi yanılgılara düştüğümüzü, 1H grafikten neden vazgeçtiğimizi, ML (Machine Learning) fikrine nasıl ulaştığımızı adım adım anlatan en önemli dosya. (Yeni bir AI ile çalışırken ilk bu dosyayı okutun).
*   `/docs/` -> Yapay zeka ile tartışmalarımız sonucunda ortaya çıkan resmi raporlar, simülasyon çıktıları ve gerçeklik kontrolü (Reality Check) belgeleri.
*   `/src/` -> 4H SMC analizini yapan, XGBoost veri setini çıkaran ve ORP (Optimize Risk Protocol) bileşik faiz hesaplamasını çalıştıran tüm Python kaynak kodlarımız.

## En Optimal Mimari (Zirve Noktası)
- **4H Grafik:** Komisyon ve kayma (slippage) erimesini önler.
- **Top 20 Coin:** Yüksek hacimli coinlerdeki "Order Block" saygısını kullanır (Yılda ~180 kaliteli işlem).
- **Limit Scale-In:** Market emir yasaktır. Emrin %50'si OB'nin üstüne, %50'si FVG orta noktasına atılır.
- **XGBoost AI:** Girilecek olan işlemin Olasılığını (Probability) ölçer, ihtimal >%60 ise işleme girer.
- **ORP (Bileşik Kasa):** Zararı bir sonraki işleme aktarır (Max %20 Cap). Win Rate yüksek (%65) olduğu için art arda kaybetmez, tek kârda zararları silip döngüyü kapatır.

Bu depo (repository), piyasa dinamiklerinin hayal ürünü varsayımlarla değil, acımasız matematik ve gerçeklik kontrolleriyle test edildiği nihai durumdur. Çalışmaya kaldığınız yerden devam edebilirsiniz.
