import sys, os
import numpy as np

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "uyg", "src"))
from dynamic_optimizer import run_orp_dynamic

# 6 Aylık (180 Günlük) Test Parametreleri
# Zaman Dilimi: 4 Saatlik (4H) Mumlar
# Coinler: BTC, ETH, SOL, BNB, XRP
# AI Seçiciliği: Ayda ortalama 6 ila 8 işlem onaylıyor. (6 Ay = ~45 İşlem)
# AI Win Rate: %75

np.random.seed(99) # Farklı bir rastgelelik sekansı
total_trades = 45
win_rate = 0.75

wins = int(total_trades * win_rate)
losses = total_trades - wins

# 2.0 = Kazanç (Take Profit +2R)
# -1.0 = Kayıp (Stop Loss -1R)
results = [2.0] * wins + [-1.0] * losses
np.random.shuffle(results) 

all_trades = []
for i, r in enumerate(results):
    all_trades.append({
        "r_mult": r,
        "sl_pct": 5.0, # Ort. Stop Mesafesi
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
print(" 🚀 6 AYLIK (180 GÜN) AI + ORP BÜYÜME SONUCU 🚀")
print("="*60)
print(f"Zaman Dilimi     : 4 Saatlik (4H) Grafikler")
print(f"Tarama Sepeti    : 5 Majör Coin (BTC, ETH, BNB, SOL, XRP)")
print(f"Toplam İşlem     : {total_trades} Adet (Sadece yapay zekanın Keskin buldukları)")
print(f"Başarı Oranı     : %{win_rate*100:.0f} (Net: {wins} Kazanç, {losses} Zarar)")
print("-"*60)
print(f"Başlangıç Kasası : $100.00")
print(f"6 Ay Sonraki Kasa: ${res['final_eq']:,.2f}  (~{res['final_eq']*33:,.0f} TL)")
print(f"Büyüme Çarpanı   : {res['total_growth']:.2f}x")
print(f"Maksimum Drawdown: %{res['max_drawdown']:.1f}")
print(f"Tamamlanan Döngü : {res['steps_achieved']}")
print("="*60)
