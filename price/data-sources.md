# Veri Kaynakları

Mümkünse aşağıdaki güncel verileri değerlendir. Bir kaynağa erişemezsen veya veri
çekemezsen bunu **açıkça belirt**, o kaynağı yokmuş gibi varsayma. Veriyi tahmin
etme; "bu kaynak alınamadı" de ve eldeki veriyle çalış.

## Haber / Makro

- **Haber akışı:** perplexity.ai/finance (crypto)

## Coinglass Metrikleri

(kaynak: coinglass.com ilgili sayfaları)

- Coinbase Premium Index
- Open Interest (OI)
- 24h Gainers / Losers
- Long/Short ratio, Binance Net Long vs Short, Bitfinex Margin
- BTC Options OI
- Funding Fee Heatmap
- Liquidation Max Pain & Map
- Perp/Spot Volume Ratio
- Liquidity Heatmap
- Orderbook Delta (±1%)
- Whale Orders & Whale Alert
- RSI Heatmap
- MVRV Z-Score
- MACD

## Önemli Not

Bu sayfaların çoğu **canlı/JS tabanlıdır**; otomatik çekilemeyebilir. Çekemezsen
veriyi tahmin etme — "bu kaynak alınamadı" diyerek işaretle.

## Motor karşılığı (`pa/market.py`)

`collect()` şu an aşağıdaki anahtarsız Binance USDⓈ-M Futures endpoint'lerini
çeker; her biri ayrı yakalanır (biri çökerse diğerleri etkilenmez):

| Metrik | Endpoint |
|--------|----------|
| Funding Rate | `fapi/v1/premiumIndex` |
| Open Interest | `fapi/v1/openInterest` |
| Long/Short Ratio | `futures/data/globalLongShortAccountRatio` |

Felsefe koda gömülü: erişilemeyen kaynak `available=False` + hata notuyla
işaretlenir, **asla uydurulmaz**. HTTP çağrısı enjekte edilebilir (`http_get`),
böylece ağsız ortamda test edilebilir. Coinglass metrikleri (liquidation map,
whale, RSI heatmap, MVRV vb.) JS tabanlı olduğundan henüz entegre değildir.
