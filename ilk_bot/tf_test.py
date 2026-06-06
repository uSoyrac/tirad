#!/usr/bin/env python3
import sys, os
import pandas as pd
import numpy as np
import warnings
import ta

warnings.filterwarnings("ignore")
COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]

def calculate_supertrend(df, period=14, multiplier=3.5):
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

def get_trade_result(df, start_idx, trend, entry, atr):
    tp_mult = 4.0
    sl_mult = 2.5
    end_idx = min(start_idx + 100, len(df))
    slice_ahead = df.iloc[start_idx:end_idx]
    initial_sl = entry - (atr * sl_mult) if trend == 1 else entry + (atr * sl_mult)
    tp = entry + (atr * tp_mult) if trend == 1 else entry - (atr * tp_mult)
    risk_dist = abs(entry - initial_sl)
    rr = tp_mult / sl_mult
    be_dist = risk_dist * 1.25
    be_trigger = entry + be_dist if trend == 1 else entry - be_dist
    current_sl = initial_sl
    is_breakeven = False
    filled = False
    for _, row in slice_ahead.iterrows():
        high, low = row["high"], row["low"]
        if trend == 1:
            if not filled and low <= entry: filled = True
            if filled:
                if high >= tp: return rr, risk_dist/entry*100
                if high >= be_trigger and not is_breakeven:
                    current_sl = entry
                    is_breakeven = True
                if low <= current_sl:
                    if is_breakeven: return 0.0, risk_dist/entry*100
                    return -1.0, risk_dist/entry*100
        else:
            if not filled and high >= entry: filled = True
            if filled:
                if low <= tp: return rr, risk_dist/entry*100
                if low <= be_trigger and not is_breakeven:
                    current_sl = entry
                    is_breakeven = True
                if high >= current_sl:
                    if is_breakeven: return 0.0, risk_dist/entry*100
                    return -1.0, risk_dist/entry*100
    return 0.0, 0.0

def test_timeframe(tf):
    all_trades = []
    for coin in COINS:
        csv_path = f"/Users/uygar/.gemini/antigravity/scratch/tirad/uyg/src/data/{coin}_USDT_{tf}.csv"
        if not os.path.exists(csv_path): continue
        df = pd.read_csv(csv_path)
        df["ts"] = pd.to_datetime(df["ts"])
        df = calculate_supertrend(df, period=14, multiplier=3.5)
        df["ema_250"] = ta.trend.EMAIndicator(df["close"], window=250).ema_indicator()
        adx_ind = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
        df['adx'] = adx_ind.adx()
        df['vol_sma'] = df['volume'].rolling(20).mean()
        df['vol_ratio'] = df['volume'] / df['vol_sma']
        
        for i in range(250, len(df) - 100):
            trend = df["st_trend"].iloc[i-1]
            prev_trend = df["st_trend"].iloc[i-2]
            close = df["close"].iloc[i-1]
            low = df["low"].iloc[i-1]
            high = df["high"].iloc[i-1]
            st = df["st"].iloc[i-1]
            atr = df["atr"].iloc[i-1]
            ema250 = df["ema_250"].iloc[i-1]
            adx = df["adx"].iloc[i-1]
            vol_ratio = df["vol_ratio"].iloc[i-1]
            
            is_signal = False
            if trend == 1:
                if prev_trend == -1: is_signal = True
                elif low <= st + (atr * 0.5): is_signal = True
            else:
                if prev_trend == 1: is_signal = True
                elif high >= st - (atr * 0.5): is_signal = True
                
            if not is_signal: continue
            if trend == 1 and close < ema250: continue
            if trend == -1 and close > ema250: continue
            if vol_ratio > 2.5: continue
            if adx > 40: continue
            
            result_r, sl_pct = get_trade_result(df, i, trend, close, atr)
            if result_r != 0.0 or (result_r == 0.0 and sl_pct > 0.0):
                all_trades.append({"date": df.iloc[i]['ts'], "r_mult": result_r, "sl_pct": sl_pct})
                
    all_trades = sorted(all_trades, key=lambda x: x["date"])
    
    if not all_trades:
        print(f"[{tf}] No trades found.")
        return
        
    wins = sum(1 for t in all_trades if t["r_mult"] > 0)
    losses = sum(1 for t in all_trades if t["r_mult"] < 0)
    win_rate = (wins / len(all_trades)) * 100 if len(all_trades) > 0 else 0
    
    equity = 100.0
    target_eq = 100.0
    step = 0
    cycle = 0.15
    max_lev = 15.0
    consecutive_losses = 0
    min_eq = 100.0
    
    for t in all_trades:
        if consecutive_losses >= 3:
            a_b = 0.01; a_m = 0.05; a_r = 1.0
        else:
            a_b = 0.05; a_m = 0.20; a_r = 1.5
            
        while equity >= target_eq:
            step += 1
            target_eq = 100.0 * ((1.0 + cycle) ** step)
            
        delta = target_eq - equity
        if delta < 0: delta = 0
        base_amt = equity * a_b
        req_risk = max(base_amt, delta / a_r)
        sl_f = t["sl_pct"] / 100.0 if t["sl_pct"] > 0 else 0.015
        pos = req_risk / sl_f
        req_lev = min(pos / equity if equity > 0 else 999, max_lev)
        act_risk = min((req_lev * equity) * sl_f, equity * a_m)
        
        equity += act_risk * t["r_mult"]
        if equity < min_eq: min_eq = equity
        if equity <= 0: break
            
        if t["r_mult"] > 0: consecutive_losses = 0
        elif t["r_mult"] < 0: consecutive_losses += 1
        
    print(f"[{tf}] Trades: {len(all_trades)} | WinRate: %{win_rate:.1f} | Min Eq: ${min_eq:,.2f} | Final Eq: ${equity:,.2f}")

test_timeframe("1h")
test_timeframe("1d")
