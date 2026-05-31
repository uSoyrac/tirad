# Price Section

Kaldıraçlı kripto işlemlerinde **fiyat hareketi (price action / SMC-ICT)** odaklı
analiz için bağımsız bir proje. Amaç: minimum riskle maksimum hedef — sadece
asimetrik (düşük risk / yüksek hedef) fırsatları yakalamak. Çoğu zaman doğru
cevap "işlem yok"tur.

## İçindekiler

### Doküman

| Dosya | Açıklama |
|-------|----------|
| [`analyst-prompt.md`](analyst-prompt.md) | Analist persona / sistem prompt'u — temel felsefe, analitik çekirdek, risk & kaldıraç kuralları, çıktı formatı. |
| [`concepts.md`](concepts.md) | Price action kavram sözlüğü — BOS, CHoCH, likidite, FVG, OB, PD array ve klasik PA yapıları. |
| [`data-sources.md`](data-sources.md) | Değerlendirilecek güncel veri kaynakları (funding, OI, long/short, whale, liquidation map vb.). |
| [`workflow.md`](workflow.md) | Analiz akışı, zaman dilimi & confluence kuralları, risk/kaldıraç hesabı, çıktı şablonu. |

### Motor (`pa/` paketi)

Deterministik, kural-tabanlı SMC/ICT yapı tespiti. **Çekirdek yalnızca Python
stdlib kullanır** (pandas/numpy gerekmez); `list[Candle]` üzerinde çalışır. Veri
kaynağı (CSV her zaman; `ccxt`/Binance opsiyonel, lazy import) ayrı katmandır.
LLM yorum katmanı bu motorun yapısal çıktısının üstüne biner.

| Modül | Sorumluluk |
|-------|-----------|
| `pa/types.py` | Çekirdek tipler (Candle, Swing, FVG, OB, Setup ...) + yardımcılar. |
| `pa/data.py` | OHLCV yükleme — CSV (stdlib), ccxt kayıtları, Binance public fetch (lazy). |
| `pa/structure.py` | Fractal swing tespiti + BOS / CHoCH (look-ahead'siz, en son swing referanslı). |
| `pa/imbalance.py` | Fair Value Gap (bullish/bearish) + mitigasyon. |
| `pa/orderblock.py` | Order block tespiti + taze/mitige ayrımı. |
| `pa/liquidity.py` | Eşit high/low havuzları (BSL/SSL) + liquidity sweep. |
| `pa/pdarray.py` | Premium / discount (equilibrium) bölgeleri. |
| `pa/risk.py` | Kaldıraç kuralı (stop% × kald < 90) + pozisyon büyüklüğü. |
| `pa/setup.py` | Setup zinciri: sweep → BOS/CHoCH → OB/FVG → hedef, R/R denetimi. |
| `pa/analyze.py` | Çok-TF confluence filtresi + risk planı. |
| `pa/report.py` | 3-bölümlü çıktı (PA / veri / karar kartı). |
| `pa/cli.py` | Komut satırı arayüzü. |

#### Test

```bash
cd price
python -m unittest discover -s tests -p "test_*.py"   # bağımlılık gerekmez (19 test)
```

#### Örnek veri üret & çalıştır

```bash
cd price
python scripts/make_sample.py               # data/sample_btc_1h.csv üretir

# CSV ile (ağ bağımsız)
python -m pa.cli --csv data/sample_btc_1h.csv --tf 1h --symbol BTC/USDT --portfolio 1000

# Binance public OHLCV (ccxt kuruluysa, anahtarsız)
python -m pa.cli --symbol BTC/USDT --tf 1h --htf 4h --portfolio 1000
```

Örnek çıktı (demo CSV, tam bir bullish ICT zinciri):

```
🎯 Coin: BTC/USDT
İşlem Yönü: LONG
Giriş: 102.0000
Stop Loss: 91.2000  (stop %10.59)
Take Profit: 142.0000
Risk/Ödül: 1:3.70
Kaldıraç: max 5x, önerilen 3x (stop %10.59 × kaldıraç < 90)
```

## Temel Felsefe (özet)

- Her setup en az **1:2 R/R**, tercihen **1:3+**. Bunu sağlamayan fikir üretilmez.
- Stop yapısaldır (invalidasyon/likidite ötesi), keyfi değil. "Yanılırsam hemen
  anlarım, haklıysam çok kazanırım" yapısı aranır.
- Kaldıraç kuralı: **stop_yüzdesi × kaldıraç < 90**.
- Belirsizken kesin konuşulmaz; veri yoksa uydurulmaz.
- Çizgi > sayı: önce yapı (trend, kanal, swing dizilimi) okunur.

## Durum

İlk dikey dilim çalışır durumda: **motor + CLI + testler** (stdlib, bağımlılıksız).
Sırada: canlı veri okuması (funding/OI/long-short/whale — BÖLÜM 2) ve isteğe bağlı
LLM yorum katmanı.
