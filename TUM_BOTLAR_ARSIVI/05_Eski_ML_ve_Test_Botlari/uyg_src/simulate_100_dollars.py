import numpy as np
import pandas as pd
from dynamic_optimizer import run_orp_dynamic

# 1 Year, 20 Coins, ~9 trades per coin = 180 trades
n_trades = 180
win_rate = 0.45

# Win outcomes based on our partial TP system (+0.78R avg from ETH, +0.20R from BTC)
# Typical scale in winners hit TP1 (+1.5R), TP2 (+2.5R) or TP3 (+4.0R).
# Losers hit SL (-1.0R) or BE (-0.1R after slippage).
np.random.seed(42) # For reproducibility

trades = []
for i in range(n_trades):
    if np.random.random() < win_rate:
        r_mult = np.random.choice([1.2, 1.8, 2.5, 3.5], p=[0.5, 0.3, 0.15, 0.05])
    else:
        r_mult = np.random.choice([-1.05, -0.2], p=[0.7, 0.3]) # -1.05 accounts for scale in slippage
        
    trades.append({
        "r_mult": r_mult,
        "sl_pct": 2.5 # Average SL distance 2.5%
    })

params = {
    "cycle_target_pct": 0.10,
    "recovery_factor": 1.0,
    "max_risk_cap": 0.20,
    "base_risk_pct": 0.04,
    "max_leverage": 10.0,
    "dynamic_recovery": False,
    "dd_scaling": False,
    "start_capital": 100.0
}

res = run_orp_dynamic(trades, params)

print("=== 1 YILLIK $100 BÜYÜME SİMÜLASYONU ===")
print(f"Başlangıç Kasası : $100.00")
print(f"Toplam İşlem Sayısı : {n_trades} (1 Yılda 20 Coin Toplamı)")
print(f"Win Rate : %{win_rate*100:.1f}")
print(f"Ortalama Getiri (R) : {np.mean([t['r_mult'] for t in trades]):.2f}R")
print("----------------------------------------")
print(f"1 YIL SONU KASA : ${res['final_eq']:,.2f}")
print(f"Büyüme Çarpanı : {res['total_growth']:.1f}x")
print(f"Maksimum Drawdown : %{res['max_drawdown']:.1f}")
print(f"Tamamlanan %10 Hedef Adımı : {res['steps_achieved']}")
print(f"Hesap Patladı Mı? : {'Evet' if res['wiped_out'] else 'Hayır'}")
