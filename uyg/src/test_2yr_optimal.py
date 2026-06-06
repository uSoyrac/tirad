import sys, os
import pandas as pd
import numpy as np
import warnings
import ta

warnings.filterwarnings("ignore")

COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]
TIMEFRAME = "4h"

# Friction rate: Maker limit %0.02 + Slippage %0.02 = %0.06 (round-trip per trade leverage multiplier)
FRICTION_RATE = 0.0006

# ORP Baseline (Same for both)
START_CAPITAL = 100.0
CYCLE_PCT = 0.15
RECOVERY_FACTOR = 1.5
BASE_RISK_PCT = 0.05
MAX_RISK_CAP = 0.20
MAX_LEVERAGE = 15.0
CONS_LOSS_FREEZE = 3

def calculate_supertrend(df, period=14, multiplier=3.5):
    high, low, close = df['high'], df['low'], df['close']
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.DataFrame({'tr1': tr1, 'tr2': tr2, 'tr3': tr3}).max(axis=1)
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    hl2 = (high + low) / 2
    basic_ub = hl2 + (multiplier * atr)
    basic_lb = hl2 - (multiplier * atr)
    ub = basic_ub.copy().values
    lb = basic_lb.copy().values
    c = close.values
    st = np.zeros(len(df))
    t = np.ones(len(df))
    for i in range(1, len(df)):
        if ub[i] > ub[i-1] and c[i-1] <= ub[i-1]: ub[i] = ub[i-1]
        if lb[i] < lb[i-1] and c[i-1] >= lb[i-1]: lb[i] = lb[i-1]
        if c[i] > ub[i-1]: t[i] = 1
        elif c[i] < lb[i-1]: t[i] = -1
        else: t[i] = t[i-1]
        if t[i] == 1: st[i] = lb[i]
        else: st[i] = ub[i]
    df['atr'] = atr
    df['st'] = st
    df['st_trend'] = t
    return df

def get_trade_result(df, start_idx, trend, entry, atr):
    tp_mult, sl_mult = 4.0, 2.5
    end_idx = min(start_idx + 100, len(df))
    slice_ahead = df.iloc[start_idx:end_idx]
    initial_sl = entry - (atr * sl_mult) if trend == 1 else entry + (atr * sl_mult)
    tp = entry + (atr * tp_mult) if trend == 1 else entry - (atr * tp_mult)
    risk_dist = abs(entry - initial_sl)
    rr = tp_mult / sl_mult
    be_dist = risk_dist * 1.25
    be_trigger = entry + be_dist if trend == 1 else entry - be_dist
    current_sl, is_breakeven, filled = initial_sl, False, False
    for _, row in slice_ahead.iterrows():
        high, low = row["high"], row["low"]
        if trend == 1:
            if not filled and low <= entry: filled = True
            if filled:
                if high >= tp: return rr, risk_dist/entry*100
                if high >= be_trigger and not is_breakeven: current_sl, is_breakeven = entry, True
                if low <= current_sl: return (0.0 if is_breakeven else -1.0), risk_dist/entry*100
        else:
            if not filled and high >= entry: filled = True
            if filled:
                if low <= tp: return rr, risk_dist/entry*100
                if low <= be_trigger and not is_breakeven: current_sl, is_breakeven = entry, True
                if high >= current_sl: return (0.0 if is_breakeven else -1.0), risk_dist/entry*100
    return 0.0, 0.0

def simulate_bot(all_dfs, version_name, vol_threshold):
    print(f"\n🏃 Simulating {version_name} (Vol Threshold: {vol_threshold})")
    all_trades = []
    
    for coin, df in all_dfs.items():
        for i in range(250, len(df) - 100):
            trend = df["st_trend"].iloc[i-1]
            prev_trend = df["st_trend"].iloc[i-2]
            close = df["close"].iloc[i-1]
            low_p, high_p = df["low"].iloc[i-1], df["high"].iloc[i-1]
            st, atr = df["st"].iloc[i-1], df["atr"].iloc[i-1]
            ema250 = df["ema_250"].iloc[i-1]
            adx = df["adx"].iloc[i-1]
            vol_ratio = df["vol_ratio"].iloc[i-1]
            
            is_signal = False
            if trend == 1:
                if prev_trend == -1 or low_p <= st + (atr * 0.5): is_signal = True
            else:
                if prev_trend == 1 or high_p >= st - (atr * 0.5): is_signal = True
                
            if not is_signal: continue
            if trend == 1 and close < ema250: continue
            if trend == -1 and close > ema250: continue
            
            if adx > 40: continue
            if vol_ratio > vol_threshold: continue
            
            res_r, sl_pct = get_trade_result(df, i, trend, close, atr)
            if res_r != 0.0 or (res_r == 0.0 and sl_pct > 0.0):
                all_trades.append({"date": df.iloc[i]['ts'], "r_mult": res_r, "sl_pct": sl_pct})
                
    all_trades = sorted(all_trades, key=lambda x: x["date"])
    
    equity = START_CAPITAL
    target_eq = START_CAPITAL
    step, cons_loss, total_fees = 0, 0, 0.0
    min_eq, peak_eq = START_CAPITAL, START_CAPITAL
    monthly_data = {}
    
    for t in all_trades:
        month_key = t["date"].strftime("%Y-%m")
        if month_key not in monthly_data:
            monthly_data[month_key] = {"start_eq": equity, "end_eq": equity, "trades": 0, "wins": 0, "losses": 0}
        monthly_data[month_key]["trades"] += 1
        
        drawdown_pct = (peak_eq - equity) / peak_eq if peak_eq > 0 else 0
        if drawdown_pct > 0.5: dyn_max_lev = max(2.0, MAX_LEVERAGE * 0.2)
        elif drawdown_pct > 0.3: dyn_max_lev = max(3.0, MAX_LEVERAGE * 0.4)
        elif drawdown_pct > 0.15: dyn_max_lev = max(5.0, MAX_LEVERAGE * 0.6)
        else: dyn_max_lev = MAX_LEVERAGE
        
        if cons_loss >= CONS_LOSS_FREEZE:
            a_b, a_m, a_r = BASE_RISK_PCT * 0.25, MAX_RISK_CAP * 0.25, max(RECOVERY_FACTOR, 1.5)
        else:
            a_b, a_m, a_r = BASE_RISK_PCT, MAX_RISK_CAP, RECOVERY_FACTOR
            
        while equity >= target_eq:
            step += 1
            target_eq = START_CAPITAL * ((1.0 + CYCLE_PCT) ** step)
            
        delta = max(0, target_eq - equity)
        req_risk = max(equity * a_b, delta / a_r)
        sl_f = max(t["sl_pct"] / 100.0, 0.015)
        act_lev = min(req_risk / sl_f / equity if equity > 0 else 999, dyn_max_lev)
        act_risk = min(act_lev * equity * sl_f, equity * a_m)
        
        friction = (act_lev * equity) * FRICTION_RATE
        total_fees += friction
        equity += (act_risk * t["r_mult"]) - friction
        
        if equity > peak_eq: peak_eq = equity
        if equity < min_eq: min_eq = equity
        if equity <= 0: break
        
        if t["r_mult"] > 0:
            cons_loss = 0
            monthly_data[month_key]["wins"] += 1
        elif t["r_mult"] < 0:
            cons_loss += 1
            monthly_data[month_key]["losses"] += 1
            
        monthly_data[month_key]["end_eq"] = equity
        
    wins = sum(1 for t in all_trades if t["r_mult"] > 0)
    losses = sum(1 for t in all_trades if t["r_mult"] < 0)
    wr = (wins/(wins+losses)*100) if (wins+losses) > 0 else 0
    
    return {
        "trades": len(all_trades),
        "wins": wins,
        "losses": losses,
        "wr": wr,
        "equity": equity,
        "min_eq": min_eq,
        "fees": total_fees,
        "monthly": monthly_data
    }

def main():
    print("="*80)
    print(" 📅 2 YILLIK (24 AYLIK) OPTİMAL SİSTEM TESTİ")
    print("="*80)
    
    all_dfs = {}
    for coin in COINS:
        csv_path = f"/Users/uygar/.gemini/antigravity/scratch/tirad/uyg/src/data/{coin}_USDT_4h_2yr.csv"
        if not os.path.exists(csv_path):
            print(f"❌ DATA NOT FOUND: {csv_path}")
            return
        df = pd.read_csv(csv_path)
        df["ts"] = pd.to_datetime(df["ts"])
        df = calculate_supertrend(df, 14, 3.5)
        df["ema_250"] = ta.trend.EMAIndicator(df["close"], window=250).ema_indicator()
        df['adx'] = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14).adx()
        df['vol_sma'] = df['volume'].rolling(20).mean()
        df['vol_ratio'] = df['volume'] / df['vol_sma']
        all_dfs[coin] = df
        print(f"✅ Loaded {coin}: {len(df)} candles ({df['ts'].iloc[0].strftime('%Y-%m')} to {df['ts'].iloc[-1].strftime('%Y-%m')})")
        
    # Run V18 (Vol < 2.5)
    v18_res = simulate_bot(all_dfs, "V18 Ultimate (Golden)", 2.5)
    
    # Run V19 (Vol < 2.0)
    v19_res = simulate_bot(all_dfs, "V19 Win Rate Champion", 2.0)
    
    # Output Reports
    with open("/Users/uygar/.gemini/antigravity/scratch/tirad/uyg/docs/v18_vs_v19_2year_report.md", "w") as f:
        f.write("# 📅 2 Yıllık Stres Testi Raporu (V18 vs V19)\n\n")
        f.write("Bu test, Haziran 2024'ten Haziran 2026'ya kadar tam 24 aylık bir süreyi kapsayan ")
        f.write("gerçek Binance 4 Saatlik fiyat, hacim ve volatilite verileriyle yapılmıştır.\n\n")
        
        f.write("## 🏆 Nihai Karşılaştırma Özeti\n\n")
        f.write("| Metrik | V18 Ultimate (Vol < 2.5x) | V19 Champion (Vol < 2.0x) |\n")
        f.write("| :--- | :---: | :---: |\n")
        f.write(f"| **İşlem Sayısı** | {v18_res['trades']} | {v19_res['trades']} |\n")
        f.write(f"| **Win Rate** | %{v18_res['wr']:.1f} | %{v19_res['wr']:.1f} |\n")
        f.write(f"| **Min Kasa (Drawdown)** | ${v18_res['min_eq']:,.2f} | ${v19_res['min_eq']:,.2f} |\n")
        f.write(f"| **Ödenen Komisyon** | ${v18_res['fees']:,.2f} | ${v19_res['fees']:,.2f} |\n")
        f.write(f"| **NİHAİ NET KÂR** | **${v18_res['equity']:,.2f}** | **${v19_res['equity']:,.2f}** |\n\n")
        
        f.write("## 🥇 V19 Şampiyon (Optimal Seçim) Aylık Dökümü\n\n")
        f.write("| Ay | Başlangıç | Bitiş | İşlem | Win Rate | Net Büyüme |\n")
        f.write("| :--- | :---: | :---: | :---: | :---: | :---: |\n")
        
        for m_key, d in v19_res["monthly"].items():
            wr = (d["wins"]/(d["wins"]+d["losses"])*100) if (d["wins"]+d["losses"]) > 0 else 0
            growth = ((d["end_eq"] - d["start_eq"]) / d["start_eq"] * 100) if d["start_eq"] > 0 else 0
            f.write(f"| **{m_key}** | ${d['start_eq']:,.2f} | **${d['end_eq']:,.2f}** | {d['trades']} | %{wr:.1f} | **%{growth:.1f}** |\n")
            
    print("\n✅ 2 yıllık test tamamlandı ve uyg/docs/v18_vs_v19_2year_report.md kaydedildi.")

if __name__ == "__main__":
    main()
