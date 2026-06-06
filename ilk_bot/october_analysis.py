import sys, os
import pandas as pd
import numpy as np
import warnings
import ta

warnings.filterwarnings("ignore")
COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]

def calc_st(df):
    high = df['high']
    low = df['low']
    close = df['close']
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.DataFrame({'tr1': tr1, 'tr2': tr2, 'tr3': tr3}).max(axis=1)
    atr = tr.ewm(alpha=1/14, adjust=False).mean()
    hl2 = (high + low) / 2
    basic_ub = hl2 + (3.5 * atr)
    basic_lb = hl2 - (3.5 * atr)
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

all_trades = []
for coin in COINS:
    csv_path = f"/Users/uygar/.gemini/antigravity/scratch/tirad/uyg/src/data/{coin}_USDT_4h.csv"
    if not os.path.exists(csv_path): continue
    df = pd.read_csv(csv_path)
    df["ts"] = pd.to_datetime(df["ts"])
    df = calc_st(df)
    df["ema_250"] = ta.trend.EMAIndicator(df["close"], window=250).ema_indicator()
    
    # Add ADX and Volume for analysis
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
        ema = df["ema_250"].iloc[i-1]
        
        is_signal = False
        if trend == 1:
            if prev_trend == -1: is_signal = True
            elif low <= st + (atr * 0.5): is_signal = True
        else:
            if prev_trend == 1: is_signal = True
            elif high >= st - (atr * 0.5): is_signal = True
            
        if not is_signal: continue
        if trend == 1 and close < ema: continue
        if trend == -1 and close > ema: continue
        
        # simplified check, assume everything inside is a trade entry
        month = df.iloc[i]['ts'].strftime("%Y-%m")
        if month in ["2025-10", "2025-11"]:
            # Evaluate outcome
            end_idx = min(i + 100, len(df))
            slice_ahead = df.iloc[i:end_idx]
            tp = close + (atr * 4.0) if trend == 1 else close - (atr * 4.0)
            sl = close - (atr * 2.5) if trend == 1 else close + (atr * 2.5)
            
            outcome = "LOSS"
            filled = False
            for _, row in slice_ahead.iterrows():
                h, l = row["high"], row["low"]
                if trend == 1:
                    if not filled and l <= close: filled = True
                    if filled:
                        if h >= tp: outcome = "WIN"; break
                        if l <= sl: outcome = "LOSS"; break
                else:
                    if not filled and h >= close: filled = True
                    if filled:
                        if l <= tp: outcome = "WIN"; break
                        if h >= sl: outcome = "LOSS"; break
            
            all_trades.append({
                "coin": coin, "month": month, "outcome": outcome,
                "adx": df['adx'].iloc[i-1], "vol_ratio": df['vol_ratio'].iloc[i-1]
            })

df_res = pd.DataFrame(all_trades)
print("=== EKİM AYI KAYIPLARI (64 Kayıp) ===")
print(df_res[(df_res['month'] == '2025-10') & (df_res['outcome'] == 'LOSS')].describe())
print("\n=== KASIM AYI KAZANÇLARI (Mega Ralli) ===")
print(df_res[(df_res['month'] == '2025-11') & (df_res['outcome'] == 'WIN')].describe())
