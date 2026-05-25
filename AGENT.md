# AGENT TALİMATLARI — ALPHA İSTİHBARAT SİSTEMİ

Bu dosya Claude Code ve diğer AI agent'ların bu proje üzerinde çalışırken uyması gereken kuralları ve önemli bağlamı içerir.

---

## Proje Özeti

`/Users/uygar/trade` — Kripto + BIST trade analiz sistemi.

- **Giriş noktası:** `live_scan.py` (standalone) veya `python main.py`
- **Dil:** Python 3.9 (`python3` komutu)
- **Venv:** `source venv/bin/activate` ile aktif et
- **Config:** `config/settings.yaml`
- **DB:** `data/database/alpha.db` (SQLite)
- **Çıktı:** Gmail SMTP + konsol (Telegram YOK)

---

## Kritik Kısıtlamalar

### Python 3.9 Uyumluluğu

**F-string içinde backslash kullanılamaz.** Her zaman değişkene çek:

```python
# YANLIŞ (Python 3.9'da SyntaxError):
print(f"  {warn(f'{r[\"sl\"]:.4f}')}")

# DOĞRU:
sl_s = f"{r['sl']:.4f}"
print(f"  {warn(sl_s)}")
```

### pandas-ta Kullanılamaz

`pandas-ta` Python 3.9 ile uyumsuzdur. `live_scan.py` tüm indikatörleri saf `numpy`/`pandas` ile implement eder:

```python
def ema(s, p): return s.ewm(span=p, adjust=False).mean()
def rsi_fn(s, p=14): ...
def macd_fn(s, f=12, sl=26, sig=9): ...
def atr_fn(df, p=14): ...
```

Proje modüllerinde (`analysis/`) `ta` kütüphanesi kullanılır — `pandas-ta` değil.

### Anti-Repainting Garantisi

**Kural:** Hiçbir hesaplama son açık mumu görmemelidir.

```python
# Binance'den veri çekerken:
return df.iloc[:-1].astype(float)   # Son mum (açık) kesilir

# İndikatör okurken:
val = float(series.shift(1).iloc[-1])   # Bir önceki kapanmış değer

# SMC hesabında:
rc = df["close"].iloc[-4:-1]   # Son 3 kapanmış mum
```

---

## Temel Dosyalar

| Dosya | Amaç |
|-------|------|
| `live_scan.py` | Standalone tarayıcı — tüm mantık tek dosyada, bağımlılıksız |
| `main.py` | CLI entrypoint — `--loop`, `--symbol`, `--backtest`, `--status` |
| `main_engine.py` | `run_full_scan()`, `analyze_symbol()` |
| `config/settings.yaml` | Tüm parametreler buradan okunur |
| `analysis/smc_engine.py` | SMC/ICT motoru |
| `analysis/classic_indicators.py` | Klasik teknik indikatörler (`ta` lib) |
| `signals/claude_synthesizer.py` | Claude API — skor ≥ 6.0 ise çağrılır |
| `output/email_notifier.py` | Gmail SMTP HTML email |
| `data/database/db.py` | SQLite CRUD — `init_db()`, `save_signal()` |
| `backtest/engine.py` | Walk-forward backtest, anti-repainting |
| `.env.example` | Ortam değişkenleri şablonu |

---

## Komutlar

```bash
# Çalıştır
source venv/bin/activate
python live_scan.py              # Hızlı tarama (standalone)
python main.py                   # Modüler sistem — tek tarama
python main.py --loop            # Sürekli tarama (APScheduler)
python main.py --symbol BTC/USDT # Tek sembol
python main.py --status          # Son sinyaller

# Syntax kontrolü (düzenleme sonrası her zaman çalıştır)
python3 -c "import ast; ast.parse(open('live_scan.py').read()); print('OK')"

# Test
source venv/bin/activate && python3 live_scan.py 2>&1 | head -80
```

---

## Puanlama Sistemi

```
Composite = (SMC_s + Classic_s + Inst_s + MTF_s + Social_s) / 37 * 10

SMC     max 10   BOS+2, CHoCH+1, MSS+1, OB+2, Breaker+1, FVG+1, Sweep+2, OTE+1, DZ+1, Wyckoff+1, Disp+0.5
Classic max 10   EMA full+2/kısmi+1, MACD bull+2/pos+1, RSI hid_div+2/div+1/OS+0.5, Stoch+1, BB+1, VWAP+1, OBV+1, MACD_div+1
Inst    max  7   CVD+2, FR nötr+1/squeeze+1, fiyat uptrend+2, VPOC yakını+1
MTF     max  4   3TF tam+4, 2TF+2, 1TF+1
Social  max  6   Sentiment + mention sayısı
```

Sinyal eşikleri: **8.0** Güçlü | **6.0** Orta | **4.0** İzlemelık | **<4.0** Yok

---

## Trade Setup Mantığı

```
BULLISH:
  Entry = Bull OB bölgesi (veya Bull FVG)
  SL    = OB_low * 0.995
  TP1   = entry_mid * 1.06  (+%6)   → %40 kapat
  TP2   = entry_mid * 1.14  (+%14)  → %35 kapat
  TP3   = entry_mid * 1.28  (+%28)  → %25 kapat

BEARISH:
  Entry = Bear OB bölgesi (veya Bear FVG)
  SL    = OB_high * 1.005
  TP1   = entry_mid * 0.94  (−%6)
  TP2   = entry_mid * 0.86  (−%14)
  TP3   = entry_mid * 0.72  (−%28)
```

---

## Bileşik Faiz Strateji Katmanı

`live_scan.py` BÖLÜM 6'da implement edilmiş fonksiyonlar:

```python
kelly_f(win_rate, rr)                    # Yarım-Kelly fraksiyonu
geo_mult(win_rate, rr, r, n)             # n işlem geometrik büyüme çarpanı
dd_estimate(win_rate, rr, r, n)          # Max drawdown normal yaklaşım
multi_tf_compound_plan(results, social)  # Portfolio + projeksiyon hesabı
print_compound_strategy(plan)            # Konsol çıktısı
```

Projeksiyonlar **sabit %2 risk** (gerçekçi) ve **yarım-Kelly** (teorik) olarak ikili gösterilir.

---

## Sosyal Keşif Mantığı

1. CryptoPanic, CoinTelegraph, CoinDesk, BTCHaber, CoinGecko Trending scrape edilir
2. 30+ kripto için mention sayısı hesaplanır (CRYPTO_MAP + ALIAS)
3. BTC/ETH/SOL sabit taranır; en çok mention alan 4 coin otomatik eklenir
4. TR/EN/DE keyword sentiment (BULL_W, BEAR_W, BULL_TR, BEAR_TR)
5. Soc score: 0–6 puan (sentiment + mention derinliği)

---

## Veri Kaynakları

| Kaynak | Veri | Ücretsiz |
|--------|------|:---:|
| Binance (ccxt) | OHLCV, Funding Rate, OI | ✅ |
| yfinance | BIST hisseleri | ✅ |
| CryptoPanic API | Kripto haberleri | ✅ |
| CoinGecko API | Trending coins | ✅ |
| CoinTelegraph | Web scraping | ✅ |
| CoinDesk | Web scraping | ✅ |
| BTCHaber | Web scraping (TR) | ✅ |
| YouTube Transcript | Transkript analizi | ✅ |
| YouTube Data API | Kanal videoları | Opsiyonel |

---

## Değişiklik Yaparken

1. `live_scan.py` düzenlendikten sonra syntax kontrolü çalıştır
2. Python 3.9 f-string kısıtlamasını kontrol et (iç içe tırnak/backslash)
3. Anti-repainting kuralını ihlal etme — her zaman `shift(1)` veya `iloc[:-1]`
4. `live_scan.py`'de tüm indikatörler saf numpy/pandas — harici lib ekleme
5. Yeni sinyal türü eklenince puanlama toplamını (37) güncelle

---

## Bilinen Sorunlar

- `pandas-ta` Python 3.9'da kurulmaz → `ta` veya manuel implement kullan
- BIST 4H verisi yfinance'den 1H resample ile gelir — daha az mum
- CoinGecko trending bazen `requests` timeout atar — try/except ile sarılmış
- Playwright kurulumu opsiyonel — kurulamasa da sistem çalışır

---

## Ortam Değişkenleri

```
ANTHROPIC_API_KEY      Claude API
BINANCE_API_KEY        Binance (opsiyonel — public da çalışır)
BINANCE_SECRET         Binance secret
YOUTUBE_API_KEY        YouTube Data API v3
EMAIL_SENDER           Gmail adresi (abc@gmail.com)
EMAIL_APP_PASSWORD     Gmail Uygulama Şifresi (2FA gerekli)
EMAIL_RECIPIENT        Bildirim alacak adres
COINGECKO_API_KEY      CoinGecko Pro (opsiyonel)
```
