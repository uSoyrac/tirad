import pandas as pd
import numpy as np
import ta
import os

def engineer_features(df):
    df = df.copy()
    
    # 1. Klasik TA İndikatörleri (Momentum)
    df['rsi_14'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
    df['rsi_21'] = ta.momentum.RSIIndicator(df['close'], window=21).rsi()
    
    macd = ta.trend.MACD(df['close'], window_slow=26, window_fast=12, window_sign=9)
    df['macd_line'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    df['macd_hist'] = macd.macd_diff()
    
    stoch = ta.momentum.StochasticOscillator(df['high'], df['low'], df['close'], window=14, smooth_window=3)
    df['stoch_k'] = stoch.stoch()
    df['stoch_d'] = stoch.stoch_signal()
    
    # 2. Volatilite & Range
    df['atr_14'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range()
    df['atr_pct'] = (df['atr_14'] / df['close']) * 100
    
    bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
    df['bb_width'] = bb.bollinger_wband()
    df['bb_pct_b'] = bb.bollinger_pband()
    
    # 3. Trend İndikatörleri
    df['adx_14'] = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14).adx()
    
    ema20 = ta.trend.EMAIndicator(df['close'], window=20).ema_indicator()
    ema50 = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
    ema200 = ta.trend.EMAIndicator(df['close'], window=200).ema_indicator()
    
    df['dist_ema20_pct'] = (df['close'] - ema20) / ema20 * 100
    df['dist_ema50_pct'] = (df['close'] - ema50) / ema50 * 100
    df['dist_ema200_pct'] = (df['close'] - ema200) / ema200 * 100
    
    # 4. Hacim
    df['vol_sma_20'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_sma_20']
    
    df['obv'] = ta.volume.OnBalanceVolumeIndicator(df['close'], df['volume']).on_balance_volume()
    df['obv_roc'] = df['obv'].pct_change(periods=5) * 100  # 5 bar OBV değişimi
    
    # 5. Price Action / Mum Yapısı
    df['body_size'] = abs(df['close'] - df['open']) / df['open'] * 100
    df['upper_wick'] = (df['high'] - np.maximum(df['close'], df['open'])) / df['open'] * 100
    df['lower_wick'] = (np.minimum(df['close'], df['open']) - df['low']) / df['open'] * 100
    
    # 6. Zaman Özellikleri (Session & Seasonality)
    df['hour'] = df.index.hour
    df['dayofweek'] = df.index.dayofweek
    df['is_london'] = ((df['hour'] >= 8) & (df['hour'] <= 16)).astype(int)
    df['is_ny'] = ((df['hour'] >= 13) & (df['hour'] <= 21)).astype(int)
    df['is_asia'] = ((df['hour'] >= 0) & (df['hour'] <= 8)).astype(int)
    
    # 7. Lagged Features (Geçmiş barlar)
    for i in [1, 2, 3]:
        df[f'ret_{i}'] = df['close'].pct_change(periods=i) * 100
        df[f'vol_ratio_lag_{i}'] = df['vol_ratio'].shift(i)
    
    # NaN temizliği (TA hesaplamaları başlarda NaN üretir)
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df.dropna(inplace=True)
    
    return df

def generate_targets(df, horizon=3, stop_loss_pct=1.5, take_profit_pct=3.0):
    """
    Horizon: İleriye dönük bakılacak bar sayısı (ör: 3 bar = 12 saat)
    Hedef: Max High > TP ise 1, aksi halde 0 (Basit sınıflandırma)
    Alternatif: Eğer Low < SL ise 0 (Stop oldu), High > TP ise 1, İkisi de yoksa son fiyata bak.
    """
    targets = []
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    
    for i in range(len(df)):
        if i + horizon >= len(df):
            targets.append(np.nan)
            continue
            
        entry_price = closes[i]
        tp_price = entry_price * (1 + take_profit_pct / 100)
        sl_price = entry_price * (1 - stop_loss_pct / 100)
        
        hit_tp = False
        hit_sl = False
        
        for j in range(1, horizon + 1):
            if lows[i + j] <= sl_price:
                hit_sl = True
                break
            if highs[i + j] >= tp_price:
                hit_tp = True
                break
                
        if hit_tp:
            targets.append(1) # Başarılı Long
        else:
            targets.append(0) # Başarısız Long
            
    df['target'] = targets
    return df

def process_all_data():
    data_dir = 'bot/engine/data'
    out_dir = 'bot/engine/features'
    os.makedirs(out_dir, exist_ok=True)
    
    files = [f for f in os.listdir(data_dir) if f.endswith('.csv')]
    for f in files:
        print(f"Processing {f}...")
        df = pd.read_csv(os.path.join(data_dir, f), parse_dates=['ts'], index_col='ts')
        
        df = engineer_features(df)
        df = generate_targets(df, horizon=6, stop_loss_pct=1.0, take_profit_pct=2.5) # 6 bar = 24 saat, 1:2.5 RR
        
        df.dropna(inplace=True)
        out_path = os.path.join(out_dir, f)
        df.to_csv(out_path)
        print(f"  Saved {len(df)} rows with features & targets to {out_path}")

if __name__ == "__main__":
    process_all_data()
