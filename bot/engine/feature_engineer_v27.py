import pandas as pd
import os
import sys

# Import the existing V25 deep quant logic
from bot.engine.feature_engineer_v25 import engineer_features_v25, apply_triple_barrier

def process_v27_data():
    data_dir = 'bot/engine/data_v24' # 1H Data
    out_dir = 'bot/engine/features_v27'
    os.makedirs(out_dir, exist_ok=True)
    
    TARGET_COINS = ["BTC_USDT.csv", "ETH_USDT.csv", "SOL_USDT.csv", "BNB_USDT.csv", "XRP_USDT.csv"]
    
    for f in TARGET_COINS:
        print(f"1H Deep Quant V27 Processing: {f}...")
        path = os.path.join(data_dir, f)
        if not os.path.exists(path):
            continue
            
        df = pd.read_csv(path, parse_dates=['ts'], index_col='ts')
        
        df = engineer_features_v25(df)
        
        # Asimetrik R:R - 3.5 TP, 1.5 SL. Zaman Bariyeri: 36 Saat
        df = apply_triple_barrier(df, horizon=36, tp_atr_mult=3.5, sl_atr_mult=1.5) 
        
        df.dropna(inplace=True)
        out_path = os.path.join(out_dir, f)
        df.to_csv(out_path)
        print(f"  Saved {len(df)} V27 (1H) features to {out_path}")

if __name__ == "__main__":
    process_v27_data()
