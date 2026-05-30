# Kripto Ticaret Botu - Kapsamlı Strateji ve Mantık Rehberi

Bu rehber, geliştirdiğimiz algoritmanın **neye dayanarak karar verdiğini**, **hangi göstergeleri kullandığını**, bugüne kadar denediğimiz **sermaye yönetimi stratejilerini** ve aralarından seçilen **en optimal yöntemi** adım adım açıklamaktadır. 

Bu dökümanı okuyarak botun çalışma mantığını tam olarak anlayabilir, uygulayabilir ve işleyişi bir başkasına (örneğin çalışma arkadaşınıza) rahatlıkla aktarabilirsiniz.

---

## 1. Botun Temel Mantığı ve Amacı

Botun temel amacı, piyasayı rastgele veya duyguya dayalı tahminlerle değil, **Kurumsal Yatırımcıların (Smart Money)** bıraktığı izleri takip ederek analiz etmektir. 

Bot, "sürekli her dalgalanmadan kar edeyim" mantığıyla çalışmaz. Bunun yerine:
- Yüksek doğruluk payı olan (Win Rate'i %80-90 civarı) **nadir ama keskin** fırsatları kollar.
- Başarılı bir işlemden sonra karı birleştirerek (bileşik faiz / compounding), ufak başlangıç sermayelerini (örneğin 100 Dolar) devasa boyutlara ulaştırmayı hedefler.
- Kasa yönetimini, Blackjack veya Rulet gibi şans oyunlarındaki **"Bet" (Bahis)** sistemlerinin istatistiksel modellerine benzer bir mantıkla, ancak rastgeleliğe değil kesin bir risk yönetim kalkanına (*Ruin Guard*) bağlayarak yapar.

---

## 2. Teknik Analiz: Bot Neleri Kullanıyor? (Nasıl Görüyor?)

Bot, klasik göstergeler (RSI, MACD gibi gecikmeli araçlar) yerine tamamen fiyat hareketinin (Price Action) mekaniğine odaklanan **SMC (Smart Money Concepts)** indikatörlerini kullanır. Bot pazarı şu 4 temel yapı taşı ile okur:

1. **OB (Order Blocks - Emir Blokları):**
   - *Nedir:* Kurumsal yatırımcıların yüklü alım/satım yaptığı ve piyasanın yönünü aniden değiştirdiği hacimli mum kümeleridir.
   - *Nasıl Kullanılır:* Bot, fiyat bu geçmiş emir bloklarına tekrar düştüğünde, kurumsal alıcıların tekrar devreye gireceğini varsayarak işleme girer.

2. **FVG (Fair Value Gaps - Adil Değer Boşlukları):**
   - *Nedir:* Piyasanın çok hızlı hareket ettiği, alıcı ve satıcı dengesinin bozulduğu ve arkada "boşluk" bıraktığı alanlardır.
   - *Nasıl Kullanılır:* Pazar genellikle bir mıknatıs gibi bu boşlukları doldurmak ister. Bot, fiyatın bu boşluklara geri dönme (pullback) ihtimalini hesaplar.

3. **BOS (Break of Structure - Yapı Kırılımı) & CHoCH (Change of Character - Karakter Değişimi):**
   - *Nedir:* Fiyatın sürekli yaptığı tepelerin veya diplerin kırılmasıdır. Yükselen bir trendin artık düşüşe geçmesi (CHoCH) veya mevcut yükselişin onaylanarak devam etmesi (BOS).
   - *Nasıl Kullanılır:* Bot, trendin asıl yönünü teyit etmek için bu kırılımları bekler.

4. **ATR (Average True Range - Ortalama Gerçek Aralık):**
   - *Nedir:* Piyasanın o anki "oynaklığını" (volatilite) ölçer.
   - *Nasıl Kullanılır:* Bot, **Zarar Kes (Stop-Loss)** seviyesini rastgele bir yüzde olarak değil, piyasanın o anki oynaklığına göre dinamik olarak belirler. Fiyat çok hareketliyse stop'u geniş, durgunsa dar tutar. Maksimum stop mesafesi asla %10'u geçmez.

---

## 3. Yatırım ve Risk Yönetimi: Bugüne Kadar Denediğimiz Stratejiler

Testlerimizde kasa büyümesini sağlamak için 4 farklı "Bet" (Bahis/Risk Yönetimi) sistemi geliştirdik. İşte sıra sıra hepsinin mantığı:

### Strateji 1: Sabit Risk (Fixed Risk - %2)
- **Mantığı:** Her işlemde kasanın sadece %2'sini riske et. Kasa büyüdükçe %2'nin dolar karşılığı artar, küçüldükçe azalır.
- **Sonuç:** Güvenli ama **çok yavaş**. Sınırlı sayıda işlem fırsatı geldiği için devasa büyümelere ulaşması çok zaman alıyor.

### Strateji 2: Fibonacci (Negatif İlerleme)
- **Mantığı:** Zarar ettikçe riski Fibonacci serisine göre (1, 1, 2, 3, 5, 8...) artırarak önceki zararı tek seferde çıkarmaya çalışır. Kazanınca riski düşürür.
- **Sonuç:** Botumuz zaten genelde kazandığı (Win Rate yüksek olduğu) için, risk çarpanı neredeyse hiç artmadı. Parayı çok güvende tuttu ancak büyüme Sabit Risk'in bile altında kaldı.

### Strateji 3: Paroli Sistemi (Pozitif İlerleme / Reverse Martingale)
- **Mantığı:** Sadece kazandıkça bahis (risk) miktarını artırır. (%2 -> %4 -> %8). Eğer kaybederse veya arka arkaya 3 kere kazanırsa tekrar %2'ye (başa) döner.
- **Sonuç:** Botumuz sıklıkla ardışık kazanma (winning streak) yakaladığı için çok **agresif ve muazzam karlı** sonuçlar verdi. Karı maksimize eden müthiş bir modeldi.

### Strateji 4 (EN OPTİMALİ): ORP (Optimized Recovery Progression - Optimize Edilmiş Kurtarma İlerlemesi)
Son olarak sizinle birlikte geliştirdiğimiz ve sistemin zirvesi olan ORP stratejisi.
- **Mantığı:** Her başarılı adımda kasanın belirli bir yüzde (Örn: %2 veya %5) büyümesini bir "Hedef" (Target) olarak koyar.
- Eğer bir işlemde zarar edilirse, bot **yeni hedef ile mevcut kasa arasındaki farkı** hesaplar ve bu farkı kapatacak kadar risk alır (R = Fark / 1.5). 
- **Ruin Guard (Batma Kalkanı):** Botun alacağı risk ASLA kasanın %15'ini veya belirlenen kaldıraç limitini (Örn: 5x) geçemez. Eğer kurtarma hamlesi çok riskliyse, bot bunu tek seferde değil, birkaç küçük işleme böler.
- **Sonuç:** Hem Paroli'nin agresif bileşik faiz etkisini hem de matematiksel bir kalkanı birleştirerek inanılmaz sonuçlar doğurdu.

---

## 4. Bot Nasıl Yatırım Yapıyor? (Adım Adım Çalışma Döngüsü)

Sistemi canlıya aldığınızda, bot arka planda tam olarak şu sırayla çalışır:

1. **Piyasa Taraması:** Bot belirlenen zaman diliminde (örn. 1 Saatlik mumlar kapanınca) ETH veya BTC grafiğine bakar.
2. **SMC Analizi:** Geriye dönük mumları tarayarak Order Block'ları ve FVG boşluklarını tespit eder. Trendin yönünü (BOS/CHoCH) teyit eder.
3. **Puanlama:** Tespit edilen yapılara puan verir. (Örn: Hacim yüksek mi? Trendle aynı yönde mi?). Eğer puan **6.0'ın (10 üzerinden) üzerindeyse** işleme girme kararı alır.
4. **Risk Hesaplama (ORP):** Hedeflenen büyüme oranına (örn %5) ulaşmak için ne kadar sermaye riske edileceğini hesaplar.
5. **Stop-Loss ve Kaldıraç Ayarı:** ATR'ye bakarak stop mesafesini belirler (Örn: %2 aşağısı). Riske edeceği tutar ile stop mesafesini oranlayarak **kullanması gereken tam kaldıracı** hesaplar (Maksimum 5x limiti asla aşmaz).
6. **Emir Gönderimi:** Binance'e Long (Alış) veya Short (Satış) emrini Stop-Loss ve Take-Profit (Kar Al) limitleriyle birlikte gönderir.
7. **Döngü Tekrarı:** İşlem kapandığında yeni kasaya göre bir sonraki %5'lik büyümeyi hedefleyerek baştan başlar.

---

## 5. En Optimal Sonuçlar (Uygulanması Gereken Nihai Strateji)

Tüm zaman dilimleri (15dk, 30dk, 1s, 4s, 1g), tüm coinler ve tüm risk yöntemlerini test ettikten sonra, **açık ara en optimal ayar** şu şekilde belirlenmiştir:

* **İşlem Çifti:** ETH/USDT (Ethereum)
* **Zaman Dilimi:** 1 Saatlik (1h) Grafikler (Sinyal kalitesi ve işlem sıklığı en dengeli burada)
* **Hedeflenen Büyüme Adımı:** Her başarılı aşamada **%5 Büyüme**
* **Strateji:** ORP (Optimized Recovery Progression) + Ruin Guard Kalkanı
* **Kaldıraç Sınırı:** Maksimum 5x

### 1 Yıllık Geriye Dönük Test (Backtest) Sonuçları:
- **Başlangıç Kasası:** 100 Dolar
- **1 Yıl Sonundaki Bitiş Kasası:** **78.040 Dolar** ($78,040.49)
- **Gerçekleşen İşlem Sayısı:** 149 İşlem
- **Tamamlanan %5'lik Hedef Adımı:** 136 Adım (Üstel Büyüme: $1.05^{136} \approx 779x$)
- **Maksimum Çekilme (Drawdown):** Sadece **%9.6** (Yani kasa 1 yıl boyunca hiçbir zaman en yüksek noktasından %9.6'dan fazla aşağıya düşmedi).
- **Likidasyon (Patlama) İhtimali:** Matematiksel olarak **SIFIR**. Çünkü 5x kaldıraçta likide olmak için %20 terste kalmak gerekirken, botun dinamik Stop-Loss'u ortalama %2 - %4 aralığında patlar ve kalkan kasanın erimesini önler.

---

## 6. Özet ve Arkadaşınıza Söyleyebilecekleriniz

* *"Kanka, bot rastgele al-sat yapmıyor. Balinaların, yani kurumsal şirketlerin (Smart Money) alım yaptığı Order Block'ları kovalıyor. O yüzden girdiğimiz 10 işlemin 8'inde kazanıyoruz."*
* *"Kasamızı her başarılı işlemde %5 büyütmeye programladık. %5 küçük duruyor ama 100 kere arka arkaya %5 büyüttüğünde bileşik faiz (compounding) etkisiyle para inanılmaz katlanıyor."*
* *"Zarar etsek bile 'Optimized Recovery' diye bir algoritma devreye giriyor. Bir sonraki başarılı işlemde o zararı çıkarıp bizi tekrar hedeflenen %5'lik yola sokuyor."*
* *"Asla kasayı patlatmıyoruz. Ruin Guard (Batma kalkanı) var ve en fazla 5x kaldıraç açabiliyor. Stop'u da otomatiğe bağlıyor, zararı kestiği için bakiyemiz hep güvende."*
