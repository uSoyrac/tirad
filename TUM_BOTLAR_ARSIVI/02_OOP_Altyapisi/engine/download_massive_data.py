import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
import os

SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", 
    "XRP/USDT", "ADA/USDT", "AVAX/USDT", "LINK/USDT", 
    "DOGE/USDT", "DOT/USDT"
]

TIMEFRAME = '4h'
YEARS = 3
BARS_NEEDED = (365 * 24 // 4) * YEARS  # ~6570 bars for 3 years
LIMIT = 1500

def fetch_data():
    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })
    
    os.makedirs('bot/engine/data', exist_ok=True)
    
    end_time = int(datetime.utcnow().timestamp() * 1000)
    
    for symbol in SYMBOLS:
        print(f"Downloading {symbol}...")
        all_ohlcv = []
        
        # Calculate the starting timestamp
        # 4H in ms = 4 * 60 * 60 * 1000 = 14400000
        since = end_time - (BARS_NEEDED * 14400000)
        
        while since < end_time:
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, since, limit=LIMIT)
                if not ohlcv:
                    break
                
                all_ohlcv.extend(ohlcv)
                since = ohlcv[-1][0] + 1  # Next candle
                print(f"  Fetched {len(ohlcv)} bars. Total: {len(all_ohlcv)}")
                time.sleep(0.5)
            except Exception as e:
                print(f"  Error: {e}")
                time.sleep(5)
                
        if all_ohlcv:
            df = pd.DataFrame(all_ohlcv, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
            df['ts'] = pd.to_datetime(df['ts'], unit='ms')
            df.drop_duplicates(subset='ts', inplace=True)
            df.set_index('ts', inplace=True)
            
            filename = symbol.replace('/', '_') + '.csv'
            filepath = os.path.join('bot/engine/data', filename)
            df.to_csv(filepath)
            print(f"Saved {len(df)} bars to {filepath}\n")

if __name__ == "__main__":
    fetch_data()
