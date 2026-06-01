import pandas as pd
import numpy as np
import os
import sys
import ta

def engineer_features_15m(df):
    df = df.copy()
    
    # 1. Trend & Volatilite (ADX & ATR)
    adx_ind = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
    df['adx_14'] = adx_ind.adx()
    
    atr_ind = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14)
    df['atr_14'] = atr_ind.average_true_range()
    df['atr_14_pct'] = (df['atr_14'] / df['close']) * 100
    
    # 2. Bollinger Bantları (Ajan 2: Sıkışma)
    bb_ind = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
    df['bb_upper'] = bb_ind.bollinger_hband()
    df['bb_lower'] = bb_ind.bollinger_lband()
    df['bb_mid'] = bb_ind.bollinger_mavg()
    df['bb_width'] = bb_ind.bollinger_wband() # Squeeze (sıkışma) tespiti için
    
    # 3. Hacim (Ajan 3: Yakıt)
    obv_ind = ta.volume.OnBalanceVolumeIndicator(df['close'], df['volume'])
    df['obv'] = obv_ind.on_balance_volume()
    df['vol_ma_20'] = df['volume'].rolling(window=20).mean()
    df['vol_spike'] = np.where(df['volume'] > (df['vol_ma_20'] * 1.5), 1, 0)
    
    # Gecikmeli özellikler (Momentum)
    df['ret_1'] = df['close'].pct_change(1)
    df['ret_4'] = df['close'].pct_change(4) # 1 Saatlik momentum
    
    return df

def apply_scalper_targets(df, horizon=16, tp_pct=0.02, sl_pct=0.005):
    """
    15m Scalping Hedefleri:
    - 10x kaldıraç kullanılacağı için hedefler yüzdesel olarak çok dardır.
    - tp_pct = 0.02 (%2 fiyat hareketi = %20 ROE)
    - sl_pct = 0.005 (%0.5 fiyat düşüşü = %5 ROE zarar, insan eliyle yapılan sıkı stop)
    """
    df = df.copy()
    
    # Ajan 1 (Gözcü) Hedefi: Macro Trend
    # Önümüzdeki 16 barda (4 saat) %1.5'ten fazla yükseliş var mı?
    future_max = df['high'].rolling(window=horizon, min_periods=1).max().shift(-horizon)
    target_max_up = (future_max - df['close']) / df['close']
    df['target_is_trend'] = (target_max_up >= 0.015).astype(int)
    
    # Ajan 2 (Nişancı) Hedefi: Vur-Kaç (Triple Barrier)
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
    
    # Son horizon kadar veriyi temizle
    df.loc[df.index[-horizon:], ['target_is_trend', 'target']] = np.nan
    df.dropna(inplace=True)
    
    return df

def process_v39_data():
    data_dir = 'bot/engine/data_v39'
    out_dir = 'bot/engine/features_v39'
    os.makedirs(out_dir, exist_ok=True)
    
    files = [f for f in os.listdir(data_dir) if f.endswith('.csv')]
    
    for f in files:
        print(f"V39 15m Feature Extraction: {f}...")
        path = os.path.join(data_dir, f)
        
        df = pd.read_csv(path, parse_dates=['ts'])
        df.sort_values('ts', inplace=True)
        df.reset_index(drop=True, inplace=True)
        
        df = engineer_features_15m(df)
        df = apply_scalper_targets(df, horizon=16, tp_pct=0.02, sl_pct=0.005)
        
        df.dropna(inplace=True)
        
        out_path = os.path.join(out_dir, f)
        df.to_csv(out_path, index=False)
        print(f"  Kaydedildi: {len(df)} 15m mum -> {out_path}")

if __name__ == "__main__":
    process_v39_data()
