# AGENT TALİMATLARI — ALPHA İSTİHBARAT SİSTEMİ v3

Bu dosya Claude Code ve diğer AI agent'ların bu proje üzerinde çalışırken uyması gereken kuralları ve önemli bağlamı içerir.

---

## Proje Özeti

`/Users/uygar/trade` — Kripto Futures + BIST sinyal analiz sistemi.

- **Ana giriş noktası:** `run_engine.py` (⭐ Yeni OOP Motor v3)
- **Klasik giriş:** `live_scan.py` (standalone, bağımlılıksız)
- **Dil:** Python 3.9 (`python3` komutu)
- **Venv:** `source venv/bin/activate` ile aktif et
- **Config:** `.env` dosyası (ortam değişkenleri)
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

**Ayrıca: dict erişimi f-string içinde çalışmaz — önce değişkene ata:**

```python
# YANLIŞ:
f"${port[\"final_eq\"]:>10,.0f}"

# DOĞRU:
final_eq_s = f"${port['final_eq']:>10,.0f}"
```

### pandas-ta Kullanılamaz

`pandas-ta` Python 3.9 ile uyumsuzdur. Tüm indikatörler saf `numpy`/`pandas` ile implement edilir:

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

# Backtest'te bar-by-bar:
df_slice = df_full.iloc[:i]   # Bar i görülmez; sinyal i-1'de
signal   = analyze(df_slice)
entry    = df_full.iloc[i]    # i'de giriş simüle edilir
```

---

## Sistem Mimarisi

```
trade/
├── run_engine.py               ← ⭐ ANA CLI — Optimal Sinyal Motoru v3
├── live_scan.py                ← Standalone SMC/ICT tarayıcı
├── main.py                     ← Klasik CLI (--loop, --symbol, --backtest)
│
├── bot/
│   ├── engine/                 ← ⭐ OOP Motor Paketi (v3)
│   │   ├── __init__.py         ← Paket arayüzü (SignalEngine, SignalResult…)
│   │   ├── base.py             ← Enum + Dataclass tanımları
│   │   ├── market_structure.py ← MarketStructureAnalyzer (SMC/ICT sarmalayıcı)
│   │   ├── confluence.py       ← ConfluenceScorer (8 gösterge, ağırlıklı)
│   │   ├── filters.py          ← TradeFilter (L1–L6 hard gate)
│   │   ├── position_sizer.py   ← PositionSizer (Kelly + ATR)
│   │   ├── signal_engine.py    ← SignalEngine (orkestratör)
│   │   └── reporter.py         ← Terminal çıktı formatlayıcı
│   ├── advanced_indicators.py  ← IB, ADR, POC, OI, Funding, Session, VWAP, Wyckoff
│   ├── signal_engine.py        ← v2 katman (geriye uyumlu)
│   └── risk_manager.py         ← Dinamik pozisyon boyutlama
│
├── agents/
│   ├── debate.py               ← Bull/Bear/PM multi-agent münazara (Ollama)
│   └── ollama_client.py        ← Yerel LLM istemcisi
│
├── backtest_enhanced.py        ← ⭐ Gerçekçi Walk-Forward Backtest v2
├── backtest_portfolio.py       ← v1 portföy backtest (referans)
├── paper_trader.py             ← Kağıt işlem simülatörü
├── bist_engine.py              ← BIST hisse analiz motoru
│
├── analysis/                   ← Klasik indikatör modülleri
├── market/                     ← Veri çekme (ccxt + yfinance)
├── signals/                    ← Pozisyon sizer, trade setup
├── nlp/                        ← Sentiment + entity extraction
├── data/                       ← Web scraper, YouTube, SQLite
└── output/                     ← Email (Gmail SMTP), konsol çıktı
```

---

## Temel Dosyalar (v3)

| Dosya | Amaç |
|-------|------|
| `run_engine.py` | ⭐ Yeni CLI — OOP motor ile tam analiz |
| `bot/engine/signal_engine.py` | SignalEngine orkestratör sınıfı |
| `bot/engine/base.py` | Enum (Trend, Session, Action) + Dataclass'lar |
| `bot/engine/market_structure.py` | MarketStructureAnalyzer — SMC skor hesabı |
| `bot/engine/confluence.py` | ConfluenceScorer — 8 ağırlıklı gösterge |
| `bot/engine/filters.py` | TradeFilter — L1–L6 hard gate filtreleri |
| `bot/engine/position_sizer.py` | PositionSizer — Kelly Criterion + ATR |
| `bot/engine/reporter.py` | Terminal çıktı formatlayıcı |
| `backtest_enhanced.py` | Walk-forward backtest, ATR SL, trailing stop |
| `paper_trader.py` | Kağıt işlem — gerçek Binance fiyatları |
| `live_scan.py` | Standalone tarayıcı (bağımlılıksız) |
| `main.py` | Klasik CLI entrypoint |

---

## Komutlar

```bash
# Venv aktif et (her zaman önce bunu yap)
source venv/bin/activate

# ──── Optimal Sinyal Motoru v3 (ÖNERİLEN) ────────────────────────
python run_engine.py --symbol ETH/USDT          # Tek sembol analiz
python run_engine.py --scan --balance 500        # Tüm watchlist tarama
python run_engine.py --scan --min-score 6.5      # Yüksek kalite filtresi
python run_engine.py --scan --min-confirmations 3
python run_engine.py --scan --llm                # Ollama ile LLM debate

# ──── Gerçekçi Backtest ──────────────────────────────────────────
python backtest_enhanced.py                      # ATR SL + trailing stop

# ──── Kağıt İşlem ───────────────────────────────────────────────
python paper_trader.py                           # 4H döngüsel
python paper_trader.py --report                  # İstatistikler
python paper_trader.py --now                     # Tek döngü

# ──── Diğer ─────────────────────────────────────────────────────
python bist_engine.py                            # 20 BIST hissesi tarama
python live_scan.py                              # Standalone tarayıcı
python main.py --loop                            # APScheduler döngüsü

# ──── Syntax Kontrolü ────────────────────────────────────────────
python3 -c "import ast; ast.parse(open('run_engine.py').read()); print('OK')"
python3 -c "import ast; ast.parse(open('backtest_enhanced.py').read()); print('OK')"
python3 -c "import ast; ast.parse(open('bot/engine/signal_engine.py').read()); print('OK')"
```

---

## OOP Engine API

```python
from bot.engine import SignalEngine

engine = SignalEngine(
    min_score         = 5.5,     # Minimum sinyal skoru (0-10)
    min_confirmations = 2,       # Minimum confluence onayı
    balance           = 500.0,   # USDT bakiyesi
    use_llm           = False,   # Ollama isteğe bağlı
)

# Tek sembol analiz
result = engine.analyze("ETH/USDT")
if result:
    print(result.action)        # Action enum
    print(result.composite)     # 0-10 skor
    print(result.entry_price)   # Giriş fiyatı
    print(result.sl)            # Stop-loss
    print(result.tp1, result.tp2, result.tp3)  # TP seviyeleri

# Watchlist tarama
results = engine.scan_watchlist(["BTC/USDT", "ETH/USDT", "SOL/USDT"])
```

### Önemli Enum Değerleri

```python
from bot.engine.base import Trend, Action, Session

# Trend
Trend.BULLISH / Trend.BEARISH / Trend.NEUTRAL

# Action (sinyal kararı)
Action.STRONG_BUY   # composite >= 7.5
Action.BUY          # composite >= 5.5
Action.HOLD         # yetersiz sinyal
Action.SELL         # SHORT sinyali
Action.STRONG_SELL  # güçlü SHORT sinyali
Action.BLOCKED      # Hard gate filtresi engelledi

# Session
Session.LONDON / Session.NEW_YORK / Session.ASIA / Session.OFF
```

---

## Hard Gate Filtreleri (TradeFilter)

| Katman | Kural | Eylem |
|--------|-------|-------|
| **L1** | Veri kalitesi, yeterli bar sayısı, NaN kontrolü | Engelle |
| **L2** | ADR >%100 kullanılmış (piyasa tükenmiş) | Engelle |
| **L3** | Funding rate yön karşıtı aşırılık (FR > 0.08% LONG için) | Engelle |
| **L4** | Confluence onay sayısı yetersiz (< min_confirmations) | Engelle |
| **L5** | SL mesafesi geçersiz (%0.5–%8 aralığı dışı) | Engelle |
| **L6** | Asia saati / seans dışı (%00–04 UTC) | Uyarı |

**`evaluate_early(df, ms, funding_rate=None)`** — L1/L3/L5 erken kontrol (confluence öncesi)  
**`evaluate(df, ms, cs, funding_rate=None)`** — Tam L1-L6 kontrol (confluence sonrası)

---

## SL/TP Sistemi (ATR Tabanlı)

```
SL   = Giriş − ATR × 1.5   (LONG)
       Giriş + ATR × 1.5   (SHORT)
       (yakın OB/FVG sınırı daha korunaklıysa onu kullan)

TP1  = risk_dist × 1.5  → %40 kapat, SL → breakeven
TP2  = risk_dist × 2.5  → %35 kapat, trailing aktif
TP3  = risk_dist × 4.0  → kalan %25 kapat
Trail= ATR × 1.2 mesafeli takip (TP1 sonrası)
```

### Backtest Sabitleri (backtest_enhanced.py)

```python
SL_ATR_MULT      = 1.5    # SL = entry ± ATR × 1.5
TP1_R            = 1.5    # TP1 hedefi (risk mesafesi × 1.5)
TP2_R            = 2.5    # TP2 hedefi
TP3_R            = 4.0    # TP3 hedefi
TRAIL_ATR        = 1.2    # Trailing stop = ATR × 1.2
TP1_CLOSE        = 0.40   # TP1'de %40 kapat
TP2_CLOSE        = 0.35   # TP2'de %35 kapat
TP3_CLOSE        = 0.25   # TP3'te %25 kapat
COMMISSION       = 0.0004  # %0.04 taker
SLIPPAGE         = 0.0005  # %0.05 slippage
EMA_TREND_PERIOD = 200    # 4H EMA200 (1D EMA50 proxy)
VOL_MULT         = 1.2    # Volume > 20-bar avg × 1.2
MIN_SCORE        = 4.5    # Minimum sinyal skoru (backtest)
```

---

## Pozisyon Boyutlama (PositionSizer)

```
Risk/İşlem  : %2 sabit (Kelly Criterion ile hafif dinamik)
Max risk    : %3 (üst sınır)
Min risk    : %1 (alt sınır)
Max pozisyon: 4 eş zamanlı

Kaldıraç kuralı (sinyal skoruna göre):
  Skor 8–10  → maks 5x
  Skor 6.5–8 → maks 4x
  Skor 5.5–6.5 → maks 3x
  Skor < 5.5 → maks 2x

Kelly: kelly_f = max(0, (wr - (1-wr)/rr) × 0.25)
Komisyon: %0.04 taker + %0.05 slippage (round-trip ~%0.18)
```

---

## Puanlama Sistemi (v3)

```
Composite = SMC_score × 0.55 + Confluence_score × 0.45

SMC Layer (max ~10):
  BOS         +2.0  Trend yönünde yapı kırılması
  CHoCH       +1.5  Trend tersine dönüş işareti
  MSS         +1.0  İç yapıda erken kırılma
  Order Block +2.0  Güçlü hareketten önceki son kontra mum
  FVG         +1.5  Fair Value Gap (3-mum boşluğu)
  BSL/SSL     +1.0  Equal high/low taraması (likidite avı)
  OTE         +0.5  Fib 0.618–0.786 optimal giriş
  Breaker     +1.0  Kırılmış OB direnç/destek
  Displacement+0.5  >2.5×ATR tek mum (market maker)

Confluence Layer (8 gösterge, ağırlıklı):
  IB     12%  Initial Balance kırılma/reddi
  ADR    13%  Günlük aralık tükenmesi
  POC    18%  Hacim profili + OB/FVG çakışması
  OI     15%  Open Interest delta yönü
  FR     14%  Funding rate kontrarian fırsat
  Seans  12%  Kill Zone saati ağırlığı
  VWAP   10%  ±2σ uç sapma
  Wyckoff 6%  Spring/UTAD kurumsal desen

Sinyal Eşikleri:
  STRONG_BUY  ≥ 7.5
  BUY         ≥ 5.5
  HOLD        < 5.5
```

---

## Backtest Sonuçları (v3 — Gerçekçi)

**Dönem:** Ocak 2026 → Mayıs 2026 · 8 sembol · 4H · 93 işlem

| Metrik | Sonuç |
|--------|-------|
| Kazanma Oranı | **81.7%** (76W / 17L) |
| Profit Factor | **10.08** |
| Max Drawdown | **10.5%** |
| Sharpe Ratio | **38.12** |
| Net Getiri | **+2,126.7%** (komisyon + slippage dahil) |

Exit Tipi: 62% WIN_TRAIL · 16% WIN_TP3 · 3% WIN_BREAKEVEN · 18% LOSS

---

## İşlem Zaman Planı (4H Futures)

```
UTC    Türkiye (UTC+3)   Öncelik   Neden
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
00:00  03:00             ATLA      Asya düşük likidite
04:00  07:00             DÜŞÜK     Asya sonu
08:00  11:00             ⭐ YÜKSEK  Londra Açılış Kill Zone
12:00  15:00             ⭐ YÜKSEK  NY Açılış Kill Zone
16:00  19:00             ⭐⭐ MAX    Londra/NY çakışma
20:00  23:00             ORTA      NY kapanış öncesi
```

**Manuel:** ~30–40 dk/gün (3 seans × 10 dak inceleme)

---

## Değişiklik Yaparken

1. Düzenleme sonrası syntax kontrolü çalıştır:
   ```bash
   python3 -c "import ast; ast.parse(open('DOSYA.py').read()); print('OK')"
   ```
2. Python 3.9 f-string kısıtlamasını kontrol et — iç içe tırnak/backslash YASAK
3. Anti-repainting kuralını ihlal etme — `iloc[-2]` veya `shift(1)` kullan
4. `live_scan.py`'de tüm indikatörler saf numpy/pandas — harici lib ekleme
5. `bot/engine/` altındaki dosyaları değiştirince `__init__.py` export'larını kontrol et
6. `backtest_enhanced.py`'de sabit adlarına dikkat: `TRAIL_ATR` (TRAIL_R değil)

---

## Bilinen Sorunlar

- `pandas-ta` Python 3.9'da kurulmaz → `ta` veya manuel implement kullan
- BIST 4H verisi yfinance'den 1H resample ile gelir — daha az mum
- CoinGecko trending bazen `requests` timeout atar — try/except ile sarılmış
- OI/Funding verisi sadece Binance Futures sembollerinde çalışır

---

## Ortam Değişkenleri

```
EMAIL_SENDER           Gmail adresi (zorunlu)
EMAIL_APP_PASSWORD     Gmail Uygulama Şifresi / 2FA (zorunlu)
EMAIL_RECIPIENT        Bildirim alacak adres (zorunlu)
BINANCE_API_KEY        Binance (opsiyonel — public API de çalışır)
BINANCE_SECRET         Binance secret (opsiyonel)
ANTHROPIC_API_KEY      Claude API (opsiyonel)
OLLAMA_BASE_URL        Yerel LLM (varsayılan: localhost:11434)
YOUTUBE_API_KEY        YouTube Data API v3 (opsiyonel)
COINGECKO_API_KEY      CoinGecko Pro (opsiyonel)
```

---

## Veri Kaynakları

| Kaynak | Veri | Ücretsiz |
|--------|------|:---:|
| Binance (ccxt) | OHLCV, Funding Rate, Open Interest | ✅ |
| yfinance | BIST hisseleri | ✅ |
| CryptoPanic API | Kripto haberleri | ✅ |
| CoinGecko API | Trending coins | ✅ |
| CoinTelegraph / CoinDesk | Web scraping | ✅ |
| YouTube Transcript | Transkript analizi | ✅ |
