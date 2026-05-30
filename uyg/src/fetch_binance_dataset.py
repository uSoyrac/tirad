#!/usr/bin/env python3
import ccxt
import pandas as pd
import time
import os

COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]
TIMEFRAME = "4h"
BARS_NEEDED = 2200

def fetch_history():
    print("="*60)
    print(" 📡 BİNANCE API GEÇMİŞ VERİ İNDİRİCİ (1 YIL) 📡")
    print("="*60)
    
    exchange = ccxt.binance({'enableRateLimit': True})
    
    out_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(out_dir, exist_ok=True)
    
    for coin in COINS:
        symbol = f"{coin}/USDT"
        print(f"[{symbol}] Veriler Binance'den çekiliyor...")
        
        all_ohlcv = []
        # First get the most recent 1000 bars
        recent = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=1000)
        all_ohlcv = recent + all_ohlcv
        
        # Paginate backwards
        while len(all_ohlcv) < BARS_NEEDED:
            earliest_ts = all_ohlcv[0][0]
            # 4h = 14400000 ms. We need 1000 bars back
            start_ts = earliest_ts - (1000 * 14400000)
            
            try:
                older = exchange.fetch_ohlcv(symbol, TIMEFRAME, since=start_ts, limit=1000)
                if not older:
                    break
                
                # Prepend the newly fetched older data
                all_ohlcv = older + all_ohlcv
                time.sleep(1) # Rate limit protection
            except Exception as e:
                print(f"Hata: {e}")
                break
                
        df = pd.DataFrame(all_ohlcv, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
        df.drop_duplicates(subset=['ts'], inplace=True)
        df.sort_values('ts', inplace=True)
        df['ts'] = pd.to_datetime(df['ts'], unit='ms')
        
        df = df.tail(BARS_NEEDED).reset_index(drop=True)
        out_path = os.path.join(out_dir, f"{coin}_USDT_{TIMEFRAME}.csv")
        df.to_csv(out_path, index=False)
        print(f"✅ {coin} kaydedildi: {len(df)} mum.")

if __name__ == "__main__":
    fetch_history()
