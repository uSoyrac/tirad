# 🅲 COMPOUND ENGINE AİLESİ — `bot_kararli/dengeli/optimal/rejim/quantpro`

> **Claude Opus 4.8 sohbetinin ürünü.** 1H ML-Scalp tabanlı, bileşik-getiri (compound)
> odaklı bot ailesi. Hepsi **aynı doğrulanmış edge'i** paylaşır; fark sadece **sizing**
> (risk yelpazesi). Ortak motor: `../src/compound_engine.py`.

## Mimari (ortak)
```
Donchian(40) + SuperTrend(10,3)   → sinyal (yön + zamanlama)
        ↓
XGBoost discriminator (14 feature, walk-forward) → "gerçek mi sahte trend mi" olasılığı
        ↓
gate top %20 → sadece kaliteli sinyallere gir
        ↓
TP +%5 / SL −%2.5  ·  sizing (bot'a göre değişir)  ·  top5 1H
```

## Botlar (risk yelpazesi)

| Bot | Sizing | $250→ | CAGR | MaxDD | **MAR** | Kime |
|---|---|---|---|---|---|---|
| `bot_kararli.py` | düz %60 notional | $480 | +%31 | %17 | 1.84 | En stabil, düşük drawdown |
| `bot_dengeli.py` | düz 1.25x | $786 | +%61 | %32 | ~1.9 | Denge (yarı-Kelly) |
| `bot_optimal.py` | güven-bazlı (≤2.5x) | $1003 | +%78 | %31 | 2.49 | En yüksek getiri |
| **`bot_rejim.py`** ⭐ | rejim-bazlı (≤2.5x) | $865-977 | +%67 | **%25** | **2.74** | **EN İYİ MAR** — boğa/ayı otomatik ayar |
| `bot_quantpro.py` | SHAP+CPCV+güven | $838 | +%65 | %29 | 2.26 | Kurumsal: SHAP-stabil feature + CPCV |
| **`bot_multimarket.py`** ⭐ | 2-sleeve (kripto+hisse) | — | — | — | **Sharpe 1.42** | **EN YÜKSEK SHARPE** — korelasyonsuz hisse sleeve |

### `bot_multimarket.py` — Vibe-Trading senaryosu (korelasyonsuz ikinci kol)
Vibe-Trading'in çok-piyasa erişimiyle (yfinance), aynı metodu US hisse/ETF'lere uyguladık.
Kripto-trend (Sharpe 1.31) + Hisse-trend (Sharpe 0.70), **rho=−0.20** → birleşik Sharpe **1.42-1.50**.
Alpha Zoo (433 alpha) kripto'da çıkmadı (redundant/overfit); değer çok-piyasa çeşitlendirmesinde.
Değer = getiri değil **risk-azaltma → güvenli kaldıraç**. (29 ay, forward doğrulama şart.)

*(OOS 2024-2026 walk-forward, gerçekçi maliyet %0.18 round-trip, tek-pozisyon)*

## ⭐ Öne çıkan: `bot_rejim.py`
Boğada trend-following kaybeder, ayıda kazanır (TEST EDİLDİ: 2023-10/2024-04 BTC +%161
döneminde sistem −%11 yaptı, al-tut +%252). `bot_rejim` her 4H barında BTC rejimini
(eğim + ADX + getiri, **sızıntısız**) okuyup otomatik ayarlar:
- 🐂 **Boğa:** notional 0.25x + top%5 gate (whipsaw'dan kaçın)
- ↔️ **Karma:** güven-bazlı optimal sistem
- 🐻 **Ayı:** 1.5x agresif (sistemin en iyi olduğu rejim)
→ En yüksek risk-ayarlı getiri (MAR 2.74), bot_optimal'den daha pürüzsüz eğri.

## Çalıştırma
```bash
cd uyg/Botlar
python3 bot_rejim.py        # veya kararli / dengeli / optimal / quantpro
python3 shadow_papertrade.py   # canlı gözlem (gerçek Binance, API-key'siz)
```
İlk çalıştırma birkaç dakika (sinyaller + walk-forward model), sonra cache'li.
Gereksinim: `xgboost scikit-learn shap pandas numpy ta scipy` + `bot/engine/data_v31/`.

## ⚠️ DÜRÜSTLÜK — bot_xasset ile kıyas
Bu aile **walk-forward OOS doğrulanmış** AMA **bot_xasset kadar titiz değil:**
- Bu ailenin **Deflated Sharpe ~%31**, **CPCV medyan ~%8** [%-16, %+64], P(>0) %73.
- bot_xasset: **DSR 0.99, PBO 0.03** (çok daha güçlü overfitting kanıtı, Sharpe 2.40).
- Bu aile **DSR/PBO kapısını tam geçmedi** — backtest iyi ama istatistiksel güven daha düşük.

**Hüküm:** Compound/MAR açısından çekici (özellikle bot_rejim), AMA en titiz-doğrulanmış
sistem `bot_xasset`'tir. Bu aile de **PAPER-TRADE adayı**, kör deploy DEĞİL.
Detaylı evrim + acımasız gerçekler: `AGENT_COMPOUND.md` ve `../../INTELLIGENCE.md`.
