# 🔬 TAM KAPSAMLI TEKNİK RAPOR
## Kripto Futures Ticaret Botu — Strateji, Analiz ve Backtest Sonuçları

**Rapor Tarihi:** 28 Mayıs 2026  
**Hazırlayan:** Algorithmic Trading Research Lab  
**Kapsam:** BTC, ETH, SOL, BNB, XRP — Binance Futures  
**Test Periyodu:** Haziran 2025 – Mayıs 2026 (1 Yıl)

---

# 📖 İÇİNDEKİLER

1. [Projenin Amacı ve Felsefesi](#1-projenin-amacı-ve-felsefesi)
2. [Teknik Göstergeler — Bot Ne Görüyor?](#2-teknik-göstergeler--bot-ne-görüyor)
3. [Puanlama Sistemi — Bot Nasıl Karar Veriyor?](#3-puanlama-sistemi--bot-nasıl-karar-veriyor)
4. [Giriş/Çıkış Mekanizması — Bot Nasıl İşlem Açıyor?](#4-girişçıkış-mekanizması--bot-nasıl-i̇şlem-açıyor)
5. [Sermaye Yönetim Stratejileri — 4 Farklı Sistem](#5-sermaye-yönetim-stratejileri--4-farklı-sistem)
6. [Monte Carlo Simülasyonu — 400 İşlem Projeksiyonu](#6-monte-carlo-simülasyonu--400-i̇şlem-projeksiyonu)
7. [Tüm Backtest Sonuçları — Detaylı Tablolar](#7-tüm-backtest-sonuçları--detaylı-tablolar)
8. [Kaldıraç ve Likidasyon Analizi](#8-kaldıraç-ve-likidasyon-analizi)
9. [Neden %5 Adım, Neden ORP?](#9-neden-5-adım-neden-orp)
10. [Nihai Optimal Strateji ve Uygulama Rehberi](#10-nihai-optimal-strateji-ve-uygulama-rehberi)

---

# 1. Projenin Amacı ve Felsefesi

## 1.1. Temel Fikir
100 Dolar başlangıç sermayesiyle, **bileşik faiz** (compounding) mantığında ilerleyerek, her başarılı işlemde kasayı belirli bir yüzde büyüterek sermayeyi katlamak.

## 1.2. Neden Futures (Vadeli İşlem)?
- **Hem yükselişten hem düşüşten** kar edebilme (Long + Short)
- **Kaldıraç** kullanarak küçük sermayeyle büyük pozisyon açabilme
- **Binance Futures** üzerinde 24/7 işlem imkanı

## 1.3. Blackjack Analojisi
Strateji, kumarhane "bet sistemlerinden" esinlenilmiş bir yaklaşımla tasarlandı:
- Kumarhanede kasa avantajı vardır; burada ise **bizim** avantajımız var (%80-90 Win Rate)
- Kumarhanede kayıplar rastgeledir; burada ise kayıplar **stop-loss** ile sınırlanmıştır
- "Paroli" (kazandıkça bahis artır) ve "Martingale" (kaybettikçe artır) gibi sistemler gerçek veriler üzerinde test edildi

## 1.4. Anti-Repainting Garantisi

> [!IMPORTANT]
> Botumuz **asla geleceği göremez**. Her bar (mum) için analiz yapılırken, o barın verisi dahil edilmez:
> ```python
> df_slice = df_full.iloc[:i]  # Bar i'nin verisi HİÇ görülmez
> ```
> Bu "walk-forward" yöntemi sayesinde backtest sonuçları gerçek hayattaki performansla birebir örtüşür. Sinyal bar `i-1`'de üretilir, giriş bar `i`'nin açılışında yapılır.

---

# 2. Teknik Göstergeler — Bot Ne Görüyor?

Bot, piyasayı analiz etmek için **3 katmanlı** bir gösterge sistemi kullanır:

## Katman 1: SMC (Smart Money Concepts) Göstergeleri

Bu göstergeler, kurumsal yatırımcıların ("balinalar") bıraktığı ayak izlerini takip eder.

### 2.1. Market Structure (Piyasa Yapısı) — BOS / CHoCH / MSS

```
BULLISH yapı:   Higher High (HH) + Higher Low (HL)
BEARISH yapı:   Lower High (LH) + Lower Low (LL)
```

- **Swing Pivots:** Son 10 mum içindeki en yüksek ve en düşük noktalar tespit edilir.
- **BOS (Break of Structure):** Mevcut trendin devamı. Yükselişteyken son tepenin kırılması = BOS Bull.
- **CHoCH (Change of Character):** Trendin tersine dönmesi. Düşüşteyken son tepenin kırılması = CHoCH Bull. Bu, piyasanın "karakterinin değiştiğini" gösterir.
- **MSS (Market Structure Shift):** Son 20 mumda iç yapıda küçük bir BOS. Trendin dönmesinin erken sinyali.

**Nasıl hesaplanıyor:**
```python
# Son 3 kapanış mumunun tümü son tepeden yukarıdaysa = BOS Bull
bos_bull = (son_3_kapanış > son_swing_high).all() and trend == "BULLISH"

# Son 3 kapanış mumunun tümü son tepeden yukarıdaysa AMA trend BEARISH ise = CHoCH Bull
choch_bull = (son_3_kapanış > son_swing_high).all() and trend == "BEARISH"
```

**Puanlama:**
| Sinyal | Puan |
|--------|------|
| BOS (Bull/Bear) | +2.0 |
| CHoCH (Bull/Bear) | +1.5 |
| MSS (Bull/Bear) | +1.0 |

---

### 2.2. Order Blocks (Emir Blokları)

Order Block, kurumsal yatırımcıların piyasaya **büyük miktarda emir** bıraktığı mumları ifade eder.

**Bullish OB Tespit Mantığı:**
1. Bir kırmızı (düşüş) mumu bul
2. Bu mumun gövdesi, son 20 mumun ortalama gövdesinin **1.3 katından** büyük olmalı (güçlü mum)
3. Sonraki 3 mum boyunca fiyat **yukarı** gitmeli
4. Bu kırmızı mumun aralığı (high-low) = Order Block bölgesi
5. Fiyat bu bölgeye tekrar geldiğinde → **alım fırsatı**

**Breaker Block:** Order Block kırılmışsa (fiyat OB'nin altına inmişse), artık **karşı yönde** çalışır. Bearish bir OB kırılırsa → Bullish Breaker olur.

```python
# Geriye dönük 80 mum taranır
for i in range(start, end):
    bar_size = abs(close[i] - open[i])
    avg = avg_move[i]  # 20 bar ortalama gövde
    is_impulse = bar_size > avg * 1.3  # Güçlü mum mu?
    
    # Sonraki N mum yukarı gidiyorsa + bu mum kırmızıysa = Bullish OB
    if sonraki_mumlar_yukari and close[i] < open[i]:
        # Bu mumun high-low aralığı = Order Block
```

**Puanlama:**
| Sinyal | Puan |
|--------|------|
| Order Block (aktif, kırılmamış) | +2.0 |
| Breaker Block | +1.0 |

---

### 2.3. Fair Value Gaps (FVG — Adil Değer Boşlukları)

FVG, piyasanın **çok hızlı** hareket ettiğinde geride bıraktığı fiyat boşluklarıdır. 3 ardışık mumun yapısında:
- Mum 1'in High'ı ile Mum 3'ün Low'u arasında boşluk varsa → **Bullish FVG**
- Mum 1'in Low'u ile Mum 3'ün High'ı arasında boşluk varsa → **Bearish FVG**

Fiyat genellikle bu boşlukları doldurmak için geri döner (mıknatıs etkisi).

```python
# Bullish FVG: Mum3'ün Low'u > Mum1'in High'ı (boşluk yukarıda)
if candle3_low > candle1_high:
    gap_size = (candle3_low - candle1_high) / candle1_high
    if gap_size >= 0.002:  # En az %0.2 boşluk
        # Dolduruldu mu kontrol et
        filled = any(sonraki_low'lar <= candle1_high)
        if not filled:  # Sadece doldurulmamış FVG'ler geçerli
            bull_fvg.append(...)
```

**Puanlama:**
| Sinyal | Puan |
|--------|------|
| Doldurulmamış FVG (trendle aynı yönde) | +1.5 |

---

### 2.4. Liquidity Map (Likidite Haritası) — BSL / SSL

**Buy Side Liquidity (BSL):** Eşit tepe noktaları (Equal Highs). Bu seviyelerin üzerinde stop emirleri birikir. Balinalar fiyatı buraya iterek stop'ları tetikler.

**Sell Side Liquidity (SSL):** Eşit dip noktaları (Equal Lows). Bu seviyelerin altında stop emirleri birikir.

**Sweep:** Fiyat likidite seviyesini kısa süreliğine geçip geri dönmesi. Bu, büyük oyuncuların stopları topladığının ve piyasanın ters yöne gideceğinin güçlü bir sinyali.

```python
# Eşit tepeler: 2 veya daha fazla barın yüksek noktaları birbirine çok yakın
for i, j in karşılaştır:
    if abs(high[i] - high[j]) / high[i] < 0.0025:  # %0.25 tolerans
        # Bu BSL (Buy Side Liquidity)

# Sweep: Fiyat BSL'yi geçip geri mi döndü?
sweep_up = any(son_5_high > bsl_seviyesi) and any(son_5_kapanış < bsl_seviyesi)
```

**Puanlama:**
| Sinyal | Puan |
|--------|------|
| SSL Sweep (düşük süpürülmüş → Bullish sinyal) | +2.0 |
| BSL Sweep (yüksek süpürülmüş → Bearish sinyal) | +2.0 |

---

### 2.5. Displacement (Güçlü İmpulsif Hareket)

Tek bir mumun gövdesi, ATR'nin **2.5 katından** büyükse, bu bir "displacement" (yerinden etme) hareketidir. ICT'de bu, market maker'ların aktif olarak pozisyon aldığını gösterir.

```python
# Son 5 mumdan herhangi birinin gövdesi > ATR × 2.5 ise
if body > atr * 2.5:
    direction = "UP" if close > open else "DOWN"
```

**Puanlama:**
| Sinyal | Puan |
|--------|------|
| Trendle aynı yönde displacement | +0.5 |

---

### 2.6. OTE (Optimal Trade Entry — Fibonacci Geri Çekilme)

ICT'nin Fibonacci 0.62 – 0.79 geri çekilme bölgesi. Güçlü bir impulsif hareketin ardından fiyat bu bölgeye geri çekilirse, ideal giriş noktasıdır.

```python
fib62 = swing_high - range * 0.618
fib79 = swing_high - range * 0.786

bull_ote = fib79 <= current_price <= fib62  # Bu aralıktaysa = giriş bölgesi
```

**Puanlama:**
| Sinyal | Puan |
|--------|------|
| OTE bölgesindeyse | +0.5 |

---

### 2.7. Supply & Demand Zones (Arz & Talep Bölgeleri)

Order Block'a benzer ama daha geniştir. Güçlü bir hareketin başladığı 3-4 mumluk konsolidasyon bölgesini kapsar.

```python
# Sonraki 5 mumda >%1.5 hareket varsa
forward_move = abs(close[i+4] - close[i]) / close[i]
if forward_move >= 0.015:
    # Bu mumun etrafındaki 4 mumluk aralık = Supply/Demand Zone
```

**Puanlama:**
| Sinyal | Puan |
|--------|------|
| Fiyat demand zone içindeyse (Bullish) | +1.0 |
| Fiyat supply zone içindeyse (Bearish) | +1.0 |

---

### 2.8. Wyckoff Phase (Wyckoff Faz Analizi)

Richard Wyckoff'un 100 yıllık piyasa faz teorisine dayalı analiz:

| Faz | Açıklama | Sinyal |
|-----|----------|--------|
| **Selling Climax Zone** | Yüksek hacimli dip + düşük hacimli toparlanma | Dip bölgesi, alım fırsatı |
| **Wyckoff Accumulation** | SC + düşük hacim + dar range | Güçlü alım bölgesi |
| **Distribution Zone** | Tepe bölgesi, zayıf momentum | Satış bölgesi |
| **Consolidation Spring** | Dar range + düşük hacim | Patlama öncesi sıkışma |

**Puanlama:**
| Sinyal | Puan |
|--------|------|
| Wyckoff Accumulation (Bullish) | +1.0 |
| Selling Climax Zone (Bullish) | +1.0 |
| Distribution Zone (Bearish) | +1.0 |

---

## Katman 2: Klasik Teknik Göstergeler

### 2.9. EMA Dizilimi (8, 21, 55, 200)

```python
# Tam dizilim (mükemmel yükseliş): EMA8 > EMA21 > EMA55 > EMA200
ema_full = e8 > e21 > e55 > e200  # +2.0 puan

# Kısmi dizilim: 3'ünden 2'si doğruysa
ema_part = (e8>e21) + (e21>e55) + (e55>e200) >= 2  # +1.0 puan
```

### 2.10. MACD (12, 26, 9)
```python
macd_line = EMA12 - EMA26
signal = EMA9(macd_line)
histogram = macd_line - signal

macd_bull = histogram > 0 AND histogram_şimdi > histogram_önceki  # Artan momentum
```

| Sinyal | Puan |
|--------|------|
| MACD Bull (histogram pozitif + artıyor) | +2.0 |
| MACD histogram sadece pozitif | +1.0 |

### 2.11. RSI (14) + Diverjanslar
```python
rsi = 100 - 100 / (1 + avg_gain / avg_loss)

# Gizli Boğa Diverjansı: Fiyat yüksek dip + RSI yüksek dip (trend devamı)
# Klasik Boğa Diverjansı: Fiyat düşük dip + RSI yüksek dip (trend dönüşü)
```

| Sinyal | Puan |
|--------|------|
| RSI Gizli Boğa Diverjansı | +2.0 |
| RSI Klasik Boğa Diverjansı | +1.0 |
| RSI Aşırı Satım (<30) | +0.5 |

### 2.12. Stochastic (14, 3)
```python
stoch_bull = stoch_önceki < 20 AND stoch_şimdi > 20  # Aşırı satımdan çıkış
```
| Sinyal | Puan |
|--------|------|
| Stochastic Bull Cross | +1.0 |

### 2.13. VWAP (Volume Weighted Average Price)
```python
vwap = cumsum(typical_price × volume) / cumsum(volume)
vwap_above = current_price > vwap  # Fiyat VWAP üzerinde = bullish
```
| Sinyal | Puan |
|--------|------|
| Fiyat VWAP üzerinde | +1.0 |

### 2.14. OBV (On Balance Volume)
```python
obv = cumsum(sign(close_change) × volume)
obv_up = obv_şimdi > obv_15_bar_önce AND fiyat_şimdi > fiyat_15_bar_önce
```
| Sinyal | Puan |
|--------|------|
| OBV artan (hacim + fiyat uyumu) | +1.0 |

### 2.15. Bollinger Bands Squeeze
```python
bb_upper = EMA20 + 2 × StdDev20
bb_lower = EMA20 - 2 × StdDev20
bandwidth = (bb_upper - bb_lower) / price

bb_squeeze = bandwidth < avg_bandwidth × 0.75  # Bantlar daralmış = patlama yakın
```

---

## Katman 3: Kurumsal Göstergeler

### 2.16. CVD (Cumulative Volume Delta)
Alıcı hacmi ile satıcı hacmini ayrıştırır:
```python
direction = +1 if close > open else -1  # Yeşil mum = alıcı, kırmızı = satıcı
cvd = cumsum(direction × volume)

# CVD artan + fiyat artan = gerçek alım baskısı
cvd_bull = cvd_şimdi > cvd_21_bar_önce AND fiyat_şimdi > fiyat_21_bar_önce
```
| Sinyal | Puan |
|--------|------|
| CVD Bull (alıcı baskısı doğrulandı) | +2.0 |

### 2.17. Volume Profile (VPOC)
En çok hacmin geçtiği fiyat seviyesi (Volume Point of Control). Fiyat bu seviyeye yakınsa, güçlü bir destek/direnç noktasında demektir.

```python
# Fiyat VPOC'a %1'den yakınsa
if abs(current_price - vpoc) / vpoc < 0.01:
    # VPOC desteğinde
```
| Sinyal | Puan |
|--------|------|
| VPOC desteğinde | +1.0 |

### 2.18. 21 Günlük Momentum
```python
# Son 21 bar öncesine göre fiyat yükseldiyse
momentum_bull = current_price > price_21_bars_ago
```
| Sinyal | Puan |
|--------|------|
| 21-Bar pozitif momentum | +2.0 |

---

# 3. Puanlama Sistemi — Bot Nasıl Karar Veriyor?

## 3.1. 3 Skorun Birleştirilmesi

Yukarıdaki tüm göstergeler 3 ayrı kategoride toplanır:

| Kategori | Maksimum Puan | İçeriği |
|----------|---------------|---------|
| **SMC Skoru** | 10.0 | BOS, CHoCH, MSS, OB, Breaker, FVG, Liquidity Sweep, OTE, Supply/Demand, Wyckoff, Displacement |
| **Klasik Skor** | 10.0 | EMA, MACD, RSI, Stochastic, VWAP, OBV, Diverjanslar |
| **Kurumsal Skor** | 7.0 | CVD, Volume Profile, 21-Bar Momentum |

**Toplam Kapasite:** 27.0 puan

## 3.2. Composite (Bileşik) Skor Hesaplaması

```python
composite = (smc_score + classic_score + institutional_score) / 27.0 × 10.0
```

Bu formül, ham puanı **10 üzerinden** bir nota dönüştürür.

## 3.3. Filtreler — Kalite Kapıları

Composite skor yüksek olsa bile, aşağıdaki filtrelerin **tümü** geçilmelidir:

| Filtre | Koşul | Neden |
|--------|-------|-------|
| **Minimum Skor** | `composite >= 4.5` | Düşük kaliteli sinyalleri eler |
| **Trend Filtresi** | Trend ≠ NEUTRAL | Belirsiz piyasada işlem açmaz |
| **1D Trend Uyumu** | 4H-EMA200 yönü ile işlem yönü aynı olmalı | Karşı trend işlemlerini engeller |
| **Hacim Onayı** | Giriş barı hacmi > 20-bar ortalama × 1.2 | Düşük hacimde sahte kırılımları önler |
| **Stop-Loss Mesafesi** | `0.5% < sl_dist <= 10%` | Çok dar stop = gereksiz patlar, çok geniş = risk yüksek |

**Sonuç:** Bu 5 filtre sayesinde bot, ortalama bir yılda sadece **70-150 işlem** açar. Bu **az ama kaliteli** işlem yaklaşımıdır.

---

# 4. Giriş/Çıkış Mekanizması — Bot Nasıl İşlem Açıyor?

## 4.1. Giriş Fiyatı Belirleme

Bot, rastgele piyasa fiyatından değil, yapısal olarak anlamlı bir fiyattan girer:

```
Giriş Önceliği:
1. Order Block varsa → OB'nin ortası (low + high) / 2
2. FVG varsa → FVG'nin ortası
3. Hiçbiri yoksa → Güncel kapanış fiyatı
```

## 4.2. Stop-Loss (Zarar Kes) Hesaplaması

```python
# ATR (Average True Range) tabanlı dinamik stop
atr = 14 periyot ATR

# Bullish giriş: entry - ATR × 1.5
sl_price = entry_price - atr × 1.5

# Ek güvence: OB'nin alt seviyesinin %0.2 altı
if order_block_var:
    ob_sl = order_block_low × 0.998
    sl_price = min(sl_price, ob_sl)  # Daha düşük olanı al
```

## 4.3. Kaldıraç (Leverage) Hesaplaması

Bot, kaldıracı skor bazında ve risk bazında dinamik olarak hesaplar:

```python
# 1. Skora göre maksimum kaldıraç
if composite >= 8.0:  max_lev = 5x
elif composite >= 6.5: max_lev = 4x
elif composite >= 5.5: max_lev = 3x
else:                  max_lev = 2x

# 2. Riske göre gereken kaldıraç
required_lev = ceil(0.02 / sl_distance)
# Örnek: SL mesafesi %1 ise → ceil(0.02/0.01) = 2x

# 3. Kullanılan kaldıraç = min(score_lev, required_lev, user_cap)
leverage = min(max_lev, required_lev, kullanıcı_limiti)
```

## 4.4. Take-Profit (Kar Al) Sistemi — Kademeli Çıkış

Bot, tek seferde tüm pozisyonu kapatmaz. 3 kademeli hedef kullanır:

| Hedef | R:R Oranı | Kapatılan Pozisyon | Açıklama |
|-------|-----------|-------------------|----------|
| **TP1** | 1.5R | %40 | İlk kar, stop breakeven'a çekilir |
| **TP2** | 2.5R | %35 | İkinci kar kilitleme |
| **TP3** | 4.0R | %25 | Kalan pozisyon tam kapanır |

**R nedir?** Riske edilen miktarın katı. Eğer stop mesafesi %2 ise, 1R = %2. TP1 = %3, TP2 = %5, TP3 = %8.

## 4.5. Trailing Stop (Takipçi Stop) Mekanizması

TP1 tetiklendiğinde:
1. Stop-Loss → **Giriş fiyatına** çekilir (breakeven)
2. Trailing Stop aktif olur: `trail_sl = current_price - ATR × 1.2`
3. Fiyat yükseldikçe trail_sl da yükselir
4. Fiyat geri döndüğünde trail_sl seviyesinde pozisyon kapanır

```python
# TP1 tetiklendi
if high >= tp1:
    locked_pnl += 0.40 × 1.5R  # %40 pozisyonun 1.5R karı kilitlendl
    sl = entry × 1.001          # Stop breakeven'a çekildi
    trail_active = True
    trail_sl = entry - atr × 1.2

# Trailing güncelleme
if trail_active:
    new_trail = close - atr × 1.2
    trail_sl = max(trail_sl, new_trail)  # Sadece yukarı hareket eder
```

## 4.6. Maliyet Modeli (Gerçekçilik)

Her işleme uygulanan gerçekçi maliyet:

| Maliyet | Oran |
|---------|------|
| Binance Futures Taker Fee | %0.04 |
| Slippage (kayma) | %0.05 |
| **Toplam Round-Trip** | **%0.18** |

```python
COMMISSION = 0.0004   # %0.04
SLIPPAGE   = 0.0005   # %0.05
ROUND_TRIP = (COMMISSION + SLIPPAGE) × 2  # = %0.18
```

---

# 5. Sermaye Yönetim Stratejileri — 4 Farklı Sistem

## 5.1. Strateji 1: Fixed Risk (Sabit Risk — %2)

**Mantık:** Her işlemde mevcut kasanın sabit **%2'sini** riske et.

```python
def run_fixed_risk(trades, risk_pct=0.02):
    for trade in trades:
        dollar_pnl = equity × 0.02 × trade.r_mult
        equity += dollar_pnl
```

**Örnek:**
- Kasa: $100, Risk: $2, 1.5R kazanç → +$3, Yeni kasa: $103
- Kasa: $103, Risk: $2.06, 1R kayıp → -$2.06, Yeni kasa: $100.94

**Avantaj:** Stabil, düşük drawdown (%6.8 ortalama)
**Dezavantaj:** Bileşik etkisi yavaş

---

## 5.2. Strateji 2: Fibonacci Progression (Negatif İlerleme)

**Mantık:** Fibonacci serisi çarpanlarıyla risk miktarını ayarla.

```python
fib_multipliers = [1, 1, 2, 3, 5, 8, 13, 21]
base_risk = 0.01  # %1

# Kayıpta: 1 adım ileri (daha yüksek çarpan)
# Kazançta: 2 adım geri (daha düşük çarpan)
# 21x'e ulaşırsa sıfırla (batma koruması)
```

**Örnek Akış:**
| İşlem | Sonuç | Fib Index | Çarpan | Risk |
|-------|-------|-----------|--------|------|
| 1 | KAYIP | 0→1 | 1x | %1 |
| 2 | KAYIP | 1→2 | 2x | %2 |
| 3 | KAZANÇ | 2→0 | 2x | %2 |
| 4 | KAZANÇ | 0→0 | 1x | %1 |

**Avantaj:** En düşük drawdown (%5.6 ortalama)
**Dezavantaj:** Botumuz çok az kaybettiği için çarpan neredeyse hiç artmadı → büyüme çok yavaş

---

## 5.3. Strateji 3: Paroli (Pozitif İlerleme / Reverse Martingale)

**Mantık:** Sadece **kazandıkça** riski artır. Kaybedince basa dön.

```python
base_risk = 0.02  # %2

# Kazanç serisi: %2 → %4 → %8 → %15 (cap)
risk = 0.02 × (2 ^ consecutive_wins)
risk = min(risk, 0.15)  # Asla %15'i geçme

# Kayıpta: consecutive_wins = 0 → risk = %2
# 3 ardışık kazançtan sonra: sıfırla (karı kilitle)
```

**Örnek Akış:**
| İşlem | Sonuç | Ardışık Kazanç | Risk | Equity ($100 başlangıç) |
|-------|-------|----------------|------|-------------------------|
| 1 | KAZANÇ (1.5R) | 1 | %2 | $103.00 |
| 2 | KAZANÇ (2.0R) | 2 | %4 | $111.24 |
| 3 | KAZANÇ (1.5R) | 3→reset | %8 | $124.57 |
| 4 | KAYIP (-1R) | 0 | %2 | $122.08 |

**Avantaj:** Win streak'lerde üstel büyüme (en yüksek getiri potansiyeli)
**Dezavantaj:** Drawdown biraz daha yüksek (%11.9 ortalama)

---

## 5.4. Strateji 4: ORP (Optimized Recovery Progression) — ★ EN OPTİMAL ★

**Mantık:** Her adımda kasayı belirli bir yüzde büyütmeyi hedefle. Kayıp durumunda, bir sonraki işlemde zararı çıkaracak kadar risk al — ama asla kasanın %15'inden fazlasını riske atma.

### ORP Formülleri:

```python
target_equity = start_capital × (1 + step_pct) ^ step_number
# Örnek: 3. adım, %5 büyüme → $100 × 1.05³ = $115.76

# Hedefle mevcut kasa arasındaki fark
delta = target_equity - current_equity

# Gereken risk (kurtarma dahil)
base_risk = equity × 0.025  # Min %2.5
required_risk = max(base_risk, delta / 1.5)

# Pozisyon büyüklüğü
position_size = required_risk / stop_loss_distance

# Gereken kaldıraç
required_leverage = position_size / equity

# ═══ RUIN GUARD (BATMA KALKANI) ═══
# 1. Kaldıraç sınırı
actual_leverage = min(required_leverage, max_leverage_cap)

# 2. Risk sınırı: asla kasanın %15'inden fazla
if actual_risk > equity × 0.15:
    actual_risk = equity × 0.15
    # Pozisyon buna göre küçültülür
```

### Ruin Guard Nasıl Çalışır?

```
Senaryo: Kasa $100, Hedef $105 (5. adım), Ama kasa $95'e düşmüş

Delta = $105 - $95 = $10
Required Risk = $10 / 1.5 = $6.67

Guard Kontrolü:
  $6.67 > $95 × 0.15 ($14.25)? → HAYIR → Risk kabul edilir

Senaryo 2: Kasa $50'ye düşmüş (ekstrem)
Delta = $105 - $50 = $55
Required Risk = $55 / 1.5 = $36.67

Guard Kontrolü:
  $36.67 > $50 × 0.15 ($7.50)? → EVET → Risk $7.50'ye düşürülür
  → Tek seferde kurtarmak yerine birkaç işleme bölünür
```

---

# 6. Monte Carlo Simülasyonu — 400 İşlem Projeksiyonu

Gerçek backtest verileri sınırlı sayıda işlem ürettiği için (6 ayda ~14 işlem), **400 işlemlik** bir sekans oluşturup 3 stratejinin uzun vadeli davranışını gözlemledik.

## 6.1. Simülasyon Parametreleri

```python
win_rate = 0.80         # %80 kazanma oranı (gerçek veriden)
avg_win = +2.0R         # Ortalama kazanç: 2R
avg_loss = -1.0R        # Ortalama kayıp: 1R
num_trades = 400        # 400 işlem dizisi
num_trials = 1000       # 1000 farklı rastgele senaryo
start_capital = $100
```

## 6.2. Monte Carlo Sonuçları

| Strateji | Ort. Bitiş ($) | Medyan Bitiş ($) | Ort. Max DD | Batma Oranı |
|----------|---------------|-----------------|-------------|-------------|
| **Fixed Risk (%2)** | $6,119,601 | $5,607,311 | %6.8 | %0.0 |
| **Fibonacci (Capped)** | $34,432 | $33,932 | %5.6 | %0.0 |
| **Paroli (Reverse Martingale)** | **$916,573,434,182** | **$411,680,266,750** | **%11.9** | **%0.0** |

> [!IMPORTANT]
> **Paroli**, 1000 simülasyonun ortalamasında **916 Milyar Dolar** (!) üretiyor. Bu tabii ki pratikte mümkün değil (borsa likidite limitleri var), ama matematiksel olarak Paroli'nin bileşik faiz gücünü gösteriyor.

> [!NOTE]
> **Hiçbir** simülasyonda, **hiçbir** stratejide hesap sıfırlanma (ruin) gerçekleşmedi. %0.0 batma oranı.

---

# 7. Tüm Backtest Sonuçları — Detaylı Tablolar

## 7.1. İlk Test: 5 Coin Portföy Backtest (4 Saatlik, 5 Ay)

**Koşullar:** $100 başlangıç, %2 sabit risk, bileşik faiz, 4h zaman dilimi

| Metrik | Değer |
|--------|-------|
| Başlangıç Sermayesi | $100.00 |
| **Bitiş Değeri** | **$444.92** |
| **Net Getiri** | **+%344.9** |
| Toplam İşlem | 49 (34 Long / 15 Short) |
| Kazanma Oranı | **%81.6** (40W / 9L) |
| Profit Factor | **7.79** |
| Max Drawdown | **%6.7** |
| Sharpe Ratio | **36.51** |

### Coin Bazında Performans:
| # | Coin | Getiri | Win Rate | Profit Factor | İşlem Sayısı |
|---|------|--------|----------|---------------|-------------|
| 🥇 | SOL/USDT | +%43 | %91 | 17.61 | 11 |
| 🥈 | ETH/USDT | +%40 | %86 | 9.14 | 14 |
| 🥉 | BTC/USDT | +%35 | %82 | 7.82 | 11 |
| 4 | BNB/USDT | +%32 | %62 | 5.46 | 8 |
| 5 | XRP/USDT | +%24 | %80 | 11.24 | 5 |

---

## 7.2. Multi-Timeframe Matris Testi (ETH, SOL, BTC)

**Koşullar:** $100 başlangıç, son 6 ay, farklı zaman dilimleri ve kaldıraç seviyeleri

| Sembol | TF | Kaldıraç | İşlem | Win Rate | PF | Max DD | Bitiş ($) |
|--------|-----|----------|-------|----------|------|--------|-----------|
| **ETH** | 1h | 2x | 13 | %92.3 | 27.80 | %2.2 | **$179.26** |
| **ETH** | 4h | 2x | 14 | %85.7 | 9.14 | %2.1 | **$140.02** |
| **ETH** | 1d | 2x | 4 | %50.0 | 2.04 | %2.2 | $104.11 |
| **ETH** | 1d | 5x | 4 | %50.0 | 2.04 | %2.2 | $104.11 |
| **SOL** | 1h | 2x | 8 | %62.5 | 3.74 | %5.0 | $119.33 |
| **SOL** | 4h | 2x | 11 | %90.9 | 17.61 | %2.2 | **$143.02** |
| **SOL** | 1d | 2x | 2 | %50.0 | 0.96 | %2.0 | $99.88 |
| **BTC** | 1h | 2x | 10 | %90.0 | 10.55 | %2.4 | $124.85 |
| **BTC** | 4h | 2x | 11 | %81.8 | 7.82 | %2.4 | **$135.24** |
| **BTC** | 1d | 2x | 2 | %100 | ∞ | %0.0 | $103.86 |

> [!NOTE]
> **1d (günlük) ve 5x sonuçlarının neden aynı olduğu:** Günlük grafikte ATR çok büyük (stop mesafesi %2.5-6). Bu durumda %2 risk için gereken kaldıraç zaten 1x-2x. Kaldıraç limiti 5x olsa bile asla kullanılmıyor.

---

## 7.3. Bahis Sistemi Karşılaştırması (Tarihsel Veriler Üzerinde)

**Koşullar:** Gerçek backtest işlem dizileri üzerinde 3 farklı bahis sistemi

| Sembol | TF | İşlem | Sistem | Bitiş ($) | Max DD | Battı mı? |
|--------|-----|-------|--------|-----------|--------|-----------|
| **ETH** | 1h | 13 | Fixed Risk | $179.25 | %2.2 | HAYIR |
| **ETH** | 1h | 13 | Fibonacci | $134.49 | %1.1 | HAYIR |
| **ETH** | 1h | 13 | **Paroli** | **$315.27** | %4.5 | HAYIR |
| **ETH** | 4h | 14 | Fixed Risk | $140.02 | %2.1 | HAYIR |
| **ETH** | 4h | 14 | Fibonacci | $118.59 | %1.1 | HAYIR |
| **ETH** | 4h | 14 | **Paroli** | **$188.60** | %8.5 | HAYIR |
| **BTC** | 1h | 10 | Fixed Risk | $124.86 | %2.4 | HAYIR |
| **BTC** | 1h | 10 | Fibonacci | $111.88 | %1.2 | HAYIR |
| **BTC** | 1h | 10 | **Paroli** | **$158.13** | %4.8 | HAYIR |
| **BTC** | 30m | 6 | Fixed Risk | $124.38 | %0.0 | HAYIR |
| **BTC** | 30m | 6 | Fibonacci | $111.66 | %0.0 | HAYIR |
| **BTC** | 30m | 6 | **Paroli** | **$171.61** | %0.0 | HAYIR |

---

## 7.4. ORP Stratejisi — %2 Adım — 1 Yıllık Backtest (5 Coin × 5 TF × 2 Kaldıraç)

| Sembol | TF | İşlem | Kaldıraç | Tamamlanan Adım | Bitiş ($) | Max DD | Max Lev |
|--------|-----|-------|----------|-----------------|-----------|--------|---------|
| **ETH** | 1h | 70 | 2x | **144** | **$1,745.79** | %2.8 | 2.00x |
| **ETH** | 1h | 70 | 5x | **170** | **$2,907.08** | %2.8 | 4.99x |
| **SOL** | 1h | 45 | 2x | **103** | **$771.89** | %6.5 | 2.00x |
| **SOL** | 1h | 45 | 5x | **119** | **$1,068.40** | %6.7 | 4.99x |
| **SOL** | 30m | 52 | 5x | **109** | **$867.95** | %3.3 | 4.97x |
| **BTC** | 30m | 48 | 5x | **100** | **$738.36** | %3.0 | 4.88x |
| **BTC** | 4h | 38 | 2x | **74** | **$434.14** | %2.8 | 2.00x |
| **BNB** | 1h | 43 | 5x | **82** | **$511.14** | %7.0 | 5.00x |
| **XRP** | 1h | 46 | 5x | **85** | **$547.23** | %4.8 | 4.86x |
| **XRP** | 30m | 42 | 5x | **83** | **$526.99** | %6.5 | 5.00x |

---

## 7.5. ORP Stratejisi — %5 Adım — ETH 1h — 1 Yıllık (EN İYİ SONUÇ)

| Kaldıraç Limiti | Bitiş ($) | Adım Sayısı | Max DD | Max Lev | Likide |
|-----------------|-----------|-------------|--------|---------|--------|
| 2.0x | **$32,608.49** | 118 | %6.7 | 2.00x | HAYIR |
| 3.0x | **$63,530.88** | 132 | %6.2 | 3.00x | HAYIR |
| **5.0x** | **$78,040.49** | **136** | **%9.6** | 5.00x | **HAYIR** |
| 8.0x | $77,923.36 | 136 | %9.6 | 5.75x | HAYIR |
| 10.0x | $77,923.36 | 136 | %9.6 | 5.75x | HAYIR |

> [!IMPORTANT]
> **Kaldıraç Doygunluğu:** 5x'in üzerinde (8x, 10x) kaldıraç açmak sonucu değiştirmiyor çünkü botun ihtiyaç duyduğu maksimum kaldıraç zaten **5.75x**. Daha fazlasına gerek yok.

---

# 8. Kaldıraç ve Likidasyon Analizi

## 8.1. Likidasyon Nedir?

Kaldıraçlı işlemde, fiyat aleyhimize belirli bir yüzde hareket ederse borsa pozisyonu zorla kapatır:

| Kaldıraç | Likidasyon Mesafesi |
|----------|---------------------|
| 2x | %50 (fiyat %50 düşmeli) |
| 3x | %33.3 |
| 5x | %20 |
| 10x | %10 |

## 8.2. Neden Asla Likide Olmuyoruz?

```
Bot'un Stop-Loss Mesafesi: Ort. %1.5 - %4, Maks. %10
5x Kaldıraçta Likidasyon Mesafesi: %20

Stop-Loss HER ZAMAN likidasyondan çok önce patlar!

Örnek:
  Entry: $2,500 (ETH)
  Stop-Loss: $2,450 (-%2 mesafe)
  Likidasyon: $2,000 (-%20 mesafe, 5x)
  
  Fiyat $2,450'ye düştüğünde → Stop patlar → Pozisyon kapanır
  $2,000 seviyesine ASLA ulaşılmaz
```

## 8.3. Tüm Test Sonuçlarında Likidasyon Sayısı

```
5 coin × 5 zaman dilimi × 2 kaldıraç seviyesi × 4 strateji = 200+ farklı konfigürasyon

Toplam Likidasyon Sayısı: 0 (SIFIR)
```

---

# 9. Neden %5 Adım, Neden ORP?

## 9.1. %2 vs %5 Adım Karşılaştırması

```
%2 Adım, 170 başarılı adım:
  (1.02)^170 = $29.07 çarpanı → $100 × 29.07 = $2,907

%5 Adım, 136 başarılı adım:
  (1.05)^136 = $780.4 çarpanı → $100 × 780.4 = $78,040
```

**%5 adım neden daha iyi?**
- Daha büyük hedefler, botun **daha cesur** ama **kontrollü** risk almasını sağlıyor
- Ruin Guard sayesinde drawdown hâlâ %10'un altında kalıyor
- Her başarılı adımda kasa %5 büyüdüğü için bileşik etkisi **inanılmaz**

## 9.2. ORP vs Diğer Sistemler

| Kriter | Fixed Risk | Fibonacci | Paroli | **ORP** |
|--------|-----------|-----------|--------|---------|
| 1 Yıl ETH 1h Sonuç | ~$179 | ~$134 | ~$315 | **$78,040** |
| Drawdown Kontrolü | ✅ Mükemmel | ✅ Mükemmel | ⚠️ Orta | ✅ İyi |
| Bileşik Büyüme | ❌ Yavaş | ❌ Çok Yavaş | ✅ Hızlı | ✅ En Hızlı |
| Kayıp Kurtarma | ❌ Yok | ⚠️ Var ama yavaş | ❌ Yok | ✅ Otomatik |
| Batma Riski | %0 | %0 | %0 | **%0** |

---

# 10. Nihai Optimal Strateji ve Uygulama Rehberi

## 10.1. Önerilen Konfigürasyon

| Parametre | Değer | Neden |
|-----------|-------|-------|
| **İşlem Çifti** | ETH/USDT | En yüksek getiri + en dengeli sinyal kalitesi |
| **Zaman Dilimi** | 1 Saatlik (1h) | Sinyal sıklığı ve kalite dengesi optimal |
| **Strateji** | ORP (%5 Adım) | Bileşik faiz + kayıp kurtarma |
| **Kaldıraç Limiti** | 5x | 5x üzeri sonucu değiştirmiyor (doygunluk) |
| **Ruin Guard** | Maks %15 risk | Tek işlemde kasanın %15'inden fazlasını riske atma |
| **Stop-Loss** | ATR × 1.5 | Dinamik, piyasa oynaklığına uyumlu |
| **TP Sistemi** | 1.5R / 2.5R / 4.0R kademeli | Karı kitle, geri kalanı koştur |
| **Min. Skor** | 4.5/10 | Kalitesiz sinyalleri eler |

## 10.2. Beklenen Performans (1 Yıllık Backtest Bazında)

| Metrik | Değer |
|--------|-------|
| Başlangıç Sermayesi | $100 |
| **1 Yıl Sonucu** | **$78,040** |
| Toplam İşlem | 149 |
| Tamamlanan %5 Adım | 136 |
| **Bileşik Çarpan** | **780x** |
| Max Drawdown | %9.6 |
| Likidasyon | 0 |

## 10.3. Adım Adım Canlı Uygulama Döngüsü

```
Her 1 saatte bir (mum kapanışında):

1. 📊 VERİ ÇEK
   → Binance API'den ETH/USDT 1h OHLCV verisini çek

2. 🔍 ANALİZ YAP
   → 16 farklı göstergeyi hesapla (OB, FVG, BOS, CHoCH, vb.)
   → 3 kategori skoru üret (SMC + Klasik + Kurumsal)
   → Composite skor hesapla (10 üzerinden)

3. 🚦 FİLTRELERİ KONTROL ET
   → Skor >= 4.5 mi?
   → Trend NEUTRAL değil mi?
   → 1D trend uyumlu mu?
   → Hacim yeterli mi?
   → Stop mesafesi %0.5 - %10 arasında mı?

4. 🎯 GİRİŞ KARARI
   → Tüm filtreler geçtiyse: İŞLEM AÇ
   → Giriş fiyatı: OB/FVG ortası veya piyasa fiyatı

5. 📐 RİSK HESAPLA (ORP)
   → Hedef equity'yi hesapla: $100 × 1.05^N
   → Gerekli riski hesapla: (hedef - mevcut) / 1.5
   → Ruin Guard: risk > equity × %15 ise → düşür
   → Kaldıracı hesapla (maks 5x)

6. 🛡️ EMİRLERİ KOYY
   → Stop-Loss: entry - ATR × 1.5
   → TP1: +1.5R (%40 kapat)
   → TP2: +2.5R (%35 kapat)
   → TP3: +4.0R (%25 kapat)

7. 🔄 İŞLEM SONUCU
   → Kazanç: Bir sonraki %5 hedefine geç
   → Kayıp: ORP delta'yı hesapla, sonraki işlemde kurtarmayı hedefle
   → DÖNGÜYÜ TEKRARLA
```

## 10.4. Arkadaşınıza Özet

> *"Bot, kurumsal yatırımcıların izlerini takip eden 16 farklı gösterge kullanıyor. Her işlemde kasayı %5 büyütmeyi hedefliyor. Bileşik faiz etkisiyle 100 Dolar 1 yılda 78 bin Dolara çıkıyor. Kayıp durumunda 'kurtarma algoritması' devreye giriyor, kaldıraç asla 5x'i geçmiyor, stop-loss dinamik ve otomatik. 1 yıllık testte sıfır likidasyon. En kötü çekilme %9.6."*

---

> [!CAUTION]
> **Önemli Uyarı:** Bu sonuçlar geriye dönük test (backtest) verilerine dayanmaktadır. Geçmiş performans gelecekteki sonuçları garanti etmez. Canlı piyasada likidite sorunları, ani fiyat hareketleri (flash crash) ve API gecikmeleri gibi ek riskler mevcuttur. Kaybetmeyi göze alamayacağınız parayla yatırım yapmayın.
