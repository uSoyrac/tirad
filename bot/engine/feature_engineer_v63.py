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

def engineer_features_v63(df):
    df = df.copy()
    
    # 1. Temporal (Zaman)
    df['hour'] = df['ts'].dt.hour
    df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
    df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
    
    # 2. Supertrend & Keltner
    df = calc_supertrend(df, period=10, multiplier=3.0)
    ema_20 = df['close'].ewm(span=20).mean()
    atr_20 = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=20).average_true_range()
    df['kc_upper'] = ema_20 + (1.5 * atr_20)
    
    # 3. V63 SMART MONEY (ORDERFLOW) TEORİSİ EKLENTİLERİ
    # Trade Size (Ortalama İşlem Büyüklüğü) = Hacim (USD) / İşlem Yapan Kişi Sayısı
    df['trade_size'] = df['quote_asset_volume'] / (df['number_of_trades'] + 1)
    
    # Trade Size Türevi (Geçmişe göre balina akışı var mı?)
    trade_size_24h_avg = df['trade_size'].rolling(window=96).mean()
    df['whale_anomaly'] = df['trade_size'] / (trade_size_24h_avg + 1e-9)
    
    # Taker Buy Ratio (Hacmin ne kadarı 'Agresif Alıcı'?)
    df['taker_buy_ratio'] = df['taker_buy_base_asset_volume'] / (df['volume'] + 1e-9)
    taker_buy_24h_avg = df['taker_buy_ratio'].rolling(window=96).mean()
    df['taker_buy_surge'] = df['taker_buy_ratio'] / (taker_buy_24h_avg + 1e-9)
    
    # 4. Standart AI Verileri
    df['dist_ema50'] = (df['close'] - df['close'].ewm(span=50).mean()) / df['close'].ewm(span=50).mean()
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

def process_v63_data():
    data_dir = 'bot/engine/data_v63'
    out_dir = 'bot/engine/features_v63'
    os.makedirs(out_dir, exist_ok=True)
    
    files = [f for f in os.listdir(data_dir) if f.endswith('.csv')]
    
    for f in files:
        print(f"V63 Smart Money Feature Extraction: {f}...")
        path = os.path.join(data_dir, f)
        
        df = pd.read_csv(path, parse_dates=['ts'])
        df.sort_values('ts', inplace=True)
        df.reset_index(drop=True, inplace=True)
        
        df = engineer_features_v63(df)
        df = apply_betting_targets(df, horizon=32, tp_pct=0.020, sl_pct=0.010) 
        
        df.dropna(inplace=True)
        
        out_path = os.path.join(out_dir, f)
        df.to_csv(out_path, index=False)
        print(f"  Kaydedildi: {len(df)} mum -> {out_path}")

if __name__ == "__main__":
    process_v63_data()
