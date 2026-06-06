import ccxt
import pandas as pd
import time
from datetime import datetime
import os

SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", 
    "ADA/USDT", "AVAX/USDT", "LINK/USDT", "DOGE/USDT", "DOT/USDT",
    "LTC/USDT", "TRX/USDT", "UNI/USDT", "ATOM/USDT", "NEAR/USDT",
    "APT/USDT", "ARB/USDT", "OP/USDT", "INJ/USDT", "RNDR/USDT",
    "FET/USDT", "GRT/USDT", "LDO/USDT", "FIL/USDT", "AAVE/USDT"
] # 25 highly liquid coins

TIMEFRAME = '1h'
YEARS = 1
BARS_NEEDED = (365 * 24) * YEARS  # ~8760 bars for 1 year
LIMIT = 1500

def fetch_data():
    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })
    
    os.makedirs('bot/engine/data_v24', exist_ok=True)
    end_time = int(datetime.utcnow().timestamp() * 1000)
    
    for symbol in SYMBOLS:
        print(f"Downloading {symbol} (1H)...")
        all_ohlcv = []
        
        # 1H in ms = 60 * 60 * 1000 = 3600000
        since = end_time - (BARS_NEEDED * 3600000)
        
        while since < end_time:
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, since, limit=LIMIT)
                if not ohlcv:
                    break
                
                all_ohlcv.extend(ohlcv)
                since = ohlcv[-1][0] + 1
                time.sleep(0.1) # Respect rate limits slightly faster for small requests
            except Exception as e:
                print(f"  Error: {e}")
                time.sleep(2)
                
        if all_ohlcv:
            df = pd.DataFrame(all_ohlcv, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
            df['ts'] = pd.to_datetime(df['ts'], unit='ms')
            df.drop_duplicates(subset='ts', inplace=True)
            df.set_index('ts', inplace=True)
            
            filename = symbol.replace('/', '_') + '.csv'
            filepath = os.path.join('bot/engine/data_v24', filename)
            df.to_csv(filepath)
            print(f"  Saved {len(df)} bars.")

if __name__ == "__main__":
    fetch_data()
