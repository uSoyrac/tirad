import ccxt
import pandas as pd
import os
import time

def download_data():
    exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'future'}})
    
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT']
    timeframe = '1h'
    # 3 years ago from ~2026-06-01 -> 2023-06-01
    since = exchange.parse8601('2023-06-01T00:00:00Z') 
    
    out_dir = 'bot/engine/data_v31'
    os.makedirs(out_dir, exist_ok=True)
    
    for symbol in symbols:
        print(f"Downloading {symbol} 3-Year 1H data...")
        all_ohlcv = []
        current_since = since
        
        while True:
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=current_since, limit=1000)
                if not ohlcv:
                    break
                
                all_ohlcv.extend(ohlcv)
                current_since = ohlcv[-1][0] + 1
                
                if len(ohlcv) < 1000:
                    break
                
                # Check if we crossed 2026-06-01
                if current_since > exchange.parse8601('2026-06-02T00:00:00Z'):
                    break
                    
                time.sleep(0.5)
            except Exception as e:
                print(f"Error for {symbol}: {e}")
                time.sleep(2)
                
        if all_ohlcv:
            df = pd.DataFrame(all_ohlcv, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
            df['ts'] = pd.to_datetime(df['ts'], unit='ms')
            
            # Limit strictly up to 2026-06-01 just to be exact
            df = df[df['ts'] <= pd.to_datetime('2026-06-01')]
            
            df = df.drop_duplicates(subset='ts').sort_values('ts')
            
            safe_sym = symbol.replace('/', '_')
            df.to_csv(f"{out_dir}/{safe_sym}.csv", index=False)
            print(f"  Saved {len(df)} 1H candles for {symbol} (3 Years)")

if __name__ == "__main__":
    download_data()
