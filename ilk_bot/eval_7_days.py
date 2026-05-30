import pandas as pd
import ccxt

exchange = ccxt.binance()
ohlcv = exchange.fetch_ohlcv("BNB/USDT", "4h", limit=50)
df = pd.DataFrame(ohlcv, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
df['ts'] = pd.to_datetime(df['ts'], unit='ms')

# Sinyal 1: 2026-05-25 12:00:00 (Limit: 661.31, 656.69, SL: 646.21)
# Sinyal 2: 2026-05-26 12:00:00 (Limit: 661.31, 656.69, SL: 647.65)
# We will just print the low and high from May 25 to May 30.

print("BNB Fiyat Hareketi (25 Mayıs Sonrası):")
for _, row in df.iterrows():
    if row['ts'] >= pd.to_datetime("2026-05-25 12:00:00"):
        print(f"Tarih: {row['ts']} | Low: {row['low']} | High: {row['high']}")
