# ALPHA İSTİHBARAT SİSTEMİ

**Kripto + BIST için SMC/ICT tabanlı otonom trade analiz sistemi.**

Web scraping ile sosyal istihbarat, Advanced SMC motoru, Kelly Kriteri bileşik büyüme hesabı ve Gmail email bildirimleri içerir. Ücretli API gerektirmez.

---

## Özellikler

### Teknik Analiz Katmanları
| Katman | Maksimum Puan | İçerik |
|--------|:---:|--------|
| **SMC / ICT** | 10 | BOS, CHoCH, MSS, Order Block, Breaker Block, FVG, Liquidity Sweep, OTE (Fib 0.618–0.786), Displacement, Wyckoff Fazı |
| **Klasik** | 10 | EMA Ribbon (8/21/55/200), MACD, RSI + Diverjans, Bollinger, VWAP, OBV, Stoch RSI |
| **Kurumsal** | 7 | CVD (yaklaşık), Funding Rate, Open Interest Proxy, Volume Profile (VPOC/VAH/VAL) |
| **Multi-TF** | 4 | 1W / 1D / 4H / 1H trend konfirmasyonu |
| **Sosyal** | 6 | Web scraping + sentiment (TR/EN/DE) + mention sayısı |
| **TOPLAM** | **37** → normalize **10** | |

### Sinyal Eşikleri
| Seviye | Skor | Aksiyon |
|--------|------|---------|
| 🚨 GÜÇLÜ | ≥ 8.0 | Trade setup + Email + Claude sentezi |
| 📊 ORTA | ≥ 6.0 | Email bildirim |
| 👁 İZLEMELİK | ≥ 4.0 | Konsol çıktısı |
| 📉 SİNYAL YOK | < 4.0 | — |

### Bileşik Faiz Strateji Motoru
Her tarama sonunda otomatik çalışır:
- **Kelly Kriteri** — `f* = (p·b − q) / b`
- **Geometrik büyüme** — `C_n = C₀ · [(1+b·r)^p · (1−r)^(1−p)]^n`
- 30 / 90 / 180 / 365 gün projeksiyonları (sabit %2 risk + Kelly versiyonu)
- Long + Short portfolio dengesini ayrı tablolar
- Max drawdown tahmini (normal dağılım yaklaşımı)

---

## Kurulum

```bash
git clone https://github.com/uSoyrac/tirad.git
cd tirad
bash setup.sh
```

`setup.sh` şunları yapar: Python venv oluşturma, bağımlılıklar, spaCy modeli, `.env` şablonu.

### .env Yapılandırması

```bash
cp .env.example .env
# Sonra doldur:
```

| Değişken | Zorunlu | Açıklama |
|----------|:-------:|----------|
| `EMAIL_SENDER` | Evet | Gmail adresi |
| `EMAIL_APP_PASSWORD` | Evet | Gmail Uygulama Şifresi (2FA gerekli) |
| `EMAIL_RECIPIENT` | Evet | Bildirim alacak email |
| `ANTHROPIC_API_KEY` | Hayır | Skor ≥ 6.0 için Claude sentezi |
| `BINANCE_API_KEY` | Hayır | Public API de çalışır (limitli) |
| `YOUTUBE_API_KEY` | Hayır | YouTube kanal verisi (opsiyonel) |

---

## Kullanım

```bash
source venv/bin/activate

# Tek tarama (tüm liste)
python main.py

# Sürekli tarama (APScheduler: kripto 4s, BIST 1s, sosyal 6s)
python main.py --loop

# Tek sembol analiz
python main.py --symbol BTC/USDT
python main.py --symbol THYAO.IS

# Son 20 sinyali göster
python main.py --status

# Backtest (tüm watchlist)
python main.py --backtest

# Standalone çok hızlı tarama (bağımlılıksız)
python live_scan.py
```

### live_scan.py — Standalone Tarayıcı

Hiçbir proje modülüne bağımlı olmayan bağımsız script. ADIM 1–7:

1. Web scraping (CryptoPanic, CoinTelegraph, CoinDesk, BTCHaber, CoinGecko)
2. Sentiment analizi (TR/EN/DE keyword)
3. BIST 4H analizi (yfinance)
4. Kripto Advanced SMC/ICT analizi (Binance)
5. Detaylı çıktı (her varlık)
6. Özet sinyal tablosu
7. **Bileşik Faiz Strateji Motoru**

---

## Mimari

```
trade/
├── live_scan.py          ← Standalone ileri seviye tarayıcı (önerilen)
├── main.py               ← CLI giriş noktası
├── main_engine.py        ← run_full_scan(), analyze_symbol()
├── scheduler.py          ← APScheduler döngüsü
├── config/
│   └── settings.yaml     ← Tüm parametreler
├── analysis/
│   ├── smc_engine.py     ← BOS/CHoCH/MSS/OB/FVG/Sweep/OTE
│   ├── classic_indicators.py  ← EMA/MACD/RSI/BB/VWAP/OBV
│   ├── institutional.py  ← CVD/FR/OI
│   └── composite_scorer.py   ← Puanlama füzyonu
├── market/
│   ├── data_fetcher.py   ← Binance (ccxt) + BIST (yfinance)
│   └── multi_tf_builder.py   ← 1W/1D/4H/1H veri seti
├── signals/
│   ├── trade_setup.py    ← Entry/SL/TP hesabı
│   ├── position_sizer.py ← %2 risk + kaldıraç
│   └── claude_synthesizer.py ← Claude API entegrasyonu
├── nlp/
│   ├── entity_extractor.py   ← Kripto/BIST mention tespiti
│   └── sentiment_analyzer.py ← FinBERT/BERTurk + keyword
├── data/
│   ├── collectors/
│   │   ├── web_scraper.py    ← CoinTelegraph/CoinDesk/BTCHaber
│   │   └── youtube_collector.py  ← Transkript analizi
│   └── database/db.py        ← SQLite (signals, mentions)
├── output/
│   ├── email_notifier.py     ← Gmail SMTP HTML email
│   └── console_printer.py    ← ANSI renkli terminal
├── backtest/engine.py    ← Walk-forward backtest (anti-repainting)
├── requirements.txt
├── setup.sh
└── .env.example
```

---

## Risk Yönetimi

- **Sabit %2 risk** — Her işlemde sermayenin maksimum %2'si riske girer
- **Max 5x kaldıraç** — Hard limit, konfigürasyonla değiştirilemez
- **Anti-repainting** — Tüm hesaplamalar yalnızca **kapanmış** mumlar üzerinde (`df.iloc[:-1]`)
- **SL limiti** — Girişten %8'den uzak SL'li setup iptal edilir
- **TP dağılımı** — %40 TP1'de kapat, SL'yi maliyete çek; %35 TP2; %25 TP3

---

## SMC / ICT Yapıları

| Yapı | Açıklama |
|------|----------|
| **BOS** | Break of Structure — trend yönünde yapı kırılması |
| **CHoCH** | Change of Character — trend tersine dönüyor |
| **MSS** | Market Structure Shift — iç yapıda erken kırılma |
| **Order Block** | Güçlü hareketten önceki son kontra mum |
| **Breaker Block** | Kırılmış OB — artık karşı yönde direnç/destek |
| **FVG** | Fair Value Gap — 3 mum boşluğu (unmitigated only) |
| **BSL/SSL Sweep** | Equal high/low'ların taranması (likidite avı) |
| **OTE** | Optimal Trade Entry — Fib 0.618–0.786 geri çekilme bölgesi |
| **Displacement** | >2.5x ATR büyüklüğünde tek mum (market maker aktivitesi) |
| **Wyckoff** | Birikim / Dağıtım faz tespiti |
| **Volume Profile** | VPOC, VAH, VAL (%70 değer alanı) |

---

## Desteklenen Varlıklar

**Kripto (Binance Futures):** BTC, ETH, SOL + sosyal keşif ile otomatik eklenen coinler (CryptoPanic + CoinGecko trending)

**BIST (yfinance `.IS` uzantısı):** THYAO, GARAN, EREGL, SASA, ASELS, KCHOL, BIMAS, TUPRS, AKBNK, ISCTR

---

## Gereksinimler

- Python 3.9+
- Binance hesabı **gerekmez** (public API yeterli)
- Gmail hesabı (App Password ile)
- Anthropic API key (opsiyonel — Claude sentezi için)

---

## Notlar

- BIST verileri `yfinance` ile çekilir; 4H verisi 1H'den resample edilir
- `live_scan.py` tüm indikatörleri saf `numpy`/`pandas` ile implement eder (`pandas-ta` gerektirmez)
- Claude API yalnızca skor ≥ 6.0 olan sinyaller için çağrılır (maliyet optimizasyonu)
- Telegram entegrasyonu yoktur — çıktı Gmail ve konsol
- SQLite veritabanı `data/database/alpha.db` konumundadır

---

*Anti-repainting garantili — Tüm analizler kapanmış mumlar üzerinde.*
