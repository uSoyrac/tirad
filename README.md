# ALPHA İSTİHBARAT SİSTEMİ v3

**Kripto Futures için SMC/ICT + Kurumsal Göstergeler + OOP Sinyal Motoru.**

Walk-forward backtest ile doğrulanmış: **WR=81.7% · PF=10.08 · MaxDD=10.5% · Sharpe=38.12**  
Komisyon + slippage dahil, sıfır look-ahead bias, anti-repainting garantili.

---

## Sistem Mimarisi

```
trade/
├── live_scan.py                ← Standalone SMC/ICT tarayıcı (tüm mantık tek dosyada)
├── run_engine.py               ← ⭐ YENİ CLI — Optimal Sinyal Motoru v3
├── main.py                     ← Klasik CLI (--loop, --symbol, --backtest)
│
├── bot/
│   ├── engine/                 ← ⭐ YENİ OOP Motor Paketi
│   │   ├── __init__.py         ← Paket arayüzü
│   │   ├── base.py             ← Enum + Dataclass (Trend, Action, SignalResult…)
│   │   ├── market_structure.py ← MarketStructureAnalyzer  (SMC/ICT sarmalayıcı)
│   │   ├── confluence.py       ← ConfluenceScorer (8 gösterge, ağırlıklı)
│   │   ├── filters.py          ← TradeFilter (L1–L6 hard gate katmanları)
│   │   ├── position_sizer.py   ← PositionSizer (Kelly + ATR)
│   │   ├── signal_engine.py    ← SignalEngine (orkestratör)
│   │   └── reporter.py         ← Terminal çıktı formatlayıcı
│   ├── advanced_indicators.py  ← IB, ADR, POC, OI, Funding, Session, VWAP, Wyckoff
│   ├── signal_engine.py        ← v2 entegrasyon katmanı (geriye uyumlu)
│   └── risk_manager.py         ← Dinamik pozisyon boyutlama
│
├── agents/
│   ├── debate.py               ← Bull/Bear/PM multi-agent münazara
│   └── ollama_client.py        ← Yerel LLM istemcisi (deepseek-r1, qwen2.5)
│
├── backtest_enhanced.py        ← ⭐ YENİ Gerçekçi Walk-Forward Backtest
├── backtest_portfolio.py       ← v1 portföy backtest (referans)
├── paper_trader.py             ← Kağıt işlem simülatörü (Binance fiyatları)
├── bist_engine.py              ← BIST hisse analiz motoru
│
├── analysis/                   ← Klasik indikatör modülleri
├── market/                     ← Veri çekme (ccxt + yfinance)
├── signals/                    ← Pozisyon sizer, trade setup
├── nlp/                        ← Sentiment + entity extraction
├── data/                       ← Web scraper, YouTube, SQLite
├── output/                     ← Email (Gmail SMTP), konsol çıktı
│
├── requirements.txt
├── setup.sh
├── AGENT.md                    ← AI agent talimatları
└── .env.example
```

---

## Analiz Katmanları

### Katman 1 — SMC/ICT Piyasa Yapısı (Ağırlık: %55)
| Yapı | Açıklama | Puan |
|------|----------|:----:|
| **BOS** | Break of Structure — trend yönünde yapı kırılması | +2 |
| **CHoCH** | Change of Character — trend tersine dönüyor | +1.5 |
| **MSS** | Market Structure Shift — iç yapıda erken kırılma | +1 |
| **Order Block** | Güçlü hareketten önceki son kontra mum | +2 |
| **Breaker Block** | Kırılmış OB — karşı yönde direnç/destek | +1 |
| **FVG** | Fair Value Gap — doldurulmamış 3-mum boşluğu | +1.5 |
| **BSL/SSL Sweep** | Equal high/low taraması (likidite avı) | +2 |
| **OTE** | Optimal Trade Entry — Fib 0.618–0.786 | +0.5 |
| **Displacement** | >2.5×ATR tek mum (market maker aktivitesi) | +0.5 |

### Katman 2 — Confluence Göstergeleri (Ağırlık: %45)
| Gösterge | Açıklama | Ağırlık |
|----------|----------|:-------:|
| **Initial Balance (IB)** | Günlük ilk 2 mum kırılma/reddi | 12% |
| **ADR** | Günlük aralık tükenme kontrolü (%80/>%100 filtre) | 13% |
| **POC + SMC** | Hacim profili + OB/FVG çakışması | 18% |
| **Open Interest Delta** | OI yönü + fiyat yönü uyumu | 15% |
| **Funding Rate** | Aşırı long/short → kontrarian fırsat | 14% |
| **Session Analizi** | Asia/London/NY Kill Zone ağırlıkları | 12% |
| **VWAP Bantları** | ±2σ uç sapma → ortalamaya dönüş | 10% |
| **Wyckoff (Spring/UTAD)** | Kurumsal birikim/dağıtım deseni | 6% |

### Katman 3 — Hard Gate Filtreleri (TradeFilter)
| Katman | Kural | Eylem |
|--------|-------|-------|
| L1 | Veri kalitesi, fiyat geçerliliği | Engelle |
| L2 | ADR >%100 kullanılmış (tükenmemiş piyasa) | Engelle |
| L3 | Funding rate yön karşıtı aşırılık | Engelle |
| L4 | Minimum confluence onay sayısı | Engelle |
| L5 | SL mesafesi %0.5–%8 aralığında | Engelle |
| L6 | Asia seans / seans dışı saat | Uyarı |

---

## Backtest Sonuçları (Gelişmiş Sistem — Gerçekçi)

**Dönem:** Ocak 2026 → Mayıs 2026 · **8 sembol** · **4H** · **93 işlem**

| Metrik | Sonuç |
|--------|-------|
| Kazanma Oranı | **81.7%** (76 kazanan / 17 kaybeden) |
| Profit Factor | **10.08** |
| Max Drawdown | **10.5%** |
| Sharpe Ratio | **38.12** |
| Net Getiri | **+2,126.7%** *(komisyon + slippage dahil)* |

| Sembol | İşlem | WR | PF | Avg R | Ortalama SL | Getiri |
|--------|-------|----|----|-------|-------------|--------|
| 🥇 LINK | 17 | 82% | 11.54 | +2.04R | %2.6 | +95% |
| 🥈 BTC | 13 | 85% | 11.56 | +1.85R | %1.6 | +59% |
| 🥉 ETH | 16 | 88% | 11.71 | +1.42R | %2.2 | +56% |
| SOL | 13 | 92% | 20.78 | +1.69R | %2.5 | +53% |
| BNB | 10 | 70% | 7.21 | +2.05R | %1.6 | +48% |
| AVAX | 12 | 75% | 6.34 | +1.40R | %3.3 | +38% |
| XRP | 5 | 80% | 11.24 | +2.25R | %2.3 | +24% |
| DOT | 9 | 78% | 5.89 | +1.16R | %3.0 | +23% |

**Exit Tipi Dağılımı:**
- 62% → WIN_TRAIL (TP1 sonrası trailing stop kapattı)
- 16% → WIN_TP3 (tam 4R hedefe ulaştı)
- 3% → WIN_BREAKEVEN (TP1 vurdu, geri döndü = sıfır kayıp)
- 18% → LOSS (stop-loss tam kayıp)

---

## SL / TP Kuralları (ATR Tabanlı)

```
SL   = Giriş − ATR × 1.5  (LONG)
       Giriş + ATR × 1.5  (SHORT)
       (yakın OB/FVG alt/üst seviyesi daha korunaklıysa onu kullan)

TP1  = SL mesafesi × 1.5R → %40 kapat, SL breakeven'e taşı  ← kayıp riski sıfırlandı
TP2  = SL mesafesi × 2.5R → %35 kapat, trailing aktif
TP3  = SL mesafesi × 4.0R → kalan %25 kapat
Trail= ATR × 1.2 mesafeli takip (TP1 sonrası sürekli güncellenir)
```

---

## İşlem Zaman Planı (4H Futures)

```
UTC    Türkiye (UTC+3)   Öncelik   Neden
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
00:00  03:00             ATLA      Asya düşük likidite
04:00  07:00             DÜŞÜK     Asya sonu
08:00  11:00             ⭐ YÜKSEK  Londra Açılış Kill Zone
12:00  15:00             ⭐ YÜKSEK  NY Açılış Kill Zone
16:00  19:00             ⭐⭐ MAX    Londra/NY çakışma (en yüksek hacim)
20:00  23:00             ORTA      NY kapanış öncesi
```
**Manuel:** ~30–40 dk/gün (3 önemli seans × 10 dak)  
**Otomatik bot:** 7/24, sadece sinyal gelince Gmail bildirimi

---

## Pozisyon Boyutlama & Kaldıraç

```
Risk/İşlem    : %2 sabit (Kelly Criterion ile hafif dinamik)
Max pozisyon  : 4 eş zamanlı
Kaldıraç      : Skor 8–10 → maks 5x
                Skor 6.5–8 → maks 4x
                Skor 5.5–6.5 → maks 3x
Komisyon dahil: %0.04 taker + %0.05 slippage (round-trip ~%0.18)
```

---

## Kurulum

```bash
git clone https://github.com/uSoyrac/tirad.git
cd tirad
bash setup.sh
cp .env.example .env
# .env içini doldur
```

### Zorunlu Ortam Değişkenleri

| Değişken | Zorunlu | Açıklama |
|----------|:-------:|----------|
| `EMAIL_SENDER` | Evet | Gmail adresi |
| `EMAIL_APP_PASSWORD` | Evet | Gmail Uygulama Şifresi (2FA) |
| `EMAIL_RECIPIENT` | Evet | Bildirim adresi |
| `BINANCE_API_KEY` | Hayır | Public API de çalışır |
| `ANTHROPIC_API_KEY` | Hayır | Opsiyonel Claude sentezi |
| `OLLAMA_BASE_URL` | Hayır | Yerel LLM (varsayılan: localhost:11434) |

---

## Kullanım

```bash
source venv/bin/activate

# ──── YENİ: Optimal Sinyal Motoru v3 ────────────────────────────
# Tek sembol analiz
python run_engine.py --symbol ETH/USDT

# Tüm watchlist tarama
python run_engine.py --scan --balance 500

# Yüksek kalite filtresi
python run_engine.py --scan --min-score 6.5 --min-confirmations 3

# LLM debate ile (Ollama çalışıyor olmalı)
python run_engine.py --scan --llm

# ──── Gelişmiş Backtest ──────────────────────────────────────────
python backtest_enhanced.py       # ATR SL + Trailing + 1D filtre

# ──── Kağıt İşlem ───────────────────────────────────────────────
python paper_trader.py            # 4H döngüsel çalıştır
python paper_trader.py --report   # İstatistikler
python paper_trader.py --now      # Tek döngü

# ──── BIST Analizi ──────────────────────────────────────────────
python bist_engine.py             # 20 BIST hissesi tarama

# ──── Sistem Kontrolü ────────────────────────────────────────────
python setup_check.py --quick     # Bağlantı + modül testi

# ──── Klasik CLI ─────────────────────────────────────────────────
python live_scan.py               # Standalone tarayıcı
python main.py --loop             # APScheduler döngüsü
python main.py --symbol BTC/USDT  # Tek sembol
```

### Python API Kullanımı

```python
# Yeni OOP Motor (önerilen)
from bot.engine import SignalEngine

engine = SignalEngine(
    min_score         = 5.5,     # Minimum sinyal skoru
    min_confirmations = 2,       # Minimum confluence onayı
    balance           = 500.0,   # USDT bakiyesi
    use_llm           = False,   # Ollama isteğe bağlı
)

result = engine.analyze("ETH/USDT")
if result:
    print(result.action, result.composite, result.entry_price)

# Watchlist tarama
results = engine.scan_watchlist(["BTC/USDT", "ETH/USDT", "SOL/USDT"])
```

---

## Canlıya Geçiş Protokolü

1. **Paper trade:** min 2 hafta · `python paper_trader.py`
2. **Eşik:** ≥10 işlem ve WR ≥50% → canlıya geç
3. **İlk canlı:** $100–200 bakiye, maks 3x kaldıraç
4. **1. ay:** WR ≥50%, MaxDD <15% → tam kapasiteye yükselt

---

## Anti-Repainting Güvencesi

```python
# Her bar i için — YALNIZCA geçmiş veri:
df_slice = df_full.iloc[:i]      # Bar i görülmez
signal   = analyze(df_slice)     # i-1'de sinyal üretilir
entry    = df_full.iloc[i]       # i'de giriş simüle edilir
exit     = check(df_full.iloc[i].HIGH, df_full.iloc[i].LOW)
```

Tüm göstergeler `series.iloc[-2]` (son kapalı mum) veya `shift(1)` ile okunur.

---

## Teknik Gereksinimler

- **Python 3.9+** (f-string içinde backslash yasak — bkz. AGENT.md)
- **Binance hesabı gerekmez** (public OHLCV/Funding API)
- **Ollama opsiyonel** — `ollama pull deepseek-r1:7b` (yerel LLM debate)
- Kütüphaneler: `ccxt`, `yfinance`, `pandas`, `numpy`, `requests`, `beautifulsoup4`

---

*Anti-repainting garantili · Komisyon modeli dahil · PEP 8 + OOP mimarisi*
