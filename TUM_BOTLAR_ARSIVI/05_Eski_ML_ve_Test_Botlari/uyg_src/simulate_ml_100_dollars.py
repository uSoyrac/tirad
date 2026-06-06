import numpy as np
from dynamic_optimizer import run_orp_dynamic

# 1 Year, 20 Coins, ~180 trades
n_trades = 180
# ML Keskinleştirme Filter Win Rate
win_rate = 0.65

np.random.seed(42) # For reproducibility

trades = []
for i in range(n_trades):
    if np.random.random() < win_rate:
        r_mult = np.random.choice([1.2, 1.8, 2.5, 3.5], p=[0.5, 0.3, 0.15, 0.05])
    else:
        r_mult = np.random.choice([-1.05, -0.2], p=[0.7, 0.3])
        
    trades.append({"r_mult": r_mult, "sl_pct": 2.5})

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

print("=== 1 YILLIK ML (XGBoost) DESTEKLİ $100 SİMÜLASYONU ===")
print(f"Toplam İşlem : {n_trades} (Yapay Zeka Onaylı)")
print(f"Win Rate : %{win_rate*100:.1f}")
print("----------------------------------------")
print(f"1 YIL SONU KASA : ${res['final_eq']:,.2f}")
print(f"Büyüme Çarpanı : {res['total_growth']:.1f}x")
print(f"Maksimum Drawdown : %{res['max_drawdown']:.1f}")
print(f"Tamamlanan Döngü : {res['steps_achieved']}")
