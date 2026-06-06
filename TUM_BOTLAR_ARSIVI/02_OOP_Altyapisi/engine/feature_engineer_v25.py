import pandas as pd
import numpy as np
import ta
import os
import sys

def calc_linreg_slope(s, window=10):
    """Vektörel Lineer Regresyon Eğimi (Hız)"""
    x = np.arange(window)
    x_mean = x.mean()
    x_var = x.var() * window
    
    # y rolling mean
    y_mean = s.rolling(window).mean()
    
    # sum of (x_i - x_mean) * y_i
    def slope_func(y):
        return np.sum((x - x_mean) * y) / x_var
        
    return s.rolling(window).apply(slope_func, raw=True)

def engineer_features_v25(df):
    df = df.copy()
    
    # 1. Hız ve İvme (Derin Regresyon)
    df['slope_10'] = calc_linreg_slope(df['close'], 10)
    df['slope_10_pct'] = (df['slope_10'] / df['close']) * 100
    df['accel_10'] = df['slope_10'].diff(3) # 3 mumluk ivme (Hızlanıyor mu yavaşlıyor mu?)
    
    # 2. Matematiksel Price Action
    df['body'] = abs(df['close'] - df['open'])
    df['wick_upper'] = df['high'] - df[['open', 'close']].max(axis=1)
    df['wick_lower'] = df[['open', 'close']].min(axis=1) - df['low']
    df['range'] = df['high'] - df['low']
    df['body_pct'] = df['body'] / (df['range'] + 1e-9)
    df['is_pinbar_bull'] = (df['wick_lower'] > (df['body'] * 2)) & (df['wick_upper'] < df['body']).astype(int)
    df['is_pinbar_bear'] = (df['wick_upper'] > (df['body'] * 2)) & (df['wick_lower'] < df['body']).astype(int)
    
    # 3. Swing Noktaları
    df['swing_high_20'] = df['high'].rolling(20).max()
    df['swing_low_20'] = df['low'].rolling(20).min()
    df['dist_sh_pct'] = (df['swing_high_20'] - df['close']) / df['close'] * 100
    df['dist_sl_pct'] = (df['close'] - df['swing_low_20']) / df['close'] * 100
    
    # 4. Vektörel SMC (Akıllı Para Konseptleri)
    # Fair Value Gap (FVG)
    # Bullish FVG: low[i] > high[i-2]
    # Bearish FVG: high[i] < low[i-2]
    df['fvg_bull'] = (df['low'] > df['high'].shift(2)).astype(int)
    df['fvg_bear'] = (df['high'] < df['low'].shift(2)).astype(int)
    
    df['fvg_bull_size'] = np.where(df['fvg_bull'], (df['low'] - df['high'].shift(2)) / df['close'] * 100, 0)
    df['fvg_bear_size'] = np.where(df['fvg_bear'], (df['low'].shift(2) - df['high']) / df['close'] * 100, 0)
    
    # Liquidity Sweep
    # Mevcut mumun low'u son 20 mumun dibini delip geçtiyse ama close > swing_low ise (Tuzak)
    df['liq_sweep_bull'] = ((df['low'] < df['swing_low_20'].shift(1)) & (df['close'] > df['swing_low_20'].shift(1))).astype(int)
    df['liq_sweep_bear'] = ((df['high'] > df['swing_high_20'].shift(1)) & (df['close'] < df['swing_high_20'].shift(1))).astype(int)
    
    # Kümülatif Hacim (CVD Yaklaşımı - Order Flow)
    # Mum yönüne göre hacmi işaretle
    direction = np.sign(df['close'] - df['open'])
    df['signed_volume'] = df['volume'] * direction
    df['cvd_10'] = df['signed_volume'].rolling(10).sum()
    df['cvd_10_norm'] = df['cvd_10'] / (df['volume'].rolling(10).mean() * 10 + 1e-9)
    
    # Trend Diverjansı (Gizli Zayıflıklar)
    # Fiyat yükseliyor (slope > 0) ama CVD düşüyor (cvd < 0) -> Gizli Satış (Bearish Divergence)
    df['div_bear'] = ((df['slope_10'] > 0) & (df['cvd_10'] < 0)).astype(int)
    df['div_bull'] = ((df['slope_10'] < 0) & (df['cvd_10'] > 0)).astype(int)
    
    # Standart Kuantitatif Metrikler
    df['atr_14_pct'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range() / df['close'] * 100
    df['rsi_14'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
    
    bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
    df['bb_width'] = bb.bollinger_wband()
    bb_width_sma = df['bb_width'].rolling(20).mean()
    df['is_squeeze'] = (df['bb_width'] < (bb_width_sma * 0.8)).astype(int)
    
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    return df

def apply_triple_barrier(df, horizon=24, tp_atr_mult=2.5, sl_atr_mult=1.5):
    targets = np.full(len(df), np.nan)
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    atrs = (df['atr_14_pct'].values / 100) * closes
    
    for i in range(len(df) - horizon):
        entry_price = closes[i]
        curr_atr = atrs[i]
        
        if pd.isna(curr_atr): continue
            
        tp_price = entry_price + (curr_atr * tp_atr_mult)
        sl_price = entry_price - (curr_atr * sl_atr_mult)
        
        hit_tp = False
        hit_sl = False
        
        for j in range(1, horizon + 1):
            if lows[i + j] <= sl_price:
                hit_sl = True
                break
            if highs[i + j] >= tp_price:
                hit_tp = True
                break
                
        if hit_tp and not hit_sl:
            targets[i] = 1
        else:
            targets[i] = 0
            
    df['target'] = targets
    return df

def process_v25_data():
    data_dir = 'bot/engine/data_v24'
    out_dir = 'bot/engine/features_v25'
    os.makedirs(out_dir, exist_ok=True)
    
    # Sadece Mentorün belirlediği Top 5 koin
    TARGET_COINS = ["BTC_USDT.csv", "ETH_USDT.csv", "SOL_USDT.csv", "BNB_USDT.csv", "XRP_USDT.csv"]
    
    for f in TARGET_COINS:
        print(f"Deep Quant Processing: {f}...")
        path = os.path.join(data_dir, f)
        if not os.path.exists(path):
            print(f"  Missing data for {f}")
            continue
            
        df = pd.read_csv(path, parse_dates=['ts'], index_col='ts')
        
        df = engineer_features_v25(df)
        # Daha katı R:R (Kurumsal mantık: 1.5 ATR SL, 2.5 ATR TP)
        df = apply_triple_barrier(df, horizon=36, tp_atr_mult=2.5, sl_atr_mult=1.5) 
        
        # Gereksiz ham veriyi at
        df.dropna(inplace=True)
        out_path = os.path.join(out_dir, f)
        df.to_csv(out_path)
        print(f"  Saved {len(df)} V25 Deep Quant features to {out_path}")

if __name__ == "__main__":
    process_v25_data()
