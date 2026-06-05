# OPTIMAL FON BOTU — firma head-to-head (combo, vol %15, gerçek takvim)

565 başlangıç günü. Rejim-zamanlaması = düşük-vol günlerinde başla (alt-tercil).

| Firma/yapı | Koşulsuz P(geç) | Düşük-vol başla P(geç) | DD modeli |
|---|---|---|---|
| HyroTrader 2-step (trailing) | 42% | **52%** | trailing |
| HyroTrader 1-step (trailing) | 28% | **20%** | trailing |
| Breakout 1-step (STATİK %6) | 49% | **53%** | STATİK |
| Velotrade 2-step (trailing %10) | 42% | **52%** | trailing |
| Velotrade 1-step Classic (trail %7) | 32% | **21%** | trailing |
| Velotrade 1-step Pro (STATİK %3) | 32% | **23%** | STATİK |

## Yorum (dürüst)

- **En yüksek geçiş: Breakout 1-step (STATİK %6) → düşük-vol başla %53.**
- **STATİK DD (Breakout) trailing'i (HyroTrader) yener** geçiş-kolaylığında: zirveden geri-çekilme cezalandırılmaz → hedefe daha rahat tırmanırsın. 1-step (tek faz) de 2-step'ten hızlı (tek hurdle).
- **Rejim-zamanlaması her firmada geçişi artırıyor** (düşük-vol başla). Screener'la o günü seç.
- **Optimal fon-botu reçetesi:** (1) **Breakout 1-step STATİK** (en kolay geçiş), (2) combo edge + **~%15 sabit vol**, (3) **düşük-vol rejiminde başla**, (4) her pozisyona ATR-stop ≤%3 + −%3 intraday self-stop, (5) Top-3 momentum + funding long/short (40%-konsantrasyon doğal geçer). Akıllı de-risk EKLEME (zarar).
- ⚠️ HyroTrader'ın avantajı: 700 coin + testnet + Bybit (doğrulama orada). Breakout'un: statik-DD kolay geçiş. **Strateji: HyroTrader'da forward-doğrula (testnet düzelince), geçiş kararını Breakout'ta ver (daha kolay).**
- ⚠️ Tek-dönem 2023-26, survivorship; büyüklük tentatif, yön güvenilir.