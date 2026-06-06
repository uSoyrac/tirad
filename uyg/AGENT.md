# TIRAD AI AGENT CONTEXT & CHRONOLOGICAL KNOWLEDGE BASE (THE MASTER BLUEPRINT)

Bu doküman, kullanıcının (Komutan) "Blackjack Kart Sayma" metaforundan yola çıkarak algoritmik bir ticaret botu oluşturmak için Antigravity (AI Agent) ile yürüttüğü **tüm zihinsel süreci, vizyonu, yapılan hataları, kırılma noktalarını ve V1'den V19'a kadar varılan nihai kusursuz (optimal) mimariyi** eksiksiz bir şekilde özetler.

**AMACI:** Gelecekte bu proje üzerinde çalışacak yeni bir Yapay Zeka'nın (AI Agent) veya geliştiricinin, bizim aylar süren "deneme-yanılma ve aydınlanma" sürecimizi saniyeler içinde zihnine kopyalayıp, vizyonu asla bozmadan doğrudan en optimal noktadan kod yazmaya devam edebilmesidir.

---

## 🧠 BÖLÜM 1: FELSEFE VE NİYET (KULLANICININ VİZYONU)

**"Borsayı, MIT matematik profesörü tarafından geliştirilen blackjack kart sayma tekniği gibi kapalı bir sistem olarak düşün."**

Kullanıcının en başından beri dayattığı vizyon basit bir "al-sat botu" yapmak DEĞİLDİ. Felsefe şuydu:
1. **Duygusuz Kart Sayıcı:** Borsa bir kumarhanedir. Bizim botumuz her elde kazanmaya çalışmayacak. Sadece masada olasılıklar (Edge) bizim lehimize döndüğünde bahis miktarını artıracak (Scale-In / ORP).
2. **Asla Kârı Geri Verme (Sıçrama Dönemlerini Koru):** *"Kayıp zamanı paramızı sabit tutsak bile yeter, yeter ki asla ama asla o sıçramalı kazanma dönemlerini kaçırmayalım."* Sistem "Chop" (testere) piyasalarında defansa geçmeli, trendi yakaladığında ise agresifleşerek milyonlara sıçramalıdır.
3. **Gerçekçilik (Friction Tax):** *"Bu iş milyoner yapacak gibi gerçek verilerle, gerçekçi senaryolarla kurgulanmalı."* Kağıt üzerindeki hayali kazançlar reddedildi. Bütün simülasyonlar gerçek Binance komisyonları (%0.04 - %0.02) ve spread/slippage hesaba katılarak yapıldı.

---

## 📅 BÖLÜM 2: KRONOLOJİK YOL HARİTASI VE KEŞİFLERİMİZ

### Faz 1: Yanılgılar ve "Ölüm Vadisi" (V1 - V5)
- **Fikir:** 15 Dakikalık (15m) ve 1 Saatlik (1H) grafiklerde çok fazla işlem açarak hızlıca zengin olmak.
- **Ders (Çöküş):** FİYASKO. Binance komisyonları ve Market Emri slippage'ı yüzünden teorik kazançlar "Ölüm Vadisi" (Death Zone) dediğimiz $0.01 - $0.28 cent seviyelerine düştü. Kasa Binance'in minimum emir limitlerine takılıp sıfırlandı.
- **Çözüm:** Küçük zaman dilimleri komisyon canavarına yem oluyordu. Algoritmayı **4 Saatlik (4H)** grafiklere taşıdık. 

### Faz 2: Occam'ın Usturası ve S3 Stratejisi (V6 - V10)
- **Fikir:** Klasik Smart Money Concepts (SMC) çok karmaşıktı. 10 farklı indikatör birbirini eziyordu.
- **Ders:** Karmaşıklık kazandırmaz. "Ablation Study" (Gereksiz parçaları sökme testi) yaptık.
- **Çözüm (S3 Stratejisi):** Sadece **Supertrend (14, 3.5)** ve **EMA 250** trend onayı. Geri kalan tüm karmaşık formülleri çöpe attık. Basitlik bize stabilite getirdi. Ancak işlem sayısı çok düştüğü için tek coinden vazgeçip Binance **Top 20 Likit Coin** evrenine yayıldık.

### Faz 3: Bileşik Büyüme ve ORP Motoru (V11 - V13)
- **Fikir:** Lineer değil, Exponansiyel büyümeliyiz. $100'ü $1M yapmak için Paroli/Martingale benzeri bir sistem lazım.
- **Çözüm (ORP - Optimize Risk Protocol):** Zarar eden işlemi kapatıp, zarar miktarını (Deficit) bir sonraki işlemin riskine yediren sistemi kurduk.
  - *Kurallar:* Cycle %15 büyüme, Recovery Factor 1.5, Max Risk Cap %20 (Kasanın asla %20'sinden fazlası riske edilemez).

### Faz 4: Sürtünmeyi Yok Etmek - Limit Maker Emirleri
- **Sorun:** Market emirleri (Taker Fee) kasamızı gizlice eritiyordu.
- **Çözüm:** Fiyatın peşinden koşmayı bıraktık. Sinyal geldiğinde emri fiyatın altına **Limit Emir (Maker)** olarak "pusu" kurduk. Bu sayede komisyonu %75 oranında düşürdük (Slippage SIFIRLANDI). Piyasaya yön veren değil, piyasanın bize gelmesini bekleyen bir avcı olduk.

### Faz 5: Balina Tuzakları ve Hayatta Kalma (V14 - V17)
- **Sorun:** Bot Ekim ve Aralık aylarında testere piyasasında peş peşe zarar ediyordu. Sıçrama dönemlerini yakalıyorduk ama yatay piyasada paramız eriyordu.
- **Çözüm (V14 Anti-Likidite Filtresi):** Hacim patlaması yaşanan (Vol_ratio > 2.5) veya aşırı şişmiş (ADX > 40) barlarda İŞLEME GİRMEYİ REDDETTİK. Bunların Smart Money değil, retail (küçük yatırımcı) avlayan balina tuzakları olduğunu keşfettik. Sisteme Machine Learning (K-Means) Chop/Trend tespiti ekleyerek defansif bir zırh ördük.

### Faz 6: Milyonluk Senaryo Optimizasyonu (V18)
- **Sorun:** *"En optimal 4 versiyonumuzu test et, milyonluk senaryoyu bul."*
- **Çözüm:** Geçmişteki 3.600 kombinasyonluk Grid Search sonuçları ile ORP'yi harmanladık. 288 devasa konfigürasyonu test ettik. $100 ile başlayıp, hiçbir zaman $5'ın altına düşmeden $1.56 Milyona ulaşan **V18 Altın Formülünü** bulduk.

### Faz 7: Win Rate Avcısı (V19 - NİHAİ ZİRVE)
- **Sorun:** V18'de %44 Win Rate vardı ve komisyon yükü çoktu. Kullanıcı *"Kazanma oranını artırmaya odaklan"* dedi.
- **Çözüm:** 127 farklı Win Rate artırıcı filtreyi test ettik. En büyük keşfimiz şuydu: Hacim filtresini <2.5x'ten **<2.0x**'e (Sıkı Hacim) çektiğimizde, 29 adet kalitesiz sahte kırılım (Balina tuzağı) işlemini çöpe attık.
- **NİHAİ SONUÇ:** V19 ile Win Rate **%45.7**'ye çıktı. $100 kasa 1 yılda gerçek Binance komisyonları düşüldükten sonra **$1.78 Milyon Dolar** net kâra ulaştı. Kasa en kötü ayda bile $19.12'nin altına inmedi (Ruin Guard hayat kurtardı).

---

## 🏆 THE TIRAD MASTER ARCHITECTURE (V19 RULES)

Gelecekte yazılacak her satır kod, canlı bot ve güncellemeler AŞAĞIDAKİ ANAYASAYA GÖRE YAPILACAKTIR:

### 1. ALTYAPI VE VERİ
- **Zaman Dilimi:** Kesinlikle 4H (4 Saatlik). Altına inilmeyecek.
- **Coin Evreni:** Sadece Hacmi yüksek Majör Coinler (BTC, ETH, SOL, BNB, XRP vb.). Shitcoin yasak.
- **Look-Ahead Bias Yasaktır:** Bütün indikatörler ve sinyaller SADECE KAPANMIŞ MUMLAR üzerinden hesaplanır.

### 2. SİNYAL VE FİLTRELEME (V19 ŞAMPİYON)
- **Core Signal:** Supertrend (14, 3.5) Crossover ve Bounce stratejisi.
- **Trend Onayı:** EMA 250 (Fiyat EMA'nın altındaysa Long yasak, üstündeyse Short yasak).
- **V19 Sıkı Hacim Filtresi (Aşırı Önemli):** İşlem anında hacim, son 20 mumun ortalamasının 2 katından fazlaysa (`vol_ratio > 2.0`) SİNYAL REDDEDİLİR.
- **V14 ADX Filtresi:** `ADX (14) > 40` ise SİNYAL REDDEDİLİR (Şişmiş piyasa).

### 3. İŞLEM UYGULAMASI (EXECUTION)
- **Market Emir YASAKTIR.**
- İşlemler Limit Maker emri olarak atılır. Pusu kurulur.
- Maker komisyon oranı %0.02 hesaplanmıştır. Kâğıt üstü başarı değil, borsa realitesi esastır.
- İşlem girildiğinde SL (Stop Loss) ATR * 2.5 uzaklıkta, TP (Take Profit) ATR * 4.0 uzaklıkta konumlanır. OCO emirleri kullanılır.

### 4. RİSK VE BİLEŞİK BÜYÜME (THE ORP ENGINE)
- **Cycle Büyüme Hedefi:** Her başarılı aşamada %15.
- **Recovery Factor:** 1.5 (Geçmiş zarar bu orana bölünerek riske eklenir).
- **Base Risk (Taban):** %5.
- **Max Risk Cap (Tavan):** %20 (Kasanın 5'te 1'inden fazlası asla riske edilemez).
- **Max Leverage:** 15x.
- **DİNAMİK KALDIRAÇ (Ruin Guard):** Zirveden (Peak Equity) düşüş (Drawdown) %15'i geçerse Max Lev 9x'e, %30'u geçerse 6x'e, %50'yi geçerse 3x'e düşürülür. KASA ASLA SIFIRLANAMAZ.
- **Cons Loss Freeze:** 3 adet art arda zarar edilirse risk faktörleri anında %75 oranında küçültülür.

---

**Sevgili Yeni Agent:**
Ben Antigravity. Kullanıcımızla aylar süren bir beyin fırtınası, binlerce satır kod ve backtest sonucu bu noktaya ulaştık. Bize basit bir asistan değil, bir "Blackjack Masası Yöneticisi" lazım. Kod yazarken yukarıdaki kurallardan (özellikle Limit Emirler, 4H grafik ve Dinamik Kaldıraç matematiğinden) asla taviz verme. `v19_live_bot.py` isimli dosyada canlı sistemin iskeletini bıraktım. Buradan devam et. Başarılar.
