import pandas as pd
import numpy as np
import os
import sys

# Yolu ekleyelim ki bot module bulunabilsin
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bot.engine.feature_engineer_v25 import engineer_features_v25

def apply_omniscient_targets(df, horizon=24, barrier_atr_mult=1.5):
    """
    V33: 3 Ayrı Yapay Zeka Hedefi Üretir.
    1. target_dir: Gelecek 24 mumda önce yukarı bariyer vurursa 1 (LONG), aşağı vurursa -1 (SHORT), hiçbiri 0 (FLAT).
    2. target_max_up: Gelecek 24 mumdaki MAKSİMUM Yükseliş Yüzdesi.
    3. target_max_down: Gelecek 24 mumdaki MAKSİMUM Düşüş Yüzdesi (Pozitif değer = zarar büyüklüğü).
    """
    df = df.copy()
    
    # 1. Regresyon Hedefleri (Max Up / Max Down)
    # rolling(window).max().shift(-window) = Mevcut mumdan sonraki N mumun maksimumu
    future_high_max = df['high'].rolling(window=horizon, min_periods=1).max().shift(-horizon)
    future_low_min = df['low'].rolling(window=horizon, min_periods=1).min().shift(-horizon)
    
    df['target_max_up'] = (future_high_max - df['close']) / df['close'] * 100
    df['target_max_down'] = (df['close'] - future_low_min) / df['close'] * 100
    
    # 2. Sınıflandırma Hedefi (Yön)
    targets_dir = np.zeros(len(df))
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    
    if 'atr_14_pct' not in df.columns:
        import ta
        df['atr_14_pct'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range() / df['close'] * 100

    atrs = (df['atr_14_pct'].values / 100) * closes
    
    for i in range(len(df) - horizon):
        entry_price = closes[i]
        curr_atr = atrs[i]
        
        if pd.isna(curr_atr): continue
            
        up_barrier = entry_price + (curr_atr * barrier_atr_mult)
        down_barrier = entry_price - (curr_atr * barrier_atr_mult)
        
        dir_val = 0
        for j in range(1, horizon + 1):
            if highs[i + j] >= up_barrier and lows[i + j] <= down_barrier:
                # Aynı mumda ikisine de vuruyorsa flat sayalım (kararsız)
                dir_val = 0
                break
            elif highs[i + j] >= up_barrier:
                dir_val = 1
                break
            elif lows[i + j] <= down_barrier:
                dir_val = -1
                break
                
        targets_dir[i] = dir_val
            
    df['target_dir'] = targets_dir
    
    # NaN'ları temizle (Son horizon kadar mum hedefsiz kalır)
    df.dropna(subset=['target_max_up', 'target_max_down', 'target_dir'], inplace=True)
    return df

def process_v33_data():
    data_dir = 'bot/engine/data_v31'
    out_dir = 'bot/engine/features_v33'
    os.makedirs(out_dir, exist_ok=True)
    
    # Top 5 koin
    TARGET_COINS = ["BTC_USDT.csv", "ETH_USDT.csv", "SOL_USDT.csv", "BNB_USDT.csv", "XRP_USDT.csv"]
    
    for f in TARGET_COINS:
        print(f"V33 Omniscient Feature Extraction: {f}...")
        path = os.path.join(data_dir, f)
        if not os.path.exists(path):
            print(f"  Veri bulunamadı: {path}")
            continue
            
        df = pd.read_csv(path, parse_dates=['ts'])
        df.sort_values('ts', inplace=True)
        df.reset_index(drop=True, inplace=True)
        
        # Base features (V25'ten)
        df = engineer_features_v25(df)
        
        # Omniscient 3x hedefler
        df = apply_omniscient_targets(df, horizon=24, barrier_atr_mult=1.5)
        
        out_path = os.path.join(out_dir, f)
        df.to_csv(out_path, index=False)
        print(f"  Kaydedildi: {len(df)} mum -> {out_path}")

if __name__ == "__main__":
    process_v33_data()
