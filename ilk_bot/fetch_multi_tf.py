import ccxt
import pandas as pd
import time
import os

exchange = ccxt.binance({'enableRateLimit': True})
symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT']
timeframes = ['1h', '1d']
data_dir = "/Users/uygar/.gemini/antigravity/scratch/tirad/uyg/src/data"
os.makedirs(data_dir, exist_ok=True)

since = exchange.parse8601('2025-05-01T00:00:00Z') # Same period as 4h data (around May 2025 to May 2026)

for symbol in symbols:
    for tf in timeframes:
        print(f"Fetching {symbol} {tf}...")
        all_ohlcv = []
        current_since = since
        while True:
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, tf, since=current_since, limit=1000)
                if not ohlcv:
                    break
                all_ohlcv += ohlcv
                current_since = ohlcv[-1][0] + 1
                if len(ohlcv) < 1000:
                    break
                time.sleep(0.1)
            except Exception as e:
                print(e)
                time.sleep(1)
        
        df = pd.DataFrame(all_ohlcv, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
        df['ts'] = pd.to_datetime(df['ts'], unit='ms')
        
        # Save
        filename = f"{symbol.replace('/', '_')}_{tf}.csv"
        df.to_csv(os.path.join(data_dir, filename), index=False)
        print(f"Saved {filename} ({len(df)} rows)")
