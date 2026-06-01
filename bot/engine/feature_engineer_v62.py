import pandas as pd
import numpy as np
import os
import ta

def calc_supertrend(df, period=10, multiplier=3.0):
    df = df.copy()
    atr = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=period).average_true_range()
    hl2 = (df['high'] + df['low']) / 2
    
    basic_upperband = hl2 + (multiplier * atr)
    basic_lowerband = hl2 - (multiplier * atr)
    
    final_upperband = np.zeros(len(df))
    final_lowerband = np.zeros(len(df))
    supertrend = np.zeros(len(df))
    direction = np.ones(len(df))
    
    close = df['close'].values
    basic_ub = basic_upperband.values
    basic_lb = basic_lowerband.values
    
    for i in range(1, len(df)):
        if basic_ub[i] < final_upperband[i-1] or close[i-1] > final_upperband[i-1]:
            final_upperband[i] = basic_ub[i]
        else:
            final_upperband[i] = final_upperband[i-1]
            
        if basic_lb[i] > final_lowerband[i-1] or close[i-1] < final_lowerband[i-1]:
            final_lowerband[i] = basic_lb[i]
        else:
            final_lowerband[i] = final_lowerband[i-1]
            
        if supertrend[i-1] == final_upperband[i-1] and close[i] <= final_upperband[i]:
            direction[i] = -1
        elif supertrend[i-1] == final_upperband[i-1] and close[i] >= final_upperband[i]:
            direction[i] = 1
        elif supertrend[i-1] == final_lowerband[i-1] and close[i] >= final_lowerband[i]:
            direction[i] = 1
        elif supertrend[i-1] == final_lowerband[i-1] and close[i] <= final_lowerband[i]:
            direction[i] = -1
            
        if direction[i] == 1:
            supertrend[i] = final_lowerband[i]
        else:
            supertrend[i] = final_upperband[i]
            
    df['supertrend_dir'] = direction
    return df

def engineer_features_v62(df):
    df = df.copy()
    
    # 1. Saatlerin Kodlanması (Temporal Encoding for AI)
    df['hour'] = df['ts'].dt.hour
    df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
    df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
    
    # 2. Supertrend (Kıvılcım)
    df = calc_supertrend(df, period=10, multiplier=3.0)
    
    # 3. Hacim Türevi (Volume Derivative)
    vol_1h = df['volume'].rolling(window=4).sum()
    vol_24h_avg = df['volume'].rolling(window=96).mean() * 4
    df['vol_derivative'] = vol_1h / (vol_24h_avg + 1e-9)
    df['smart_money_spike'] = np.where(df['vol_derivative'] > 2.5, 1, 0)
    
    # 4. Gövde/Fitil Oranı
    body = np.abs(df['close'] - df['open'])
    upper_wick = df['high'] - np.maximum(df['close'], df['open'])
    lower_wick = np.minimum(df['close'], df['open']) - df['low']
    total_len = df['high'] - df['low']
    
    df['body_ratio'] = body / (total_len + 1e-9)
    df['upper_wick_ratio'] = upper_wick / (total_len + 1e-9)
    df['lower_wick_ratio'] = lower_wick / (total_len + 1e-9)
    
    # 5. Ortalama Uzaklığı
    ema_50 = df['close'].ewm(span=50, adjust=False).mean()
    ema_200 = df['close'].ewm(span=200, adjust=False).mean()
    
    df['dist_ema50'] = (df['close'] - ema_50) / ema_50
    df['dist_ema200'] = (df['close'] - ema_200) / ema_200
    
    # 6. Keltner Channel
    ema_20 = df['close'].ewm(span=20).mean()
    atr_20 = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=20).average_true_range()
    df['kc_upper'] = ema_20 + (1.5 * atr_20)
    
    # 7. Trend İvmesi (MACD) ve Aşırı Alım/Satım (RSI)
    macd = ta.trend.MACD(df['close'])
    df['macd_diff'] = macd.macd_diff()
    df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
    
    return df

def apply_betting_targets(df, horizon=32, tp_pct=0.020, sl_pct=0.010):
    df = df.copy()
    targets = np.zeros(len(df))
    close_prices = df['close'].values
    high_prices = df['high'].values
    low_prices = df['low'].values
    
    for i in range(len(df) - horizon):
        entry_price = close_prices[i]
        if pd.isna(entry_price):
            continue
            
        tp_price = entry_price * (1 + tp_pct)
        sl_price = entry_price * (1 - sl_pct)
        
        hit_tp = False
        hit_sl = False
        
        for j in range(1, horizon + 1):
            if low_prices[i + j] <= sl_price:
                hit_sl = True
                break
            if high_prices[i + j] >= tp_price:
                hit_tp = True
                break
                
        if hit_tp and not hit_sl:
            targets[i] = 1
            
    df['target'] = targets
    df.loc[df.index[-horizon:], 'target'] = np.nan
    return df

def process_v62_data():
    data_dir = 'bot/engine/data_v39'
    out_dir = 'bot/engine/features_v62'
    os.makedirs(out_dir, exist_ok=True)
    
    files = [f for f in os.listdir(data_dir) if f.endswith('.csv')]
    
    for f in files:
        print(f"V62 Holy Grail Feature Extraction: {f}...")
        path = os.path.join(data_dir, f)
        
        df = pd.read_csv(path, parse_dates=['ts'])
        df.sort_values('ts', inplace=True)
        df.reset_index(drop=True, inplace=True)
        
        df = engineer_features_v62(df)
        df = apply_betting_targets(df, horizon=32, tp_pct=0.020, sl_pct=0.010) 
        
        df.dropna(inplace=True)
        
        out_path = os.path.join(out_dir, f)
        df.to_csv(out_path, index=False)
        print(f"  Kaydedildi: {len(df)} 15m mum -> {out_path}")

if __name__ == "__main__":
    process_v62_data()
