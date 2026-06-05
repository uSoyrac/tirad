#!/usr/bin/env python3
import sys
import time
import math
import numpy as np
import pandas as pd
from collections import defaultdict
from datetime import datetime

# Import backtest functions from our multi-tf script
from backtest_multi_tf import backtest_symbol_v2, ohlcv, WARMUP
from live_scan import B, R, GR, RD, YL, CY, DM, ok, bad, warn, nfo, dim, head, h2

# Emojis for terminal output
CROSS = "❌"
CHECK = "✅"

def run_fixed_risk(trades, start_capital=100.0, risk_pct=0.02):
    """Fixed risk: compounds risk_pct (2%) of current equity."""
    equity = start_capital
    equity_curve = [start_capital]
    wiped_out = False
    
    for t in trades:
        if wiped_out:
            equity_curve.append(0.0)
            continue
            
        dollar_pnl = equity * risk_pct * t["r_mult"]
        equity += dollar_pnl
        
        if equity <= 1.0: # Account wiped out
            equity = 0.0
            wiped_out = True
            
        equity_curve.append(equity)
        
    return {
        "final_eq": equity,
        "max_drawdown": calculate_max_dd(equity_curve),
        "wiped_out": wiped_out
    }

def run_fibonacci_progression(trades, start_capital=100.0, base_risk_pct=0.01):
    """
    Fibonacci progression:
    - Base risk is 1% of current equity.
    - Fibonacci sequence: 1, 1, 2, 3, 5, 8, 13, 21.
    - Loss: Move 1 step forward. Capped at index 7 (21x risk). If we lose at 21x, reset to 1x to prevent total ruin.
    - Win: Move 2 steps backward (min index 0).
    """
    fib = [1, 1, 2, 3, 5, 8, 13, 21]
    fib_idx = 0
    equity = start_capital
    equity_curve = [start_capital]
    wiped_out = False
    
    for t in trades:
        if wiped_out:
            equity_curve.append(0.0)
            continue
            
        multiplier = fib[fib_idx]
        current_risk_pct = base_risk_pct * multiplier
        
        dollar_pnl = equity * current_risk_pct * t["r_mult"]
        equity += dollar_pnl
        
        if equity <= 1.0:
            equity = 0.0
            wiped_out = True
            equity_curve.append(0.0)
            continue
            
        equity_curve.append(equity)
        
        # Outcome tracking
        if t["result"] == "LOSS":
            fib_idx = min(fib_idx + 1, len(fib) - 1)
            # Capped reset to protect account
            if fib_idx == len(fib) - 1:
                fib_idx = 0
        else: # WIN or BREAKEVEN
            fib_idx = max(fib_idx - 2, 0)
            
    return {
        "final_eq": equity,
        "max_drawdown": calculate_max_dd(equity_curve),
        "wiped_out": wiped_out
    }

def run_paroli_progression(trades, start_capital=100.0, base_risk_pct=0.02):
    """
    Paroli positive progression (Reverse Martingale):
    - Base risk is 2% of current equity.
    - Loss: Reset risk to base (2%).
    - Win: Double the risk for the next trade (2% -> 4% -> 8%), up to 3 consecutive wins max.
    - Reset to base (2%) after 3 consecutive wins or a loss.
    """
    consec_wins = 0
    equity = start_capital
    equity_curve = [start_capital]
    wiped_out = False
    
    for t in trades:
        if wiped_out:
            equity_curve.append(0.0)
            continue
            
        current_risk_pct = base_risk_pct * (2 ** consec_wins)
        current_risk_pct = min(current_risk_pct, 0.15) # Cap max risk at 15% to avoid ruin
        
        dollar_pnl = equity * current_risk_pct * t["r_mult"]
        equity += dollar_pnl
        
        if equity <= 1.0:
            equity = 0.0
            wiped_out = True
            equity_curve.append(0.0)
            continue
            
        equity_curve.append(equity)
        
        # Outcome tracking
        if t["result"] == "LOSS":
            consec_wins = 0
        else: # WIN
            consec_wins = min(consec_wins + 1, 3)
            if consec_wins == 3: # 3 consecutive wins reached, reset to lock in profits
                consec_wins = 0
                
    return {
        "final_eq": equity,
        "max_drawdown": calculate_max_dd(equity_curve),
        "wiped_out": wiped_out
    }

def calculate_max_dd(equity_curve):
    eq_arr = np.array(equity_curve)
    if len(eq_arr) == 0:
        return 0.0
    peak = np.maximum.accumulate(eq_arr)
    # Avoid divide by zero
    peak = np.where(peak == 0, 1.0, peak)
    dd = (eq_arr - peak) / peak
    return float(abs(dd.min()) * 100)

def main():
    head(f"BARR-PROGRESSIVE BETTING SIMULATOR (BLACKJACK/ROULETTE ANALOGY)")
    
    symbols = ["ETH/USDT", "BTC/USDT"]
    timeframes = ["15m", "30m", "1h", "4h", "1d"]
    
    # We fetch up to 1000 bars (Binance max default limit)
    limit = 1000
    
    # Fetch data
    data = defaultdict(dict)
    h2("VERİ İNDİRME")
    for sym in symbols:
        for tf in timeframes:
            sys.stdout.write(f"  ⬇  {sym:10} | {tf:3} ...")
            sys.stdout.flush()
            df = ohlcv(sym, tf, limit)
            if df.empty or len(df) < WARMUP + 20:
                print(f"  {bad('HATA — yetersiz veri')}")
                continue
            data[sym][tf] = df
            d0 = str(df.index[WARMUP])[:10]
            d1 = str(df.index[-1])[:10]
            print(f"  {ok('✅')} {len(df)} bar  {d0} → {d1}")
            time.sleep(0.3)
            
    h2("İLERİ BET SİSTEMİ SİMÜLASYONU")
    print()
    print(f"  {'Sembol':7} | {'TF':3} | {'İşlem':5} | {'Sistem':15} | {'Bitiş ($)':10} | {'MaxDD':6} | {'Likide':6}")
    print(f"  {'-'*75}")
    
    results = []
    
    for sym in symbols:
        for tf in timeframes:
            df = data[sym].get(tf)
            if df is None or df.empty:
                continue
                
            # Generate the trade sequence under 2x leverage cap
            res = backtest_symbol_v2(sym, df, max_leverage_limit=2)
            trades = res["trades"]
            n_trades = len(trades)
            
            if n_trades == 0:
                continue
                
            # Run simulations
            fixed = run_fixed_risk(trades)
            fib = run_fibonacci_progression(trades)
            paroli = run_paroli_progression(trades)
            
            results.append({
                "symbol": sym,
                "tf": tf,
                "n": n_trades,
                "fixed": fixed,
                "fib": fib,
                "paroli": paroli
            })
            
            # Print console row
            for label, r in [("Fixed Risk (2%)", fixed), ("Fibonacci (1-21)", fib), ("Paroli (Comp)", paroli)]:
                eq_col = ok if r["final_eq"] > 100.0 else bad
                dd_col = ok if r["max_drawdown"] <= 15.0 else (warn if r["max_drawdown"] <= 30.0 else bad)
                liq_str = bad("EVET") if r["wiped_out"] else ok("HAYIR")
                eq_val = r["final_eq"]
                dd_val = r["max_drawdown"]
                print(f"  {sym:7} | {tf:3} | {n_trades:>5} | {label:15} | {eq_col(f'${eq_val:>9.2f}'):10} | {dd_col(f'{dd_val:>5.1f}%'):6} | {liq_str:6}")
            print(f"  {'-'*75}")
            
    # Markdown Table output for walkthrough
    print("\n\n### BET SİSTEMLERİ KARŞILAŞTIRMA TABLOSU (MARKDOWN)\n")
    print("| Sembol | Zaman Dilimi | İşlem Sayısı | Bahis Sistemi | Bitiş Değeri ($100 ile) | Maksimum Çekilme (DD) | Hesap Battı mı? |")
    print("|--------|--------------|--------------|---------------|-------------------------|-----------------------|-----------------|")
    for r in results:
        sym = r["symbol"].replace("/USDT", "")
        for label, sys_res in [("Fixed Risk (2%)", r["fixed"]), ("Fibonacci (Capped)", r["fib"]), ("Paroli (Positive)", r["paroli"])]:
            liq_str = "**EVET (BATTIDIM)**" if sys_res["wiped_out"] else "HAYIR (GÜVENLİ)"
            print(f"| **{sym}** | {r['tf']} | {r['n']} | {label} | **${sys_res['final_eq']:.2f}** | {sys_res['max_drawdown']:.1f}% | {liq_str} |")

if __name__ == "__main__":
    main()
