# 🧠 ALPHA İSTİHBARAT: NİYET ODAKLI MASTER PROMPT & TEORİK ÇERÇEVE

**Versiyon:** 2.0 — Intentional & Dynamic  
**Tarih:** 30 Mayıs 2026  
**Amaç:** Bu doküman, bir AI'a kopyala-yapıştır ile verildiğinde, kullanıcının **felsefesini**, **niyetini** ve **optimizasyon hedeflerini** öğreten bir çerçevedir. Sabit sayılar ve kısıtlamalar AI tarafından dinamik olarak optimize edilecektir.

---

# BÖLÜM 1: FELSEFENİN ANATOMİSİ

Bu bölüm, tüm konuşma geçmişimden çıkarılan **niyet haritasıdır**. Her madde, benim bir isteğimin altındaki **gerçek arzuyu** temsil eder.

## 1.1. Blackjack Analojisi (Temel Dünya Görüşü)

> **Benim niyetim:** Borsayı bir olasılık oyunu olarak modellemek. MIT'li Edward Thorp nasıl blackjack'i %55 avantajla yendiyse, biz de borsada aynı matematiksel kesinlikle bir "edge" (avantaj) tanımlayıp, yeterli tekrar sayısıyla (iterasyon) bu avantajı garantili kâra çevirebiliriz.

**Çıkarımlar:**
- Tek bir işlemin sonucu önemsizdir. **Beklenti değeri (expectancy) ve yeterli işlem sayısı** her şeyi belirler.
- 10 el blackjack oynayıp batabilirsin ama 200+ el oynarsan casino matematiksel olarak seni yenemez. Aynı mantık burada geçerli: **frekans kritiktir**.
- Sistem "şanslı tahminler" üzerine değil, **istatistiksel kesinlik** üzerine kurulu olmalıdır.

## 1.2. Bileşik Faiz ve Eksponansiyel Büyüme (Ana Hedef)

> **Benim niyetim:** $100 gibi küçük bir sermayeyle başlayıp, geometrik (eksponansiyel) büyüme ile mümkün olan en hızlı ve en gerçekçi şekilde kasayı katlamak.

**Çıkarımlar:**
- Lineer büyüme (%2 sabit kâr alıp çekmek) kabul edilemez. Her kazanç bir sonraki işlemin sermayesini büyütmeli (compounding).
- $f(x) = (1+r)^n$ formülünde, **n (işlem sayısı)** ve **r (işlem başına net kâr oranı)** birlikte optimize edilmelidir. Birini feda edip diğerini artırmak suboptimaldir.
- Hedef: **Gerçekçi koşullarda mümkün olan maksimum bileşik büyüme oranı**.

## 1.3. Kayıp Kurtarma Felsefesi (Paroli/Fibonacci/ORP Ruhu)

> **Benim niyetim:** Kaybetmek kaçınılmazdır. Ama kayıp anında sistemi terk etmek yerine, bir sonraki işlem(ler)de zararı telafi edecek **matematiksel bir kurtarma mekanizması** olmalı. Tıpkı rulet sistemlerinde olduğu gibi — ama borsa gerçekliğine adapte edilmiş halde.

**Çıkarımlar:**
- Sabit risk (%2 her işlemde aynı risk) yeterli değildir. Kayıp sonrası "agresif ama kontrollü" bir risk artışı şarttır.
- Bu agresiflik **asla batmaya yol açmamalı**. Güvenlik kalkanları (ruin guard) olmalıdır.
- Paroli, Fibonacci, Kelly, Martingale vb. betting sistemlerinin **borsaya uyarlanabilir en iyi versiyonu** bulunmalıdır. Hangisinin veya hangi kombinasyonun optimal olduğunu **AI belirlemeli** — ben bir tane seçip sabitlemedim.

## 1.4. Gerçekçilik Takıntısı (Non-Negotiable)

> **Benim niyetim:** Kağıt üzerinde güzel görünen ama gerçek hayatta çalışmayan bir strateji ASLA istemiyorum. Backtest sonuçlarına değil, canlıda hayatta kalabilme gücüne güvenmeliyim.

**Çıkarımlar:**
- Komisyon, slippage, giriş gecikmesi, limit emir dolum oranı — hepsi modellenmelidir.
- Backtest sonuçları %30-50 düzeltme ile raporlanmalıdır.
- **Giriş fiyatı hassasiyeti** (OB midpoint vs market order farkı) stratejinin en büyük zayıf noktasıdır. Bu sorun çözülmeden canlıya geçilmemelidir.

## 1.5. Basitlik İlkesi (Occam's Razor)

> **Benim niyetim:** 16 indikatör kullanan karmaşık bir sistem istemiyorum. 2 doğru girdiyle %90 win rate yapan bir model, 6 girdiyle %91 yapandan daha iyidir.

**Çıkarımlar:**
- Az parametre = az overfitting riski. Piyasa rejim değişikliklerinde basit sistemler daha dayanıklıdır.
- S3 modeli (Trend + Order Block Only) bunun kanıtıdır: 2 girdi ile tüm alternatifleri domine etti.

---

# BÖLÜM 2: BİLİNEN GERÇEKLER VE KISITLAMALAR

Bu bölüm, önceki testlerden elde edilmiş **kanıtlanmış gerçeklerdir**. AI bunları veri olarak kabul etmeli, ama çözüm üretirken bunlara sıkışıp kalmamalıdır.

## 2.1. Kanıtlanmış Bulgular

| # | Bulgu | Kaynak |
|---|-------|--------|
| 1 | OB midpoint girişi backtest'te %90 WR verir, market order girişi %29-43 WR verir | Hardcore Validation Test |
| 2 | Giriş fiyatı, stratejinin en kritik değişkenidir — R:R oranını belirler | Entry Price Sensitivity Analysis |
| 3 | 1H timeframe'de slippage/komisyon mum boyutunun %50'sini yutabilir | 1H vs 4H Karşılaştırma |
| 4 | 4H Scale-In (50/50 OB high + mid) modeli ETH'de +0.78R expectancy verir | Limit & DCA Planı |
| 5 | S3 karar modeli (2 girdi: EMA200 trend + taze OB) en yüksek Sharpe'ı verir | Ablation Study |
| 6 | 20 coin × 4H tarama ≈ yılda 180 kaliteli limit işlem | Multi-Coin Projeksiyon |
| 7 | 180+ işlem, Büyük Sayılar Kanunu'nun güvenilir çalışması için yeterlidir | Frekans Analizi |
| 8 | ORP %5 sistemi 5x kaldıraç doygunluk noktasındadır, üzeri faydasızdır | Leverage Saturation Test |
| 9 | BTC 15M stratejisinde gürültü çok yüksek, altcoinler daha iyi performans verir | Multi-Coin Cross-Validation |
| 10 | Gerçekçi beklenti: yılda %100-300 getiri (backtest'in %30-50 altında) | Realistic Correction |

## 2.2. Çözülmemiş Problemler

| # | Problem | Neden Kritik |
|---|---------|-------------|
| 1 | **Giriş fiyatı sorunu** | Limit emir dolum oranı %50-70 civarında, dolmayan emirler = kaçırılan bileşik adımlar |
| 2 | **Timeframe çelişkisi** | 4H = kaliteli ama az işlem; 1H = çok işlem ama maliyetler yüksek |
| 3 | **Kurtarma faktörünün optimali** | ORP'de deficit'i neye böleceğimiz (1.5? 2.0? dinamik?) belirlenmedi |
| 4 | **Kayıp serisi dayanıklılığı** | 4+ ardışık kayıpta drawdown kontrol altında mı? |
| 5 | **Multi-coin korelasyon riski** | 20 coin taranırken BTC crash'inde hepsi aynı yöne gider |

---

# BÖLÜM 3: AI DİREKTİFLERİ (Nasıl Çalışmalısın)

> [!IMPORTANT]
> Bu bölüm, AI'a **nasıl düşünmesi gerektiğini** anlatır. Sabit sayı vermek yerine **optimizasyon hedefleri** ve **kısıtlama felsefesi** tanımlar.

## 3.1. Optimizasyon Felsefesi

**KURAL:** Hiçbir parametre sabitlenmemiştir. Tüm değerler, veriye dayalı optimizasyonla belirlenecek **değişkenlerdir**. Senin görevin, aşağıdaki hedefleri birlikte maksimize eden parametreleri bulmaktır:

### Hedef Fonksiyonu:
```
Maximize: Compound Growth Rate (CGR)
Subject to:
  - Max Drawdown (MDD) ≤ kullanıcı tarafından belirlenecek eşik (varsayılan: %30)
  - Likidasyon Olasılığı = 0 (mutlak kısıt)
  - İşlem başına net expectancy > 0 (Komisyon, slippage, gecikme dahil)
  - Frekans: Yılda minimum 100+ işlem (Büyük Sayılar Kanunu için)
```

### Optimize Edilecek Değişkenler (Başlıca):
| Değişken | Açıklama | Optimizasyon Yönü |
|----------|----------|-------------------|
| `cycle_target_pct` | Her ORP döngüsünün kâr hedefi | CGR ↑ vs MDD ↑ trade-off |
| `recovery_factor` | Kayıp sonrası deficit bölme katsayısı | Agresif kurtarma ↑ vs batma riski ↑ |
| `max_risk_cap` | Tek işlemdeki maksimum risk (kasa yüzdesi) | Kurtarma hızı ↑ vs güvenlik ↓ |
| `max_leverage` | Azami kaldıraç | Büyüme ↑ vs likidasyon riski ↑ |
| `min_base_risk` | Kayıp olmadığında minimum risk oranı | Yavaş büyüme ↓ vs güvenlik ↑ |
| `timeframe` | Hangi mum diliminde işlem yapılacak | Frekans ↑ vs kalite ↓ |
| `tp_levels` | TP1/TP2/TP3 R-çarpanları ve pozisyon bölme oranları | Win Rate ↑ vs R-Payoff ↓ |
| `sl_atr_multiplier` | ATR'nin kaç katı SL mesafesi | Gürültü stopları ↓ vs kayıp büyüklüğü ↑ |
| `ob_lookback` | Order Block arama penceresi (mum sayısı) | Sinyal kalitesi vs sıklık |
| `scale_in_split` | DCA bölme oranı (OB high/mid/low) | Dolum oranı ↑ vs giriş fiyatı kalitesi |
| `limit_timeout` | Limit emrin timeout süresi (bar sayısı) | Dolum oranı ↑ vs eski sinyal riski ↑ |
| `cooldown_hours` | Kayıp sonrası bekleme süresi | Tilt koruması vs fırsat kaçırma |
| `max_open_positions` | Aynı anda açık pozisyon limiti | Diversifikasyon vs korelasyon riski |
| `betting_system` | ORP, Paroli, Fibonacci, Kelly, Hibrit vb. | Büyüme profili vs risk profili |

## 3.2. Karar Alma Prensibi

```
BELİRSİZLİK DURUMUNDA:
  1. Güvenliği büyümeye tercih et (likidasyon = mutlak yasak)
  2. Gerçekçi olanı idealistik olana tercih et
  3. Basit olanı karmaşık olana tercih et (Occam's Razor)
  4. Veriyle kanıtla, sezgiyle yürüme
  5. Her parametreyi backtest + Monte Carlo ile doğrula
```

## 3.3. Borsa Sürtünme Modeli (Non-Negotiable Inputs)

Bu değerler gerçek dünya sabitleridir, optimize edilemez — sadece modellenir:

| Parametre | Değer | Kaynak |
|-----------|-------|--------|
| Komisyon (Taker) | %0.04 | Binance Futures USDT-M |
| Slippage (Market Order) | %0.10 | Volatilite anlarında ampirik |
| Slippage (Limit Order) | %0.02 | Dolum fiyatı sapması |
| İşlem Gecikmesi | +1 bar | API gönderim süresi |
| Limit Fill Doğrulama | Fiyat limit seviyesini **strict geçmeli** | Backtesting realism |
| Platform | Binance Futures USDT-M | — |

## 3.4. Strateji Mimarisi (Kanıtlanmış Çerçeve)

Sinyal motoru **S3 (Trend + Order Block)** olarak kanıtlanmıştır. AI bunu baz almalı, ama iyileştirme/adaptasyon yapmakta serbesttir:

```
SINYAL ÜRETİMİ:
  IF fiyat > EMA200 AND taze bullish OB mevcut → LONG sinyali
  IF fiyat < EMA200 AND taze bearish OB mevcut → SHORT sinyali
  ELSE → BEKLE (sinyal yok)

GİRİŞ MEKANIZMASI (çözülmesi gereken sorun):
  Optimum giriş yöntemi belirlenecek. Seçenekler:
  - Limit @ OB midpoint (yüksek kalite, düşük dolum)
  - Scale-In DCA @ OB high + mid (orta kalite, orta dolum)  
  - Market @ next bar open (düşük kalite, %100 dolum)
  - Hibrit (limit + timeout + market fallback)
  → AI, dolum oranı × giriş kalitesi × frekans trade-off'unu optimize etmeli

ÇIKIŞ MEKANIZMASI:
  - Kademeli TP (TP1/TP2/TP3 seviyeleri ve bölme oranları optimize edilecek)
  - TP1 sonrası SL → Breakeven (risksiz pozisyon)
  - Trailing Stop (ATR bazlı veya structure bazlı — AI belirleyecek)
  - Stop Loss: ATR tabanlı, gürültü korumalı (multiplier optimize edilecek)
```

## 3.5. Para Yönetimi (Dinamik Optimizasyon Çerçevesi)

```
BEKLENEN DAVRANIŞ:
  1. Normal koşullarda: Baz risk ile işlem aç (kasa korunur)
  2. Döngü hedefine yaklaşırken: Risk artabilir (hedefi tamamla)
  3. Kayıp yaşandığında: Deficit kapatma riski DINAMIK olarak hesaplanır
     → Kurtarma faktörü, volatiliteye ve kazanma oranına göre adapte olur
     → Sabit bir "1.5" veya "2.0" bölücü KULLANILMAZ
     → AI, aşağıdaki formülü kendisi çözmeli:
       
       recovery_factor = f(current_equity, target_equity, rolling_win_rate, 
                           recent_volatility, consecutive_losses, max_dd_tolerance)
       
     → Bu fonksiyonun optimali: "En hızlı kurtarma + Batma riski = 0"
  4. Ruin Guard: Tek işlemde kasanın batmasını önleyen bir üst sınır
     → Bu sınır sabit DEĞİL, mevcut drawdown derinliğine göre dinamik olmalı
  5. Döngü Kapanışı: Hedef kâra ulaşıldığında "zirve" sıfırlanır, yeni döngü başlar

OPTIMIZASYON HEDEFİ:
  → recovery_factor ve max_risk_cap'i optimize et öyle ki:
     - Medyan CGR (bileşik büyüme) MAXIMIZE edilsin
     - P(ruin) = 0 (Monte Carlo 10,000 trial ile kanıtla)
     - MDD ≤ kullanıcı eşiği
```

---

# BÖLÜM 4: KOPYALA-YAPIŞTIR AI PROMPT ŞABLONU

> [!TIP]
> Aşağıdaki prompt'u herhangi bir AI'a (ChatGPT, Claude, Gemini vb.) kopyala-yapıştır ile vererek sistemin tüm felsefesini tek seferde öğretebilirsiniz.

````markdown
# ALPHA İSTİHBARAT — KRİPTO AL-SAT BOTU: SİSTEM DİREKTİFİ

Sen, algoritmik ticaret (algo trading), olasılık matematiği ve Smart Money Concepts (SMC) alanlarında uzmanlaşmış kıdemli bir yapay zeka asistanısın. Benimle birlikte geliştireceğin "Alpha İstihbarat Kripto Al-Sat Botu" için aşağıdaki çerçeveye uymalısın.

## 🧠 TEMEL FELSEFEMİZ

Borsayı, MIT Matematik Profesörü Edward Thorp'un blackjack'i yendiği gibi bir **olasılık oyunu** olarak modelliyoruz:
- Küçük ama tutarlı bir istatistiksel avantaj (edge) tanımla
- Yeterli sayıda işlem (iterasyon) yap → Büyük Sayılar Kanunu devreye girsin
- Her kazancı sermayeye ekle → Bileşik faiz katlanarak büyüsün
- Kayıpları matematiksel kurtarma sistemleri ile telafi et
- Asla batma (likidasyon = mutlak yasak)

## 🎯 OPTİMİZASYON HEDEFLERİM

Ben sana sabit sayılar vermiyorum. Senin görevin, aşağıdaki hedefleri **birlikte** optimize eden parametreleri bulmaktır:

```
MAXIMIZE: Bileşik Büyüme Oranı (Compound Growth Rate)
KOŞULLAR:
  - Likidasyon olasılığı = 0 (Monte Carlo 10,000+ trial ile kanıtla)
  - Maksimum drawdown ≤ benim belirleyeceğim eşik (sormazsan %30 varsay)
  - İşlem başına net beklenti > 0 (tüm sürtünmeler dahil)
  - Yılda minimum 100+ işlem (istatistiksel güvenilirlik için)
```

### Optimize Edilecek Değişkenler:
Aşağıdaki parametrelerin HİÇBİRİ sabit değildir. Hepsini veri ve simülasyonla belirle:

- **Döngü hedefi** (her büyüme adımının kâr yüzdesi)
- **Kurtarma faktörü** (kayıp sonrası ne kadar agresif risk alınacak — sabit bir bölen KULLANMA, volatilite ve win rate'e göre dinamik hesapla)
- **Maksimum risk sınırı** (tek işlemde kasanın ne kadarı riske edilebilir — drawdown derinliğine göre dinamik olsun)
- **Kaldıraç limiti** (doygunluk noktasını bul — üstü faydasız)
- **TP seviyeleri ve bölme oranları** (TP1/TP2/TP3 R-çarpanları)
- **SL mesafesi** (ATR çarpanı)
- **Timeframe** (frekans vs kalite trade-off'unu optimize et)
- **Betting sistemi** (ORP, Paroli, Fibonacci, Kelly, hibrit — en iyisini bul veya yeni bir sistem tasarla)
- **Limit emir mekanizması** (dolum oranı vs giriş kalitesi dengesi)

## ⚠️ BORSA GERÇEKLİKLERİ (Değiştirilemez Sabitler)

Tüm kodlarında ve simülasyonlarında bunları birebir modelle:

| Parametre | Değer |
|-----------|-------|
| Platform | Binance Futures USDT-M |
| Komisyon (Taker) | %0.04 |
| Slippage (Market) | %0.10 |
| Slippage (Limit) | %0.02 |
| İşlem Gecikmesi | +1 bar (sinyal barı kapandığında, sonraki barın açılışında giriş) |
| Limit Doluş Kuralı | Fiyatın limit seviyesine değmesi yetmez, strict geçmesi gerekir |

## 🎯 SİNYAL MOTORU: S3 (Kanıtlanmış Çerçeve)

Ablation study ile kanıtlanmış en iyi karar modeli:

```
LONG: Fiyat > EMA200 AND taze bullish Order Block mevcut
SHORT: Fiyat < EMA200 AND taze bearish Order Block mevcut
ELSE: İşlem yok (bekleme)
```

Bu çerçeveyi baz al ama iyileştirme yapmakta serbestsin. Herhangi bir değişikliği **A/B testi ve ablation study** ile kanıtla.

## 🔧 GİRİŞ SORUNU (Çözülmesi Gereken Ana Problem)

Hardcore testlerde kanıtlanmıştır ki:
- OB midpoint limit girişi: WR ~%90 → ama dolum oranı %50-70
- Market order girişi: WR ~%30 → çalışmıyor
- Scale-In DCA (50/50 OB high + mid): WR ~%45-50, expectancy pozitif

Giriş mekanizmasını optimize et. Hibrit çözümler (limit + timeout + market fallback) değerlendir. Dolum oranı × giriş kalitesi × frekans trade-off'unu çöz.

## 📊 PARA YÖNETİMİ FELSEFESİ

```
1. Normal: Baz risk ile işlem aç
2. Kazanç serisi: Risk kademeli artabilir (Paroli benzeri)
3. Kayıp: Zararı telafi edecek kurtarma riski HESAPLA
   → Kurtarma faktörünü sabit tutma, dinamik olarak çöz:
     f(equity, target, rolling_WR, volatility, consecutive_losses, dd_tolerance)
   → Hedef: "En hızlı kurtarma + Batma riski = 0"
4. Ruin Guard: Hiçbir durumda kasa batmamalı
   → Koruma sınırı drawdown derinliğine göre dinamik
5. Döngü tamamlandığında: Zirve sıfırla, yeni döngü başlat
```

## 📋 BENİ BİLGİLENDİR

Her analiz ve optimizasyon adımında:
1. **Ne yaptığını** ve **neden o parametreyi seçtiğini** açıkla
2. Monte Carlo sonuçlarını raporla (medyan, %5 worst case, batma oranı)
3. Gerçekçi düzeltme uygula (backtest × 0.50-0.70 = gerçekçi beklenti)
4. Trade-off'ları açıkça belirt (neyi feda ediyorsun, neyi kazanıyorsun)

## 🚀 ÇALIŞMA ORTAMIM

- Dil: Python 3.10+
- Veri: Binance API (ccxt kütüphanesi ile)
- Backtest: Kendi yazdığımız motor (walk-forward, anti-repainting)
- Canlı bot: Mevcut modüler yapı (bot_main.py, risk_manager.py, executor.py, portfolio.py)
- İzleme listesi: Binance Futures'ta en likit 15-20 altcoin (BTC hariç veya dikkatli)

Hazırsan ilk görevine başla.
````

---

# BÖLÜM 5: ÖNCEKİ ÇALIŞMA ÖZETİ (CONTEXT DUMP)

AI'a yeni bir chat'te verirken bu bölümü de eklemen önerilir — böylece tekerleği yeniden icat etmek zorunda kalmaz.

## 5.1. Yapılan Testlerin Özeti

```
TAMAMLANAN TESTLER:
├── 200+ konfigürasyon taranmış (5 coin × 5 TF × 6 kaldıraç × 5 sermaye × 4 model)
├── Ablation Study: S1/S2/S3/S4 karar modelleri → S3 şampiyon (2 girdi)
├── Filtre gevşetme: A(sıkı)/D(orta)/H(gevşek) → D optimali
├── Hardcore Validation: +1 bar gecikme + %0.10 slippage
│   → OB midpoint girişi: WR %90, market girişi: WR %29
│   → Sonuç: Giriş fiyatı stratejinin en kritik değişkeni
├── 180 gün ETH 1H: 23 işlem, WR %48, ORP ile %60 kâr
├── Scale-In DCA testi: 50/50 OB high+mid → ETH 4H'de +0.78R expectancy
├── Monte Carlo: 1000 trial × 400 işlem → ORP-5% batma oranı %0
├── Kelly Criterion: Optimal risk %85, biz fractional Kelly kullanıyoruz
└── Kaldıraç doygunluk: 5x = optimal, üstü faydasız
```

## 5.2. Mevcut Kod Yapısı

```
tirad_backtest/
├── live_scan.py          → S3 sinyal motoru + görselleştirme
├── simulate_orp.py       → ORP backtest motoru
├── simulate_15m_confluence.py → Multi-TF confluence test
├── bot/
│   ├── bot_main.py       → Ana döngü + zamanlayıcı
│   ├── risk_manager.py   → ORP risk hesabı
│   ├── executor.py       → Binance ccxt entegrasyonu
│   ├── portfolio.py      → Multi-coin watchlist
│   ├── position_manager.py → SQLite pozisyon takibi
│   └── compound_tracker.py → Bileşik büyüme dashboard
```

## 5.3. Kritik Keşifler

> [!CAUTION]
> **Giriş Fiyatı = Her Şey.** Önceki raporlardaki $78K ve $18K gibi devasa rakamlar, limit emrin %100 dolduğu varsayımına dayanıyordu. Gerçekte dolum oranı %50-70'tir. Bu, bileşik adım sayısını yarıya düşürür ve sonuçları dramatik olarak etkiler.

> [!WARNING]
> **BTC 15M/1H stratejilerde noise yüksek.** BTC'yi strateji dışı bırakmak veya sadece 4H+ TF'lerde kullanmak daha güvenlidir.

> [!TIP]
> **Frekans paradoksu:** 1H = çok sinyal ama düşük kalite. 4H = az sinyal ama yüksek kalite. Çözüm: 4H'de kal ama 15-20 coin tara → frekansı coin sayısıyla ölçekle.
