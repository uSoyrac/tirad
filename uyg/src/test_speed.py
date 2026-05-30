#!/usr/bin/env python3
import time
import pandas as pd
import cProfile
import pstats
from simulate_orp import backtest_symbol_optimized

def main():
    print("Loading data...")
    df = pd.read_csv("data/historical/BTC_USDT_1h.csv")
    df["ts"] = pd.to_datetime(df["ts"])
    df.set_index("ts", inplace=True)
    df = df.sort_index()
    
    # We take the first 500 bars to profile
    test_df = df.iloc[:500]
    print(f"Profiling 500 bars...")
    
    t0 = time.time()
    pr = cProfile.Profile()
    pr.enable()
    
    backtest_symbol_optimized("BTC/USDT", test_df, max_leverage_limit=5)
    
    pr.disable()
    elapsed = time.time() - t0
    print(f"Elapsed time for 500 bars: {elapsed:.3f} seconds ({elapsed/500*1000:.3f} ms per bar)")
    
    # Print the top 15 functions by cumulative time
    ps = pstats.Stats(pr).sort_stats('cumulative')
    ps.print_stats(15)

if __name__ == "__main__":
    main()
