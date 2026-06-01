import ccxt
import pandas as pd
import os
import time

def download_data():
    exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'future'}})
    
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT']
    timeframe = '4h'
    # 4H data for 1 year is 365 * 6 = 2190 candles
    since = exchange.parse8601('2025-06-01T00:00:00Z') # exactly 1 year ago (assuming today is 2026-06-01)
    
    out_dir = 'bot/engine/data_v26'
    os.makedirs(out_dir, exist_ok=True)
    
    for symbol in symbols:
        print(f"Downloading {symbol} 4H data...")
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
                time.sleep(0.5)
            except Exception as e:
                print(f"Error for {symbol}: {e}")
                time.sleep(2)
                
        if all_ohlcv:
            df = pd.DataFrame(all_ohlcv, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
            df['ts'] = pd.to_datetime(df['ts'], unit='ms')
            
            # Remove duplicates just in case
            df = df.drop_duplicates(subset='ts').sort_values('ts')
            
            safe_sym = symbol.replace('/', '_')
            df.to_csv(f"{out_dir}/{safe_sym}.csv", index=False)
            print(f"  Saved {len(df)} 4H candles for {symbol}")

if __name__ == "__main__":
    download_data()
