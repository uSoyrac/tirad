# CRYPTO PROP-FIRM hedef seçimi — gerçek combo edge'imizle (trend+funding)

Edge = DSR/PBO-doğrulanmış crypto combo. Ham yıllık Sharpe ~1.69, haircut ×0.6 → sim ~1.01. Block-bootstrap 20000 yol. Crypto-native firmalar (gerçek perp + funding) — edge BURADA çalışır (FundingPips'in aksine).

## HyroTrader 1-step  (split 80%, ~$279, TRAILING DD)

| yıllık vol | P(tüm fazlar) | fon: P(ay patlama) | beklenen aylık $ |
|---|---|---|---|
| 3% | 1% | 0.0% | $75 |
| 5% | 12% | 0.0% | $126 |
| 7% | 29% | 0.0% | $175 |
| 10% | 42% | 0.3% | $251 |
| 15% | 42% | 4.7% | $373 |

## HyroTrader 2-step  (split 80%, ~$249, TRAILING DD)

| yıllık vol | P(tüm fazlar) | fon: P(ay patlama) | beklenen aylık $ |
|---|---|---|---|
| 3% | 0% | 0.0% | $76 |
| 5% | 6% | 0.0% | $128 |
| 7% | 18% | 0.0% | $177 |
| 10% | 35% | 0.0% | $257 |
| 15% | 48% | 0.1% | $381 |

## Breakout 1-step  (split 80%, ~$200, STATİK DD)

| yıllık vol | P(tüm fazlar) | fon: P(ay patlama) | beklenen aylık $ |
|---|---|---|---|
| 3% | 1% | 0.0% | $76 |
| 5% | 11% | 0.0% | $129 |
| 7% | 28% | 0.0% | $177 |
| 10% | 48% | 0.2% | $253 |
| 15% | 57% | 2.8% | $380 |

## FundedNext 2-step  (split 80%, ~$200, STATİK DD)

| yıllık vol | P(tüm fazlar) | fon: P(ay patlama) | beklenen aylık $ |
|---|---|---|---|
| 3% | 1% | 0.0% | $77 |
| 5% | 10% | 0.0% | $127 |
| 7% | 26% | 0.0% | $180 |
| 10% | 44% | 0.0% | $254 |
| 15% | 57% | 0.1% | $379 |

## SIRALAMA — hangi firmaya saldıralım (EV)

| firma | en iyi vol | P(funded) | fon patlama/ay | aylık $ | funded olma maliyeti | challenge $ |
|---|---|---|---|---|---|---|
| Breakout 1-step | 15% | 57% | 2.8% | $380 | $348 | $200 |
| FundedNext 2-step | 15% | 57% | 0.1% | $379 | $350 | $200 |
| HyroTrader 2-step | 15% | 48% | 0.1% | $381 | $519 | $249 |
| HyroTrader 1-step | 15% | 42% | 4.7% | $373 | $667 | $279 |

## Yorum (dürüst)

- **En yüksek-EV hedef: Breakout 1-step** — ~%15 funded olma olasılığı (~%15'de $200 challenge geçilir → beklenen maliyet ~$348), funded sonrası ~$380/ay (aylık patlama %2.8). Önerilen vol ~%15.
- **TRAILING DD (HyroTrader) statikten daha zor:** zirveden geri-çekilme bile eler → trailing firmalarda DAHA düşük vol gerekir. Statik DD (Breakout) hedefe daha rahat yürür.
- **Crypto-native = edge'imiz GERÇEK** (gerçek perp + funding; FundingPips'te imkansızdı). 700+ coin (HyroTrader) bizim 20-44'ten fazla breadth → momentum kolu daha da güçlü olabilir.
- ⚠️ Dürüst sınırlar: EOD modeli (intraday DD daha kötü → bota −%3 intraday self-stop); survivorship haircut; min-10-gün hedefi erken tutsan da riske maruz bırakır; gerçek perp funding/komisyon firmada biraz farklı. Önce küçük hesapla/paper, sonra ölçekle.
- **Sonraki: seçilen firma için bot_xasset'in crypto-only + o firmanın vol-hedefli versiyonunu paketle.** Canlı emir/API kodu öncesi SOR.