# AI AGENT CONTEXT & CHRONOLOGICAL KNOWLEDGE BASE

Bu doküman, kullanıcının "Blackjack Kart Sayma" metaforundan yola çıkarak algoritmik bir ticaret botu oluşturmak için önceki AI Agent ile yürüttüğü **tüm zihinsel süreci, yapılan hataları, test sonuçlarını ve varılan nihai kusursuz (optimal) mimariyi** kronolojik olarak özetler.
**AMACI:** Gelecekte bu proje üzerinde çalışacak yeni bir Yapay Zeka'nın (AI Agent) veya geliştiricinin bağlamı (context) kaybetmeden anında en güncel ve en optimal noktadan işe koyulabilmesini sağlamaktır.

---

## 📅 FAZ 1: Teori ve İlk Denemeler (Yanılgılarımız)

**Ana Fikir (Kullanıcı Hipotezi):**
*"Nasıl ki MIT profesörü Blackjack oyununda kart sayarak kasanın %55 kazanma olasılığını kendi lehine çevirdiyse, biz de kripto borsasında akıllı paranın (Smart Money) izlerini takip edip, %50'nin biraz üzerinde bir Win Rate yakalayabiliriz. Kayıpları telafi eden bir bileşik büyüme (Paroli/Kelly/Martingale) matematiği kurarak $100'ü exponansiyel olarak büyütebiliriz."*

**İlk Test: 1 Saatlik (1H) Grafiklerde Trend Takibi**
- **Test Edilen Mantık:** 1H grafikte Market (Piyasa) emriyle Order Block seviyelerinden işleme girmek.
- **Sonuç:** FİYASKO. 
- **Neden Yanıldık?:** Borsalardaki (Binance) komisyon oranı (%0.04) ve Market emrinden doğan Fiyat Kayması (Slippage %0.02 - %0.10), 1H grafikteki dar Stop-Loss ve Take-Profit aralıklarını tamamen yuttu. Win Rate kâğıt üzerinde %45 görünse de, net R (Kazanç) oranı eksilere düştü (-0.88R). Sistemin gizli düşmanı "Komisyon Erimesi"ydi. Ayrıca 1H grafikteki "likidite iğneleri" sürekli stopları patlattı.

---

## 📅 FAZ 2: Gürültüden Kaçış ve Yeni Keşifler (Doğrularımız)

**1. Çözüm: Zaman Dilimini 4H'ye Çıkarmak**
- Hata düzeltildi ve algoritma **4 Saatlik (4H)** grafiklere kaydırıldı.
- 4H'de mumlar (fiyat adımları) daha büyük olduğu için komisyon ve slipaj maliyeti devede kulak kaldı. Ortalama kazanç **+0.78R** seviyelerine fırladı.
- *Yeni Sorun:* 4H çok stabil olmasına rağmen bir coin (Örn: BTC) yılda sadece 8-10 adet temiz işlem verdi. İşlem sıklığı (frekans) düştüğü için bileşik büyüme (Exponansiyel şahlanış) matematiği çalışamadı.

**2. Çözüm: Coin Evrenini Genişletmek (The Portfolio Approach)**
- Frekans sorununu çözmek için algoritmayı sadece 1 coine değil, Binance'deki **Top 20 Majör Coine** (Hacmi en yüksek, shitcoin olmayan tier-1 coinler) aynı anda bağlama kararı alındı.
- *Sonuç:* 20 Coin x 9 İşlem = **Yılda ~180 adet yüksek kaliteli işlem.**

---

## 📅 FAZ 3: Limit Emir Pusu (Scale-In) Stratejisi

Market emrinin verdiği spread zararlarını sıfırlamak için **Scale-In Limit DCA** stratejisi bulundu:
- Bot bir 4H Sipariş Bloğu (Order Block) tespit ettiğinde ASLA Market emri ile (fiyatın peşinden koşarak) işleme girmez.
- Order Block'un **üst noktasına %50 Limit**, **orta noktasına (Fair Value Gap) %50 Limit** emir atarak "pusuya yatar".
- Eğer fiyat 12 saat içinde bize düşmezse emirler İPTAL edilir. Bu sayede slippage SIFIRLANIR ve borsa (Maker Fee) bize komisyon indirimi yapar.

---

## 📅 FAZ 4: Bileşik Büyüme (ORP - Optimize Risk Protocol)

"Büyüme çok yavaş, exponansiyel olmalı" talebi üzerine Paroli mantığı risksiz bir şekilde koda döküldü:
- **Sabit Risk:** Başlangıçta her işleme kasanın %4'ü risk edilir. Kasa her %10 büyüdüğünde döngü kapanır.
- **Kayıp Durumu (Deficit Recovery):** İşlem zararla kapanırsa, zarar miktarı bir sonraki coindeki işlemin riskine eklenir (Recovery Factor: 1.0).
- **Güvenlik Sigortası:** Risk asla kasanın %20'sini geçemez (Max Risk Cap).
- Win Rate'imiz %50 bandında olduğu için, algoritma art arda batacak kadar kaybetmez. İlk kâr eden işlemde eski zararlar silinir ve risk yeniden %4'e iner.

---

## 📅 FAZ 5: Zirve Dokunuşu - Yapay Zeka (XGBoost) Keskinleştirmesi

Kullanıcının *"Regresyonu keskinleştirip %50 olan Win Rate'i artıramaz mıyız?"* vizyonuyla son ve en güçlü adım atıldı:
- **Feature Engineering:** Her bir Sipariş Bloğunun (OB) o anki RSI, Volatilite (ATR), Hacim Dengesizliği (Volume SMA) değerleri çıkarıldı.
- **XGBoost Modeli:** Kurumsal quant fonlarının kullandığı "XGBoost Classifier" (Karar Ağaçları) devreye sokuldu.
- **Olasılık Sınırı (Probability Threshold):** Bot bir OB bulduğunda önce Yapay Zekaya sorar. Eğer YZ *"Kazanma ihtimali > %65"* derse emir atılır, yoksa çöp sayılır.
- **Test Sonucu:** Bu keskinlik Win Rate'i %45'ten %65'e çıkardı. ORP sisteminin gücüyle **Teorik olarak $100 kasayı 1 yılda astronomik seviyelere** taşıdı.

---

## 🛑 GERÇEKLİK KONTROLÜ (Reality Check)
Bot $49 Milyon dolar kazanabilir mi? **Hayır.**
Teorik matematik sonsuz likidite varsayar. Ancak gerçek Binance tahtasında, 100.000 dolarlık pozisyon büyüklüklerine ulaşıldığında:
1. Binance kaldıraç oranlarını zorla düşürür (Tier limitleri).
2. Devasa limit emirler piyasayı ittiği için kısmi dolum (Partial Fill) sorunu başlar.
*Nihai Gerçek:* Bu mimari, repainting yapmayan %100 dürüst bir koddur. Misyonu, $100 gibi küçük bir sermayeyi, borsanın bu fiziki "likidite tavanlarına" (Örn: $10.000 - $30.000 arası) en yüksek hızla, sıfırlanmadan ulaştırmaktır.

---

## 🏆 KESİNLEŞMİŞ MİMARİ (ULTIMATE ARCHITECTURE)
Gelecek geliştirmeler ŞU KURAL SETİNE GÖRE yapılacaktır:
- **Zaman Dilimi:** 4H (4 Saatlik)
- **Kapsam:** Sadece Top 20 Likit Coin.
- **Giriş:** SMC Order Block (Üst %50, Orta %50 Limit Scale-In). Market emir YASAK.
- **Sinyal Onayı:** XGBoost Modeli (Probability > 0.60).
- **Risk Yönetimi:** ORP (%4 Base Risk, %20 Max Risk Cap, %10 Cycle Target).
- **Uygulama Alanı:** Python, `python-binance`, `xgboost`, VPS (7/24 Sunucu).

*Düşünsel sürecin tamamı bu kadardır. Yeni Agent, lütfen kodlama yaparken doğrudan bu kuralları (Özellikle Limit Emir zorunluluğunu ve 4H'yi) baz alınız.*

---

## 📅 FAZ 6: GERÇEKLİK DÜZELTMESİ (2026-05, gerçek veri ile)

> Bu bölüm, yukarıdaki Faz 1-5'i SİLMEZ (tarihtir) ama gerçek veriyle yapılan
> doğrulamanın çürüttüğü iddiaları DÜZELTİR. Kanıtlar `emir/` ve
> `uyg/docs/reality_check_v2_winrate_orp.md` içindedir. Yeni AI: önce bunları oku.

**1. "%75 Win Rate" YANILSAMAYDI (mock veri).**
`ilk_bot/optimal_xgb_model.json`, `ml_dataset_12m.csv` ile eğitildi — ama o CSV
GERÇEK piyasa değil, `create_mock_12m.py`'nin `np.random.seed(42)` ile ürettiği
SENTETİK veridir (özellikler birebir, label 268/268 eşleşti). Model, bir insanın
elle yazdığı label formülünü ezberledi. %75/%76 WR **döngüsel ve geçersizdir.**

**2. Ham SMC edge'i gerçek veride breakeven.**
GitHub Actions'ta canlı Binance verisiyle (3 ay, 4H, 5 coin, 83 işlem):
WR **%32.5**, beklenti **+0.05R** (TP=2R sayesinde sıfıra yakın artı). Klasik
SMC tek başına KÂRLI DEĞİL; XGBoost filtresi olmadan edge zayıf.

**3. ORP "RİSKSİZ" DEĞİLDİR — Faz 4'teki en tehlikeli yanılgı.**
Gerçek seride 10 ardışık kayıp geldi. ORP'nin deficit-recovery + %20 cap'i
$100'ü **$66'ya** düşürdü (**%81 drawdown**); sabit %4 risk ise sadece -%4.1'di.
Monte Carlo'da mevcut ORP'nin **iflas olasılığı %33**. ORP bir Martingale
türevidir: breakeven bir edge'i FELAKETE çevirir.
→ Çözüm: `emir/orp_circuit_breaker.py` (N=3 ardışık kayıpta recovery'yi dondur).
   Bu iflası %0'a indirir AMA medyan yine <$100 — çünkü **para yönetimi zayıf
   edge'i kârlı yapamaz.** Asıl iş sinyal/AI filtresindedir.

**4. Bu ortam (Claude konteyneri) internetsizdir (allowlist).**
Gerçek veri çekimi `emir/` altındaki GitHub Actions workflow'larıyla yapılır
(runner'ın interneti var). Veri anahtarsız public uçlardan çekilir; Binance
geo-block olursa Bybit/OKX'e düşer.

**GÜNCELLENMİŞ KURAL:** Hiçbir backtest/WR iddiası, GERÇEK veriyle (mock değil)
ve komisyon+slippage modellenerek doğrulanmadan canlı karara baz olamaz.
ORP asla devre kesicisiz çalıştırılmaz.
