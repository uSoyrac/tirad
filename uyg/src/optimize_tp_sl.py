#!/usr/bin/env python3
import sys, os
import pandas as pd
import numpy as np
import warnings
import ta
from dynamic_optimizer import run_orp_dynamic

warnings.filterwarnings("ignore")
COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]
TIMEFRAME = "4h"

def calculate_supertrend(df, period=10, multiplier=3):
    high = df['high']
    low = df['low']
    close = df['close']
    
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

def get_trade_result(df, start_idx, trend, entry, sl, tp):
    end_idx = min(start_idx + 60, len(df))
    slice_ahead = df.iloc[start_idx:end_idx]
    
    risk_dist = abs(entry - sl)
    reward_dist = abs(entry - tp)
    rr = reward_dist / risk_dist if risk_dist > 0 else 0
    sl_pct = risk_dist / entry * 100
    
    filled = False
    for _, row in slice_ahead.iterrows():
        high, low = row["high"], row["low"]
        if trend == 1:
            if not filled and low <= entry: filled = True
            if filled:
                if low <= sl: return -1.0, sl_pct
                if high >= tp: return rr, sl_pct
        else:
            if not filled and high >= entry: filled = True
            if filled:
                if high >= sl: return -1.0, sl_pct
                if low <= tp: return rr, sl_pct
    return 0.0, 0.0

def load_data():
    all_data = {}
    for coin in COINS:
        csv_path = os.path.join(os.path.dirname(__file__), "data", f"{coin}_USDT_{TIMEFRAME}.csv")
        if not os.path.exists(csv_path): continue
        df = pd.read_csv(csv_path)
        df["ts"] = pd.to_datetime(df["ts"])
        df = calculate_supertrend(df, 10, 3)
        df["adx"] = ta.trend.ADXIndicator(df["high"], df["low"], df["close"], window=14).adx()
        all_data[coin] = df
    return all_data

def evaluate_strategy(all_data, params):
    sl_type = params["type"] 
    sl_val = params["sl"]
    tp_val = params["tp"]
    
    all_trades = []
    
    for coin, df in all_data.items():
        test_df = df.iloc[-600:].reset_index(drop=True)
        for i in range(50, len(test_df) - 60):
            trend = test_df["st_trend"].iloc[i-1]
            prev_trend = test_df["st_trend"].iloc[i-2]
            close = test_df["close"].iloc[i-1]
            low = test_df["low"].iloc[i-1]
            high = test_df["high"].iloc[i-1]
            st = test_df["st"].iloc[i-1]
            atr = test_df["atr"].iloc[i-1]
            adx = test_df["adx"].iloc[i-1]
            
            is_signal = False
            if trend == 1:
                if prev_trend == -1: is_signal = True
                elif low <= st + (atr * 0.5): is_signal = True
            else:
                if prev_trend == 1: is_signal = True
                elif high >= st - (atr * 0.5): is_signal = True
                
            if not is_signal: continue
            
            if adx < 25: continue
            
            if sl_type == "ATR":
                sl = close - (atr * sl_val) if trend == 1 else close + (atr * sl_val)
                tp = close + (atr * tp_val) if trend == 1 else close - (atr * tp_val)
            else:
                sl = close * (1 - sl_val/100) if trend == 1 else close * (1 + sl_val/100)
                tp = close * (1 + tp_val/100) if trend == 1 else close * (1 - tp_val/100)
                
            result_r, sl_pct = get_trade_result(test_df, i, trend, close, sl, tp)
            if result_r != 0.0:
                all_trades.append({"coin": coin, "date": test_df.iloc[i]['ts'], "r_mult": result_r, "sl_pct": sl_pct})
                
    all_trades = sorted(all_trades, key=lambda x: x["date"])
    
    if not all_trades: return {"wr": 0, "eq": 0, "trades": 0, "rr": 0}
    
    wins = sum(1 for t in all_trades if t["r_mult"] > 0)
    win_rate = (wins / len(all_trades)) * 100
    
    # AGGRESSIVE ORP SETTINGS FOR MAX PROFIT
    orp_params = {
        "cycle_target_pct": 0.15,
        "recovery_factor": 1.5,
        "max_risk_cap": 0.20,
        "base_risk_pct": 0.05,
        "max_leverage": 15.0,
        "dynamic_recovery": True,
        "dd_scaling": True,
        "start_capital": 100.0
    }
    
    res = run_orp_dynamic(all_trades, orp_params)
    return {"wr": win_rate, "eq": res['final_eq'], "trades": len(all_trades), "rr": tp_val/sl_val}

def run_optimizer():
    print("="*60)
    print(" 🧪 MAKSİMUM KÂR (AGRESİF ORP) TP/SL OPTİMİZASYONU")
    print("="*60)
    
    all_data = load_data()
    
    strategies = [
        {"type": "ATR", "sl": 1.0, "tp": 2.0, "name": "ATR 1.0 / 2.0 (Dar)"},
        {"type": "ATR", "sl": 1.2, "tp": 2.4, "name": "ATR 1.2 / 2.4 (Orta)"},
        {"type": "ATR", "sl": 1.5, "tp": 3.0, "name": "ATR 1.5 / 3.0 (Eski)"},
        {"type": "ATR", "sl": 2.0, "tp": 4.0, "name": "ATR 2.0 / 4.0 (Geniş)"},
        {"type": "ATR", "sl": 2.5, "tp": 5.0, "name": "ATR 2.5 / 5.0 (Çok Geniş)"},
        {"type": "FIXED", "sl": 2.0, "tp": 4.0, "name": "SABİT %2 SL / %4 TP"},
        {"type": "FIXED", "sl": 3.0, "tp": 6.0, "name": "SABİT %3 SL / %6 TP"}
    ]
    
    best_eq = 0
    best_strat = None
    
    for s in strategies:
        res = evaluate_strategy(all_data, s)
        print(f"Strateji: {s['name']:<25} | İşlem: {res['trades']:<3} | Win Rate: %{res['wr']:<4.1f} | R/R: {res['rr']:.1f} | Bitiş Kasa: ${res['eq']:,.2f}")
        if res['eq'] > best_eq:
            best_eq = res['eq']
            best_strat = s
            
    print("="*60)
    print(f"🏆 EN ÇOK PARA BASAN STRATEJİ: {best_strat['name']}")
    print(f"🏆 NİHAİ BİTİŞ KASASI: ${best_eq:,.2f}")

if __name__ == "__main__":
    run_optimizer()
