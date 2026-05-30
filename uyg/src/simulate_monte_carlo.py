#!/usr/bin/env python3
import random
import numpy as np
import pandas as pd

def run_monte_carlo(win_rate=0.80, avg_win_r=2.0, avg_loss_r=-1.0, num_trades=400, start_capital=100.0, num_trials=1000):
    results = {
        "fixed_risk": [],
        "fibonacci": [],
        "paroli": []
    }
    
    ruined = {
        "fixed_risk": 0,
        "fibonacci": 0,
        "paroli": 0
    }
    
    max_dds = {
        "fixed_risk": [],
        "fibonacci": [],
        "paroli": []
    }

    # Fibonacci sequence capped at index 7 (21x risk)
    fib = [1, 1, 2, 3, 5, 8, 13, 21]

    for trial in range(num_trials):
        # 1. Fixed Risk (2% risk of current equity per trade)
        fixed_equity = start_capital
        fixed_curve = [start_capital]
        fixed_ruin = False
        
        # 2. Fibonacci Progression (1% base risk of current equity)
        fib_equity = start_capital
        fib_curve = [start_capital]
        fib_idx = 0
        fib_ruin = False
        
        # 3. Paroli Progression (2% base risk of current equity)
        paroli_equity = start_capital
        paroli_curve = [start_capital]
        consec_wins = 0
        paroli_ruin = False

        for t in range(num_trades):
            # Roll trade outcome
            is_win = random.random() < win_rate
            r_mult = avg_win_r if is_win else avg_loss_r
            
            # --- Fixed Risk ---
            if not fixed_ruin:
                pnl = fixed_equity * 0.02 * r_mult
                fixed_equity += pnl
                if fixed_equity <= 1.0:
                    fixed_equity = 0.0
                    fixed_ruin = True
                fixed_curve.append(fixed_equity)
            else:
                fixed_curve.append(0.0)
                
            # --- Fibonacci Capped ---
            if not fib_ruin:
                multiplier = fib[fib_idx]
                pnl = fib_equity * 0.01 * multiplier * r_mult
                fib_equity += pnl
                if fib_equity <= 1.0:
                    fib_equity = 0.0
                    fib_ruin = True
                fib_curve.append(fib_equity)
                
                # Update Fibonacci index
                if not is_win:
                    fib_idx = min(fib_idx + 1, len(fib) - 1)
                    if fib_idx == len(fib) - 1: # Capped reset
                        fib_idx = 0
                else:
                    fib_idx = max(fib_idx - 2, 0)
            else:
                fib_curve.append(0.0)
                
            # --- Paroli ---
            if not paroli_ruin:
                # 2% -> 4% -> 8% -> 15% (cap)
                risk_pct = 0.02 * (2 ** consec_wins)
                risk_pct = min(risk_pct, 0.15)
                pnl = paroli_equity * risk_pct * r_mult
                paroli_equity += pnl
                if paroli_equity <= 1.0:
                    paroli_equity = 0.0
                    paroli_ruin = True
                paroli_curve.append(paroli_equity)
                
                # Update Paroli wins
                if not is_win:
                    consec_wins = 0
                else:
                    consec_wins = min(consec_wins + 1, 3)
                    if consec_wins == 3:
                        consec_wins = 0
            else:
                paroli_curve.append(0.0)

        # Calculate metrics for this trial
        def get_max_dd(curve):
            arr = np.array(curve)
            peak = np.maximum.accumulate(arr)
            peak = np.where(peak == 0, 1.0, peak)
            dd = (arr - peak) / peak
            return float(abs(dd.min()) * 100)

        # Store results
        results["fixed_risk"].append(fixed_equity)
        results["fibonacci"].append(fib_equity)
        results["paroli"].append(paroli_equity)
        
        if fixed_ruin: ruined["fixed_risk"] += 1
        if fib_ruin: ruined["fibonacci"] += 1
        if paroli_ruin: ruined["paroli"] += 1
        
        max_dds["fixed_risk"].append(get_max_dd(fixed_curve))
        max_dds["fibonacci"].append(get_max_dd(fib_curve))
        max_dds["paroli"].append(get_max_dd(paroli_curve))

    # Print results summary
    print(f"=== MONTE CARLO SIMULATION RESULTS FOR {num_trades} TRADES ===")
    print(f"Settings: trials={num_trials}, start_capital=${start_capital}, win_rate={win_rate:.1%}, avg_win={avg_win_r}R, avg_loss={avg_loss_r}R\n")
    
    systems = ["fixed_risk", "fibonacci", "paroli"]
    labels = ["Fixed Risk (2%)", "Fibonacci Capped", "Paroli Positive"]
    
    print(f"{'Sistem':18} | {'Ort. Bitiş ($)':15} | {'Medyan Bitiş ($)':16} | {'Maks DD Ort. (%)':16} | {'Batma İht. (%)':14}")
    print("-" * 88)
    
    for sys_name, label in zip(systems, labels):
        final_eqs = np.array(results[sys_name])
        mean_final = np.mean(final_eqs)
        median_final = np.median(final_eqs)
        mean_dd = np.mean(max_dds[sys_name])
        ruin_rate = (ruined[sys_name] / num_trials) * 100
        
        print(f"{label:18} | ${mean_final:13,.2f} | ${median_final:14,.2f} | {mean_dd:15.1f}% | {ruin_rate:13.1f}%")

if __name__ == "__main__":
    # Simulate BTC/ETH conservative parameters: Win Rate 80%, Avg Win 2.0R, Avg Loss -1R, 400 trades
    run_monte_carlo(win_rate=0.80, avg_win_r=2.0, avg_loss_r=-1.0, num_trades=400, start_capital=100.0, num_trials=1000)
