# Devir Notu — `price/` projesi

> Bu dosya, oturumlar/ortamlar arası devir içindir. Yeni bir Claude Code
> oturumu (özellikle VS Code'da) bunu okuyup bağlamı hızlıca toparlayabilir.
> Branch: **`claude/pensive-shannon-BpUKs`** · PR: **#1**

## Proje nedir

Kaldıraçlı kripto için **price action / SMC-ICT** analiz motoru. Bağımsız proje
(repo'nun geri kalanından ayrı, `price/` altında). Felsefe: minimum riskle
maksimum hedef; her setup ≥ 1:2 R/R; çoğu zaman doğru cevap "işlem yok".
Tam persona/kurallar: `analyst-prompt.md`, `workflow.md`, `concepts.md`,
`data-sources.md`.

## Mimari kararlar (neden böyle)

- **Çekirdek SADECE Python stdlib.** pandas/numpy/ccxt zorunlu değil. Sebep:
  her ortamda `pip install` olmadan çalışsın, test hızlı ve deterministik olsun.
- **Motor `list[Candle]` üzerinde çalışır** (pandas DataFrame değil). Veri
  katmanı (`pa/data.py`) ayrı; CSV her zaman, Binance klines stdlib `urllib`
  ile (ccxt sadece diğer borsalar için lazy fallback).
- **HTTP enjekte edilebilir** (`http_get` parametresi) → ağsız test edilebilir.
- **Look-ahead yok:** yapı olayları (BOS/CHoCH) swing onaylandıktan `k` mum
  sonra damgalanır. `detect_structure` EN SON onaylanmış swing'i referans alır
  (en yüksek/en düşük değil — bu bir bug'dı, düzeltildi).
- **Dürüstlük koda gömülü:** erişilemeyen veri kaynağı `available=False` +
  hata notuyla işaretlenir, ASLA uydurulmaz. (`pa/market.py`, `pa/scanner.py`)

## Modül haritası (`pa/`)

| Modül | İş |
|-------|-----|
| `types.py` | Candle + SMC/ICT tipleri (Swing, FVG, OB, Setup, ...) |
| `data.py` | OHLCV: `load_csv`, `fetch_binance` (stdlib), `fetch_ohlcv` |
| `structure.py` | fractal swing + BOS/CHoCH (look-ahead'siz) |
| `imbalance.py` | FVG (bullish/bearish + mitigasyon) |
| `orderblock.py` | order block + taze/mitige |
| `liquidity.py` | eşit H/L havuzları (BSL/SSL) + sweep |
| `pdarray.py` | premium/discount |
| `risk.py` | kaldıraç kuralı `stop% × kald < 90` + pozisyon büyüklüğü |
| `setup.py` | zincir: sweep→BOS/CHoCH→OB/FVG→hedef, R/R kapısı (≥2) |
| `analyze.py` | çok-TF confluence filtresi + risk planı |
| `market.py` | **BÖLÜM 2** canlı veri (funding/OI/long-short, Binance fapi) |
| `report.py` | 3-bölümlü çıktı + veri-yapı confluence |
| `scanner.py` | çoklu sembol tarama (VDS/cron için) |
| `cli.py` | `python -m pa.cli` |

## Çalıştırma

```bash
cd price
python3 -m unittest discover -s tests -p "test_*.py"   # 33 test, bağımlılık yok

python3 scripts/make_sample.py                          # demo CSV üret
python3 -m pa.cli --csv data/sample_btc_1h.csv --tf 1h --symbol BTC/USDT --portfolio 1000

# CANLI (internet gerekir — web sandbox'ta ÇALIŞMAZ, VS Code/VDS'de çalışır):
python3 -m pa.cli --symbol BTC/USDT --tf 1h --htf 4h --data --portfolio 1000
python3 scripts/scan_once.py            # çoklu sembol; env ile yapılandır
```

## ⚠️ Ağ durumu (kritik bağlam)

Claude Code **web sandbox**'ının çıkışı allowlist proxy ile kilitli:
dış HTTP `403 "Host not in allowlist"` (`x-deny-reason: host_not_allowed`)
döner. Bu yüzden `--data` ve canlı OHLCV web oturumunda doğrulanamadı —
kod yazıldı ve sahte `http_get` ile test edildi, ama gerçek Binance
çağrısı denenmedi.

**Çözüm = bu projeyi internet erişimi olan yerde çalıştırmak:**
VS Code'daki Claude Code (kullanıcının makinesi) veya VDS. Orada `--data`
gerçek veri çeker. VDS için `deploy/` altında systemd+cron hazır.

## Yapıldı

- [x] Dokümanlar (analyst-prompt, concepts, data-sources, workflow)
- [x] Deterministik motor + CLI + 33 test
- [x] BÖLÜM 2 canlı veri katmanı (funding/OI/long-short)
- [x] stdlib Binance klines fetcher (ccxt'siz)
- [x] Çoklu sembol scanner + VDS systemd/cron dağıtımı

## Açık işler / sıradakiler

- [x] **Canlı doğrulama (2026-05-31, VS Code / internetli makine):**
      `python3 -m pa.cli --symbol BTC/USDT --tf 1h --htf 4h --data
      --portfolio 1000` çalıştırıldı → exit 0, stderr boş. Klines canlı
      çekildi (giriş+HTF; bağımsız `urllib` Binance çağrısıyla aynı fiyat
      aralığı) ve BÖLÜM 2 `market.py` funding/OI/long-short (fapi) üç
      metrik de gerçek değerle geldi (alınamadı uyarısı yok). 33/33 test OK.
- [ ] **Backtest & doğrulama:** kuralları geçmiş veride çalıştırıp gerçek
      isabet/R/R dağılımını ölç ("bu kurallar gerçekten çalışıyor mu").
- [ ] **LLM yorum katmanı:** motorun yapısal çıktısını Claude API'ye verip
      3-bölümlü analizi doğal dilde yorumlat (API anahtarı gerekir).
- [ ] **Coinglass metrikleri** (liquidation map, whale, RSI heatmap, MVRV) —
      JS tabanlı; resmi API veya headless tarayıcı gerekir.
- [ ] Bildirim katmanı (Telegram/webhook) — token'lar VDS'de .env'de, repoya
      girmemeli.

## Notlar

- Tüm commit'ler bu branch'te; PR #1 push'larla güncellenir. Yeni PR açma.
- Model kimliği vb. commit/PR/koda yazılmaz (sadece sohbet).
