import pandas as pd
import numpy as np
import ta
import os

def engineer_features_v24(df):
    df = df.copy()
    
    # Klasik İndikatörler
    df['rsi_14'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
    df['rsi_21'] = ta.momentum.RSIIndicator(df['close'], window=21).rsi()
    
    macd = ta.trend.MACD(df['close'], window_slow=26, window_fast=12, window_sign=9)
    df['macd_line'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    df['macd_hist'] = macd.macd_diff()
    
    stoch = ta.momentum.StochasticOscillator(df['high'], df['low'], df['close'], window=14, smooth_window=3)
    df['stoch_k'] = stoch.stoch()
    
    # Volatilite & Range
    df['atr_14'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range()
    df['atr_pct'] = (df['atr_14'] / df['close']) * 100
    
    bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
    df['bb_width'] = bb.bollinger_wband()
    df['bb_pct_b'] = bb.bollinger_pband()
    
    # YENİ: Squeeze (BB Daralması) - Keltner kanalı ile de ölçülebilir ama pratik olarak bb_width ortalamasına uzaklık
    bb_width_sma = df['bb_width'].rolling(20).mean()
    df['is_squeeze'] = (df['bb_width'] < (bb_width_sma * 0.8)).astype(int)
    
    # EMA Uzaklıkları
    ema20 = ta.trend.EMAIndicator(df['close'], window=20).ema_indicator()
    ema50 = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
    ema200 = ta.trend.EMAIndicator(df['close'], window=200).ema_indicator()
    
    df['dist_ema20_pct'] = (df['close'] - ema20) / ema20 * 100
    df['dist_ema50_pct'] = (df['close'] - ema50) / ema50 * 100
    df['dist_ema200_pct'] = (df['close'] - ema200) / ema200 * 100
    
    # YENİ: Hacim Patlamaları (Volume Climax)
    vol_mean = df['volume'].rolling(50).mean()
    vol_std = df['volume'].rolling(50).std()
    df['vol_climax'] = (df['volume'] > (vol_mean + 2.5 * vol_std)).astype(int)
    df['vol_ratio'] = df['volume'] / (vol_mean + 1e-9)
    
    # Zaman Özellikleri (Kurumsal işlem saatleri)
    df['hour'] = df.index.hour
    df['dayofweek'] = df.index.dayofweek
    df['is_london'] = ((df['hour'] >= 8) & (df['hour'] <= 12)).astype(int)
    df['is_ny'] = ((df['hour'] >= 13) & (df['hour'] <= 17)).astype(int)
    df['is_asia'] = ((df['hour'] >= 0) & (df['hour'] <= 6)).astype(int)
    
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    return df

def apply_triple_barrier(df, horizon=24, tp_atr_mult=2.5, sl_atr_mult=1.5):
    """
    Triple Barrier Method (Makine Öğrenmesi Standart Etiketleme)
    1. Üst Bariyer (Take Profit): Entry + (ATR * 2.5)
    2. Alt Bariyer (Stop Loss): Entry - (ATR * 1.5)
    3. Zaman Bariyeri: Entry'den sonraki 24 saat (1H için 24 bar)
    
    Eğer önce TP vurulursa: 1 (Başarılı)
    Önce SL vurulursa veya Zaman Bariyeri biterse: 0 (Başarısız)
    """
    targets = np.full(len(df), np.nan)
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    atrs = df['atr_14'].values
    
    for i in range(len(df) - horizon):
        entry_price = closes[i]
        curr_atr = atrs[i]
        
        if pd.isna(curr_atr):
            continue
            
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

def process_v24_data():
    data_dir = 'bot/engine/data_v24'
    out_dir = 'bot/engine/features_v24'
    os.makedirs(out_dir, exist_ok=True)
    
    files = [f for f in os.listdir(data_dir) if f.endswith('.csv')]
    for f in files:
        print(f"Processing {f}...")
        df = pd.read_csv(os.path.join(data_dir, f), parse_dates=['ts'], index_col='ts')
        
        df = engineer_features_v24(df)
        df = apply_triple_barrier(df, horizon=24, tp_atr_mult=2.0, sl_atr_mult=1.2) # R:R = 1.6
        
        df.dropna(inplace=True)
        out_path = os.path.join(out_dir, f)
        df.to_csv(out_path)
        print(f"  Saved {len(df)} rows to {out_path}")

if __name__ == "__main__":
    process_v24_data()
