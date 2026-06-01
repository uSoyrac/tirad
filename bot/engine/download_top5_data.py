import requests
import pandas as pd
import time
import os

def download_extra_coins():
    symbols = ['BNBUSDT', 'XRPUSDT']
    interval = '15m'
    start_time_str = '2024-01-01 00:00:00'
    end_time_str = '2026-06-01 00:00:00'
    
    start_time_ms = int(pd.Timestamp(start_time_str).timestamp() * 1000)
    end_time_ms = int(pd.Timestamp(end_time_str).timestamp() * 1000)
    
    out_dir = 'bot/engine/data_v63' # Append to existing v63 dir
    os.makedirs(out_dir, exist_ok=True)
    
    for symbol in symbols:
        print(f"Downloading {symbol} Smart Money Data from {start_time_str}...")
        current_time_ms = start_time_ms
        all_klines = []
        
        while current_time_ms < end_time_ms:
            url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&startTime={current_time_ms}&limit=1500"
            try:
                response = requests.get(url)
                if response.status_code != 200:
                    print(f"Rate limited or error: {response.text}")
                    time.sleep(5)
                    continue
                    
                data = response.json()
                if not data:
                    break
                
                all_klines.extend(data)
                current_time_ms = data[-1][0] + 1
                
                if len(data) < 1500:
                    break
                    
                time.sleep(0.5) 
                
            except Exception as e:
                print(f"Exception: {e}")
                time.sleep(2)
                
        if all_klines:
            columns = [
                'ts', 'open', 'high', 'low', 'close', 'volume', 
                'close_time', 'quote_asset_volume', 'number_of_trades', 
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ]
            df = pd.DataFrame(all_klines, columns=columns)
            
            num_cols = ['open', 'high', 'low', 'close', 'volume', 'quote_asset_volume', 
                       'number_of_trades', 'taker_buy_base_asset_volume']
            df[num_cols] = df[num_cols].apply(pd.to_numeric, axis=1)
            
            df['ts'] = pd.to_datetime(df['ts'], unit='ms')
            df = df[['ts', 'open', 'high', 'low', 'close', 'volume', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume']]
            
            df = df[df['ts'] <= pd.to_datetime(end_time_str)]
            df = df.drop_duplicates(subset='ts').sort_values('ts')
            
            save_sym = symbol.replace('USDT', '_USDT')
            df.to_csv(f"{out_dir}/{save_sym}.csv", index=False)
            print(f"  Saved {len(df)} 15m candles with Smart Money Orderflow for {save_sym}")

if __name__ == "__main__":
    download_extra_coins()
