import pandas as pd
import numpy as np
import os
import sys

# Yolu ekleyelim ki bot module bulunabilsin
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bot.engine.feature_engineer_v25 import engineer_features_v25, apply_triple_barrier

def apply_watcher_target(df, horizon=24, trend_pct=4.0):
    """
    Gözcü Ajan (Watcher) Hedefi:
    Önümüzdeki 'horizon' kadar mum içerisinde, kapanış fiyatına göre
    en yüksek nokta %'trend_pct' (örn: %4) üzerinde bir artış yakalıyor mu?
    Amacı piyasada Chop (Yataylık) bitip gerçek bir trend (volatilite) başlayıp başlamadığını bilmek.
    """
    df = df.copy()
    
    future_high_max = df['high'].rolling(window=horizon, min_periods=1).max().shift(-horizon)
    target_max_up = (future_high_max - df['close']) / df['close'] * 100
    
    # Trend hedefi: %4'ten büyük zıplama varsa 1, yoksa (yatay/düşüş) 0.
    df['target_is_trend'] = (target_max_up >= trend_pct).astype(int)
    
    # NaN'ları temizle (Son horizon kadar mum hedefsiz kalır)
    df.loc[df.index[-horizon:], 'target_is_trend'] = np.nan
    df.dropna(subset=['target_is_trend'], inplace=True)
    
    return df

def process_v37_data():
    data_dir = 'bot/engine/data_v31'
    out_dir = 'bot/engine/features_v37'
    os.makedirs(out_dir, exist_ok=True)
    
    # Top 5 koin
    TARGET_COINS = ["BTC_USDT.csv", "ETH_USDT.csv", "SOL_USDT.csv", "BNB_USDT.csv", "XRP_USDT.csv"]
    
    for f in TARGET_COINS:
        print(f"V37 Multi-Agent Feature Extraction: {f}...")
        path = os.path.join(data_dir, f)
        if not os.path.exists(path):
            print(f"  Veri bulunamadı: {path}")
            continue
            
        df = pd.read_csv(path, parse_dates=['ts'])
        df.sort_values('ts', inplace=True)
        df.reset_index(drop=True, inplace=True)
        
        # 1. Base features (V25'ten)
        df = engineer_features_v25(df)
        
        # 2. Keskin Nişancı Hedefi (Sniper - Yön ve Kırılım)
        df = apply_triple_barrier(df, horizon=36, tp_atr_mult=2.5, sl_atr_mult=1.5)
        
        # 3. Gözcü Ajan Hedefi (Watcher - Chop Filtresi)
        df = apply_watcher_target(df, horizon=36, trend_pct=4.0)
        
        df.dropna(inplace=True)
        
        out_path = os.path.join(out_dir, f)
        df.to_csv(out_path, index=False)
        print(f"  Kaydedildi: {len(df)} mum -> {out_path}")

if __name__ == "__main__":
    process_v37_data()
