import os
import pandas as pd
from binance.client import Client
import time
from datetime import datetime, timedelta

def fetch_2yr_data():
    client = Client()
    coins = ["BTC", "ETH", "SOL", "BNB", "XRP"]
    interval = Client.KLINE_INTERVAL_4HOUR
    
    # 2 years ago from today
    start_str = (datetime.now() - timedelta(days=730)).strftime("%d %b %Y %H:%M:%S")
    print(f"Fetching 2 years of 4H data from {start_str}...")
    
    os.makedirs("/Users/uygar/.gemini/antigravity/scratch/tirad/uyg/src/data", exist_ok=True)
    
    for symbol in coins:
        ticker = f"{symbol}USDT"
        print(f"Downloading {ticker}...")
        try:
            klines = client.futures_historical_klines(ticker, interval, start_str)
            if not klines:
                print(f"No futures data for {ticker}, trying spot...")
                klines = client.get_historical_klines(ticker, interval, start_str)
                
            df = pd.DataFrame(klines, columns=['ts', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
            df['ts'] = pd.to_datetime(df['ts'], unit='ms')
            df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
            
            # Select required columns
            df = df[['ts', 'open', 'high', 'low', 'close', 'volume']]
            
            output_path = f"/Users/uygar/.gemini/antigravity/scratch/tirad/uyg/src/data/{symbol}_USDT_4h_2yr.csv"
            df.to_csv(output_path, index=False)
            print(f"✅ Saved {symbol}: {len(df)} candles. Start: {df['ts'].iloc[0]}")
        except Exception as e:
            print(f"❌ Failed to fetch {symbol}: {e}")
            
if __name__ == "__main__":
    fetch_2yr_data()
