#!/usr/bin/env python3
import sys, os
import pandas as pd
import numpy as np
import ta
import warnings
import multiprocessing

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
        if ub[i] > ub[i-1] and c[i-1] <= ub[i-1]:
            ub[i] = ub[i-1]
        if lb[i] < lb[i-1] and c[i-1] >= lb[i-1]:
            lb[i] = lb[i-1]
            
        if c[i] > ub[i-1]:
            t[i] = 1
        elif c[i] < lb[i-1]:
            t[i] = -1
        else:
            t[i] = t[i-1]
            
        if t[i] == 1:
            st[i] = lb[i]
        else:
            st[i] = ub[i]
            
    df['atr'] = atr
    df['st'] = st
    df['st_trend'] = t
    return df

def get_label(df, start_idx, trend, entry, atr):
    end_idx = min(start_idx + 40, len(df))
    slice_ahead = df.iloc[start_idx:end_idx]
    
    sl = entry - (atr * 1.5) if trend == 1 else entry + (atr * 1.5)
    tp = entry + (atr * 3.0) if trend == 1 else entry - (atr * 3.0)
    
    filled = False
    for _, row in slice_ahead.iterrows():
        high, low = row["high"], row["low"]
        if trend == 1:
            if not filled and low <= entry: filled = True
            if filled:
                if low <= sl: return 0
                if high >= tp: return 1
        else:
            if not filled and high >= entry: filled = True
            if filled:
                if high >= sl: return 0
                if low <= tp: return 1
    return 0

def process_coin(coin):
    print(f"🔄 İşleniyor (Supertrend): {coin}/USDT...", flush=True)
    dataset = []
    
    csv_path = os.path.join(os.path.dirname(__file__), "data", f"{coin}_USDT_{TIMEFRAME}.csv")
    if not os.path.exists(csv_path): return dataset
        
    df = pd.read_csv(csv_path)
    if len(df) < 100: return dataset
    
    df["ts"] = pd.to_datetime(df["ts"])
    df = calculate_supertrend(df, 10, 3)
    
    df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
    adx_ind = ta.trend.ADXIndicator(df["high"], df["low"], df["close"], window=14)
    df["adx"] = adx_ind.adx()
    bb_ind = ta.volatility.BollingerBands(df["close"], window=20, window_dev=2)
    df["bb_width"] = bb_ind.bollinger_wband()
    df["vol_sma"] = ta.trend.SMAIndicator(df["volume"], window=20).sma_indicator()
    
    df.fillna(0, inplace=True)
    
    # Sinyalleri tarıyoruz
    for i in range(50, len(df) - 1):
        trend = df["st_trend"].iloc[i]
        prev_trend = df["st_trend"].iloc[i-1]
        close = df["close"].iloc[i]
        low = df["low"].iloc[i]
        high = df["high"].iloc[i]
        st = df["st"].iloc[i]
        atr = df["atr"].iloc[i]
        
        is_signal = False
        if trend == 1:
            # Bullish Flip or Pullback
            if prev_trend == -1: is_signal = True # Flip
            elif low <= st + (atr * 0.5): is_signal = True # Pullback (touched or very close)
        else:
            # Bearish Flip or Pullback
            if prev_trend == 1: is_signal = True # Flip
            elif high >= st - (atr * 0.5): is_signal = True # Pullback
            
        if not is_signal: continue
        
        vol_sma = df["vol_sma"].iloc[i]
        
        # Features
        features = {
            "st_trend": trend,
            "dist_to_st": abs(close - st) / close * 100,
            "atr_pct": atr / close * 100,
            "rsi": float(df["rsi"].iloc[i]),
            "adx": float(df["adx"].iloc[i]),
            "bb_width": float(df["bb_width"].iloc[i]),
            "vol_ratio": float(df["volume"].iloc[i]) / vol_sma if vol_sma > 0 else 1.0,
            "label": get_label(df, i+1, trend, close, atr) # Label from next candle onwards
        }
        dataset.append(features)
        
    print(f"✅ {coin} tamamlandı. ({len(dataset)} sinyal)")
    return dataset

def build_dataset():
    print("="*60)
    print(" ⚡ SUPERTREND (10,3) + ML VERİ ÇIKARICI ⚡")
    print("="*60)
    dataset = []
    
    # We can use multiprocessing, but the fast logic doesn't need it. We'll do it sequentially for safety
    for coin in COINS:
        dataset.extend(process_coin(coin))

    df_out = pd.DataFrame(dataset)
    df_out.dropna(inplace=True)
    out_path = os.path.join(os.path.dirname(__file__), "ml_dataset_live.csv")
    df_out.to_csv(out_path, index=False)
    
    print(f"\n✅ Supertrend Veri Seti: {out_path} ({len(df_out)} örnek)")
    print(f"Başarılı İşlemler: {df_out['label'].sum()} (%{df_out['label'].mean()*100:.1f})")

if __name__ == "__main__":
    build_dataset()
