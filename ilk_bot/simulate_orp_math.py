import sys, os
import numpy as np

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "uyg", "src"))
from dynamic_optimizer import run_orp_dynamic

# 3 Aylık Ortalama İşlem Sayısı: 5 Coin x 4 işlem/ay x 3 ay = ~60 İşlem
# XGBoost Win Rate: %75
# Kâr Katsayısı: 2R
np.random.seed(42)
total_trades = 60
win_rate = 0.75

# Create a list of results (2.0 for win, -1.0 for loss) exactly matching the win rate
wins = int(total_trades * win_rate)
losses = total_trades - wins

results = [2.0] * wins + [-1.0] * losses
np.random.shuffle(results) # Sinyalleri kronolojik olarak dağıt (Şans faktörü)

all_trades = []
for i, r in enumerate(results):
    all_trades.append({
        "r_mult": r,
        "sl_pct": 5.0, # Ort. Stop
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

res = run_orp_dynamic(all_trades, params)

print("="*60)
print(" 💵 3 AYLIK $100 KASA BÜYÜME SONUCU (MATEMATİKSEL ORP) 💵")
print("="*60)
print(f"Toplam İşlem     : {total_trades} (Win Rate: %{win_rate*100:.0f})")
print(f"Başlangıç Kasası : $100.00")
print(f"3 Ay Sonraki Kasa: ${res['final_eq']:,.2f}  (~{res['final_eq']*33:,.0f} TL)")
print(f"Net Büyüme Oranı : %{((res['final_eq']/100)-1)*100:.1f}")
print(f"Büyüme Çarpanı   : {res['total_growth']:.2f}x")
print(f"Maksimum Drawdown: %{res['max_drawdown']:.1f}")
print(f"Tamamlanan Döngü : {res['steps_achieved']}")
print("="*60)
