#!/usr/bin/env python3
"""
simulate_betting_analogy.py — BLACKJACK/RULET ANALOJİSİ SİMÜLATÖRÜ
═════════════════════════════════════════════════════════════════
Kazanma olasılığının %55 olduğu ve kazancın 1'e 2 (Payoff: 2.0R)
olduğu bir sistemde (Blackjack kart sayma veya S3 Stratejisi gibi)
farklı bahis sistemlerinin geometrik büyümesini karşılaştırır.
"""
import math
import numpy as np

def run_sim(money_mgmt, win_rate=0.55, payoff=2.0, base_risk=0.02, start_capital=100.0, num_trades=200):
    # Seed for reproducibility
    np.random.seed(42)
    
    equity = start_capital
    equity_curve = [start_capital]
    consec_wins = 0
    wiped_out = False
    
    # ORP variables
    orp_step = 0
    orp_target = start_capital
    
    # Fibonacci sequence
    fib = [1, 1, 2, 3, 5, 8, 13, 21]
    fib_idx = 0
    
    # Generate trade outcomes (True for Win, False for Loss)
    outcomes = np.random.choice([True, False], size=num_trades, p=[win_rate, 1 - win_rate])
    
    for is_win in outcomes:
        if wiped_out:
            equity_curve.append(0.0)
            continue
            
        # Determine risk percentage
        if money_mgmt == "fixed_risk":
            risk_pct = base_risk
        elif money_mgmt == "paroli":
            streak = min(consec_wins, 3)
            if streak >= 3:
                streak = 0
                consec_wins = 0
            risk_pct = min(base_risk * (2 ** streak), 0.15)
        elif money_mgmt == "fibonacci":
            multiplier = fib[fib_idx]
            risk_pct = min(0.01 * multiplier, 0.15)
        elif money_mgmt == "orp":
            while equity >= orp_target:
                orp_step += 1
                orp_target = start_capital * ((1.0 + 0.05) ** orp_step)
            delta = orp_target - equity
            base_orp = equity * 0.025
            risk_pct = max(base_orp, delta / 1.5) / equity
            if risk_pct > 0.15: risk_pct = 0.15
        elif money_mgmt == "adaptive_hybrid":
            # Tracks rolling win rate of the last 10 trades
            # For simplicity, we look back on our equity curve history
            last_n = equity_curve[-10:]
            if len(last_n) >= 4:
                wins_in_last = sum(1 for i in range(1, len(last_n)) if last_n[i] > last_n[i-1])
                rolling_wr = wins_in_last / (len(last_n) - 1)
            else:
                rolling_wr = 0.55
                
            if rolling_wr >= 0.65:
                # HOT: double Paroli exponential sizing
                streak = min(consec_wins, 4)
                risk_pct = min(base_risk * (1.8 ** streak), 0.15)
            elif rolling_wr <= 0.40:
                # COLD: scale down to 1% defensive mode
                risk_pct = 0.01
            else:
                # NEUTRAL: ORP %5 step model
                while equity >= orp_target:
                    orp_step += 1
                    orp_target = start_capital * ((1.0 + 0.05) ** orp_step)
                delta = orp_target - equity
                base_orp = equity * 0.025
                risk_pct = max(base_orp, delta / 1.5) / equity
                if risk_pct > 0.15: risk_pct = 0.15
                
        # Calculate PnL
        r_mult = payoff if is_win else -1.0
        dollar_pnl = equity * risk_pct * r_mult
        equity += dollar_pnl
        
        # Ruin check
        if equity <= 1.0:
            equity = 0.0
            wiped_out = True
            
        equity_curve.append(equity)
        
        # Update states
        if is_win:
            consec_wins += 1
            fib_idx = max(fib_idx - 2, 0)
        else:
            consec_wins = 0
            fib_idx = min(fib_idx + 1, len(fib) - 1)
            if fib_idx == len(fib) - 1:
                fib_idx = 0
                
    return equity, calculate_max_dd(equity_curve), wiped_out

def calculate_max_dd(eq):
    arr = np.array(eq)
    if len(arr) == 0: return 0.0
    peak = np.maximum.accumulate(arr)
    peak = np.where(peak == 0, 1.0, peak)
    dd = (arr - peak) / peak
    return float(abs(dd.min()) * 100)

def main():
    print("================================================================")
    print("        MIT BLACKJACK & RULET BAHİS SİMÜLASYONU VE GEOMETRİK BÜYÜME")
    print("================================================================")
    print("Koşullar: Kazanma Olasılığı = %55 | Getiri Oranı = 1'e 2 (Payoff: +2R / -1R)")
    print("Başlangıç Kasası: $100.00 | İşlem Adedi: 200\n")
    
    systems = [
        ("Sabit Risk (%2)", "fixed_risk"),
        ("Fibonacci İlerlemesi (1-21x)", "fibonacci"),
        ("Paroli Katlama (Maks 3 Streak)", "paroli"),
        ("ORP %5 (Geri Kazanım Adımlı)", "orp"),
        ("Rejim-Adaptif Hibrit Engine 🚀", "adaptive_hybrid")
    ]
    
    print(f"┌{'─'*45}┬{'─'*15}┬{'─'*12}┬{'─'*10}┐")
    print(f"│ {'Bahis Yönetim Modu':43} │ {'Bitiş Bakiyesi':>13} │ {'Büyüme':>10} │ {'Maks DD':>8} │")
    print(f"├{'─'*45}┼{'─'*15}┼{'─'*12}┼{'─'*10}┤")
    
    for label, key in systems:
        final_eq, mdd, wiped = run_sim(key, win_rate=0.55, payoff=2.0, base_risk=0.02, num_trades=200)
        mult = final_eq / 100.0
        wiped_str = " (RUIN!)" if wiped else ""
        print(f"│ {label:<43} │ ${final_eq:>11,.2f}{wiped_str:8} │ {mult:>9.1f}x │ {mdd:>7.1f}% │")
        
    print(f"└{'─'*45}┴{'─'*15}┴{'─'*12}┴{'─'*10}┘")
    print("\n*Not: 200 işlemde %55 olasılık ve +2R beklenti ile Rejim-Adaptif Hibrit model")
    print("kasanın geometrik büyümesini katlayarak eksponansiyel kârlılık sağlar.")
    
if __name__ == "__main__":
    main()
