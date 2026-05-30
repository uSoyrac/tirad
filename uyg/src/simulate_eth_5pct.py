#!/usr/bin/env python3
import os
import sys
import math
import numpy as np
import pandas as pd

from simulate_orp import backtest_symbol_optimized, run_orp, WARMUP
from live_scan import B, R, GR, RD, YL, CY, DM, ok, bad, warn, nfo, dim, head, h2

def main():
    head("ETH/USDT 1h — 5% STEP GROWTH SIMULATION")
    
    csv_path = "data/historical/ETH_USDT_1h.csv"
    if not os.path.exists(csv_path):
        print(f"{bad('Error')}: Historical CSV not found at {csv_path}")
        return
        
    df = pd.read_csv(csv_path)
    df["ts"] = pd.to_datetime(df["ts"])
    df.set_index("ts", inplace=True)
    df = df.sort_index()
    
    # Run on the full 1-year dataset (8,760 bars)
    # df = df.tail(4000)
    
    print(f"Loaded {len(df)} bars of ETH/USDT 1h.")
    d0 = str(df.index[WARMUP])[:10]
    d1 = str(df.index[-1])[:10]
    print(f"Backtesting period: {d0} to {d1}")
    
    print("\nRunning backtest to extract raw trade logs...", end="", flush=True)
    res = backtest_symbol_optimized("ETH/USDT", df, max_leverage_limit=10)
    trades = res["trades"]
    print(f" {ok('Done')}. Total trades generated: {len(trades)}")
    
    if len(trades) == 0:
        return
        
    print("\nSimulating ORP with 5% Step Growth:")
    print("-" * 75)
    print(f"{'Limit Leverage':15} | {'Final Equity':15} | {'Completed 5% Steps':20} | {'Max DD':10} | {'Max Lev Used':12}")
    print("-" * 75)
    
    # We will test caps: 2x, 3x, 5x, 8x, 10x
    for cap in [2.0, 3.0, 5.0, 8.0, 10.0]:
        sim = run_orp(trades, start_capital=100.0, target_step_pct=0.05, max_lev_cap=cap)
        eq_col = ok if sim["final_eq"] > 100.0 else bad
        dd_col = ok if sim["max_drawdown"] <= 15.0 else (warn if sim["max_drawdown"] <= 30.0 else bad)
        
        eq_val = sim["final_eq"]
        dd_val = sim["max_drawdown"]
        steps_val = sim["steps_achieved"]
        lev_val = sim["max_lev_used"]
        print(f"{f'{cap}x Limit':15} | {eq_col(f'${eq_val:,.2f}'):15} | {f'{steps_val} steps':20} | {dd_col(f'{dd_val:.1f}%'):10} | {lev_val:.2f}x")

if __name__ == "__main__":
    main()
