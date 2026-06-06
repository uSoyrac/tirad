import json
with open("ultimate_backtest_data.json") as f:
    d = json.load(f)
bin_w = d["binance"]["weekly"]
prop_w = d["prop"]["weekly"]
weeks = sorted(list(set(bin_w.keys()) | set(prop_w.keys())))

print("| Hafta | Binance Kasa ($) | Binance PnL | Prop Payouts Çekilen ($) | Prop Kasa ($) |")
print("| :--- | :--- | :--- | :--- | :--- |")
for w in weeks:
    b = bin_w.get(w, {"end": "-", "pnl": "-"})
    p = prop_w.get(w, {"payouts": "-", "end_eq": "-"})
    
    b_end_val = b.get("end", "-")
    b_pnl_val = b.get("pnl", "-")
    p_pay_val = p.get("payouts", "-")
    p_end_val = p.get("end_eq", "-")
    
    b_end = f"${b_end_val:,.2f}" if isinstance(b_end_val, float) else "-"
    b_pnl = f"${b_pnl_val:,.2f}" if isinstance(b_pnl_val, float) else "-"
    p_pay = f"${p_pay_val:,.2f}" if isinstance(p_pay_val, float) else "-"
    p_end = f"${p_end_val:,.2f}" if isinstance(p_end_val, float) else "-"
    
    print(f"| {w} | {b_end} | {b_pnl} | {p_pay} | {p_end} |")
