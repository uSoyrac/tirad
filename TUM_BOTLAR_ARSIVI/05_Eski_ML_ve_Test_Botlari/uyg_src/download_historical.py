#!/usr/bin/env python3
import os
import sys
import time
import pandas as pd
import ccxt

def get_exchange():
    return ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "future"}})

def download_ohlcv_one_year(symbol, timeframe):
    exchange = get_exchange()
    # 1 year in milliseconds
    duration_ms = 365 * 24 * 60 * 60 * 1000
    now = int(time.time() * 1000)
    since = now - duration_ms
    
    all_candles = []
    limit = 1000
    
    print(f"Downloading {symbol} {timeframe} for the last 1 year...")
    
    while since < now:
        try:
            candles = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)
            if not candles:
                break
            all_candles.extend(candles)
            # update since to the timestamp of the last candle + interval
            last_ts = candles[-1][0]
            since = last_ts + 1
            # print progress
            sys.stdout.write(f"\r  Fetched {len(all_candles)} candles so far...")
            sys.stdout.flush()
            time.sleep(0.1) # rate limit friendly
        except Exception as e:
            print(f"\nError: {e}, retrying in 2 seconds...")
            time.sleep(2)
            
    print(f"\nCompleted. Total candles: {len(all_candles)}")
    if not all_candles:
        return pd.DataFrame()
        
    df = pd.DataFrame(all_candles, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms")
    df.set_index("ts", inplace=True)
    
    # Save to CSV
    os.makedirs("data/historical", exist_ok=True)
    filename = f"data/historical/{symbol.replace('/', '_')}_{timeframe}.csv"
    df.to_csv(filename)
    print(f"Saved to {filename}\n")
    return df

def main():
    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
    timeframes = ["15m", "30m", "1h", "4h", "1d"]
    
    for sym in symbols:
        for tf in timeframes:
            # Check if file already exists to avoid duplicate work
            filename = f"data/historical/{sym.replace('/', '_')}_{tf}.csv"
            if os.path.exists(filename):
                # Check file age/size, if valid, skip
                size = os.path.getsize(filename)
                if size > 1000:
                    print(f"Skipping {sym} {tf} as {filename} already exists ({size} bytes).")
                    continue
            download_ohlcv_one_year(sym, tf)

if __name__ == "__main__":
    main()
