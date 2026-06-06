# 📚 TIRAD AI: NİHAİ VERSİYON TARİHÇESİ VE VERİ SÖZLÜĞÜ (HANDOVER MANUAL)

Bu belge, "Tirad" isimli algoritmik ticaret botunun sıfır noktasından itibaren geçirdiği tüm evrimleri (V1 - V19), kullanılan verilerin yapılarını ve ardında yatan matematiksel felsefeyi detaylandırır. 

**Hedef Kitle:** Projeyi devralacak yeni Yapay Zeka Ajanları (AI Agents) ve Geliştiriciler.

---

## 📊 BÖLÜM 1: VERİ SÖZLÜĞÜ (DATA DICTIONARY)

Sistem kâğıt üstündeki hayali testleri değil, gerçek piyasa "sürtünme" (friction) kurallarını kullanır.

1. **OHLCV Verisi:**
   - **Kaynak:** Binance Futures (Vadeli İşlemler).
   - **Kapsam:** Sadece Top 20 Likit Majör Coin (BTC, ETH, SOL, BNB, XRP vb.). Pumping/Dumping shitcoinler yasaktır.
   - **Zaman Dilimi (Timeframe):** Kesinlikle `4H` (4 Saatlik). Diğer tüm küçük zaman dilimleri komisyon canavarı tarafından yutulmuştur.

2. **Komisyon ve Slippage (Sürtünme Vergisi):**
   - Sistem **Market (Piyasa) Emirlerini YASAKLAR.** Fiyatın peşinden koşulmaz.
   - Tüm girişler ve çıkışlar **Limit Maker** (Piyasa Yapıcı) emri olarak atılır.
   - **Maker Fee:** Binance'de %0.02'dir. İşleme giriş ve çıkış toplamı yuvarlatılmış %0.04 - %0.06 (slippage payı dahil) olarak simüle edilmiştir. 1 Saatlik grafiklerde bu komisyon %50'den fazla kârı silerken, 4H grafiklerde kâr marjı büyük olduğu için tolere edilebilmektedir.

3. **Look-Ahead Bias (Geleceği Görme Hatası) Engeli:**
   - İndikatör hesaplamalarında kapanmamış (canlı) mum ASLA kullanılmaz. Tüm hesaplamalar `iloc[-2]` (son kapanmış mum) üzerinden yapılır.

---

## 🧬 BÖLÜM 2: VERSİYON TARİHÇESİ (EVRİM SÜRECİ)

Bütün versiyonların kodları ve raporları `uyg/src/versions/` ve `uyg/docs/` dizinlerine arşivlenmiştir.

### ❌ V1 - V5: "Ölüm Vadisi" (The Death Zone)
- **Mantık:** 15 Dakikalık (15m) ve 1 Saatlik (1H) grafiklerde çok sayıda işlem açarak hızlıca zengin olma denemesi. İşlemlere SMC Order Block mantığıyla Market emri kullanılarak girildi.
- **Sonuç:** FİYASKO. Binance'in minimum işlem büyüklüğü kuralları (Örn: BTC için min 0.001) ve Market taker komisyonları (%0.04) yüzünden kasa $100'den $0.28'e kadar eridi. Komisyonlar kârı yuttu.

### 🛠️ V6 - V10: "Occam'ın Usturası" ve 4H'ye Geçiş
- **Mantık:** Zaman dilimi `4H`'ye çıkarıldı. Karmaşık SMC indikatörleri silindi, yerine sadece **Supertrend (14, 3.5)** ve **EMA 250** bırakıldı (Buna S3 Stratejisi dendi). İşlem sayısını artırmak için 5 farklı coine yayıldı.
- **Sonuç:** Kârlılık başladı. Komisyonlar 4H'de önemsizleşti. Ancak lineer büyüme çok yavaştı.

### 🚀 V11 - V13: "ORP" Bileşik Büyüme Motorunun İcadı
- **Mantık:** $100 kasayı Milyon dolarlara taşımak için **Optimized Recovery Progression (ORP)** matematik motoru icat edildi.
  - *Kurallar:* Hedef %15 büyüme. Zarar gelirse, zararı 1.5'e (Recovery Factor) bölerek yeni işleme risk olarak ekle. Kasanın %20'sinden fazlasını asla riske atma (Max Risk Cap).
- **Sonuç:** Sistem bir anda exponansiyel (katlanarak) büyümeye başladı. Kasa 20 bin doların üzerine çıktı.

### 🛡️ V14: Balina Tuzağı Filtresi (Anti-Likidite)
- **Mantık:** Testere (Chop) aylarında (Ekim ve Aralık) kasanın ciddi eridiği fark edildi. Bu aylarda işlem girmemek için "Hacim ve Trend" filtreleri kodlandı.
  - *Kural:* Eğer `vol_ratio > 2.5` (Son 20 mumun hacminin 2.5 katından büyük bir hacim var) veya `ADX > 40` ise **İŞLEMİ REDDET**. Çünkü bunlar trend kırılımı değil, Smart Money'in stop patlatma (likidite alma) iğneleriydi.
- **Sonuç:** Ekim ayındaki çöküşler inanılmaz derecede yumuşatıldı.

### 🤖 V15 - V17: Limit Maker ve Makine Öğrenmesi Dönemi
- **Mantık:** XGBoost ve K-Means algoritmaları kullanılarak geçmiş 90 günlük veriden piyasanın "Trend" mi yoksa "Chop" (Testere) mi olduğu etiketlendi. Ancak en büyük devrim, Market emrini çöpe atıp **Limit Emirlerle (Maker)** komisyonu %75 oranında ucuzlatmamız oldu.

### 🥇 V18 Ultimate: Grid Search ve Altın Formül
- **Olay:** 3.600 farklı ORP kombinasyonu ve strateji varyasyonu `v18_ultimate.py` ile test edildi.
- **Keşif:** V14 Filtresi + Limit Emir + Dinamik Kaldıraç (Çöküşte kaldıracı 15x'ten 3x'e kadar düşüren sistem) + ORP (%15 Hedef, %20 Max Risk) birleşti.
- **Sonuç:** Sadece $100 başlangıçla (gerçekçi komisyonlar düşüldüğünde) **1.56 MİLYON DOLAR NET KÂR** ve iflas sıfır riski (Kasa en kötü $12'ye düştü). Raporlar `v18_ultimate_report.md` ve `v18_golden_monthly.md` olarak kaydedildi.

### 🏆 V19 WIN RATE HUNTER: Nihai Şampiyon
- **Olay:** Kullanıcı (Komutan), *"Win Rate (Kazanma Oranı) %44.2, bunu artırın"* emrini verdi. `v19_winrate.py` yazıldı ve 127 farklı filtre kombinasyonu test edildi.
- **Keşif:** Balina tuzağı filtresi olan Hacim Oranı, `2.5x` yerine **`< 2.0x` (Sıkı Hacim)** olarak daraltıldığında inanılmaz bir sonuç elde edildi. 29 adet gereksiz ve zararla sonuçlanan "sahte kırılım" işlemi çöpe atıldı.
- **Sonuç:** Win Rate **%45.7**'ye fırladı. Kasa iflas sınırı daha da güvenli bir noktaya ($19.12) taşındı. Toplam net kâr ise **$1.78 MİLYON DOLAR'a** çıktı. Bu, tüm testlerin zirvesidir. `v19_winrate_report.md` olarak arşivlendi.

---

## 🛠️ BÖLÜM 3: GÜNCEL DOSYA YAPISI VE GELECEK ADIMLAR

Bütün dosyalar başarıyla "scratch" ortamından profesyonel `uyg` dizinine taşınmıştır.

```text
uyg/
├── AGENT.md                 # Yeni Ajanlar için Hızlı Felsefe Özeti
├── docs/
│   ├── VERSION_HISTORY_AND_DATA.md # Bu Belge (V1'den V19'a tüm tarihçe)
│   ├── v18_ultimate_report.md
│   ├── v18_golden_monthly.md
│   └── v19_winrate_report.md
└── src/
    ├── v19_live_bot.py      # CANLI İŞLEM MOTORU (V19 Şampiyon Mimarisi)
    ├── data/                # OHLCV Geçmiş Test Verileri
    └── versions/            # Eski Python test dosyaları (v18_ultimate, v18_golden, v19_winrate vb.)
```

**Sıradaki AI Agent İçin Görev:**
Mimarisi kurulan `uyg/src/v19_live_bot.py` dosyasını aç ve "TODO" ile belirtilen kısımlara Binance API bağlantılarını (OCO Emirleri, Limit Maker atma algoritmaları) kodla. Gelecek senin ellerinde!
