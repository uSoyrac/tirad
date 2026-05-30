#!/usr/bin/env python3
import sys, os
import pandas as pd
import numpy as np
import ta
import warnings

warnings.filterwarnings("ignore")
from backtest_multi_tf import score_slice_v2, WARMUP, _trend_1d

COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]
TIMEFRAME = "4h"

def get_label(df, start_idx, trend, entry, sl, atr):
    """
    Looks ahead in the dataframe to see if the Limit Order was filled,
    and whether it hit TP or SL first.
    """
    end_idx = min(start_idx + 30, len(df)) # Look ahead 5 days
    slice_ahead = df.iloc[start_idx:end_idx]
    
    tp = entry + atr * 2 if trend == "BULLISH" else entry - atr * 2
    filled = False
    
    for _, row in slice_ahead.iterrows():
        high, low = row["high"], row["low"]
        
        if trend == "BULLISH":
            if not filled and low <= entry:
                filled = True
            if filled:
                if low <= sl: return 0
                if high >= tp: return 1
        else:
            if not filled and high >= entry:
                filled = True
            if filled:
                if high >= sl: return 0
                if low <= tp: return 1
                
    return 0 # Timeout

def build_dataset():
    print("="*60)
    print(" ⚡ VEKTÖRİZE VERİ ÇIKARICI (12 AYLIK TARAMA) ⚡")
    print("="*60)
    
    dataset = []
    
    for coin in COINS:
        print(f"🔄 İşleniyor: {coin}/USDT...")
        # Since this script runs from `uyg/src`, historical data is in `tirad_backtest/data/historical`
        # We'll try to find it there.
        csv_path = f"../../../tirad_backtest/data/historical/{coin}_USDT_{TIMEFRAME}.csv"
        
        if not os.path.exists(csv_path):
            print(f"Veri bulunamadı: {csv_path}")
            continue
            
        df = pd.read_csv(csv_path)
        if len(df) < WARMUP + 50:
            continue
            
        df["ts"] = pd.to_datetime(df["ts"])
        df.sort_values("ts", inplace=True)
        df.reset_index(drop=True, inplace=True)
        
        # Sadece son 12 ay (Yaklaşık 2190 mum - 4 Saatlik)
        df = df.tail(2190).reset_index(drop=True)
        
        # Vektörel İndikatör Hesaplamaları (Çok Hızlı)
        df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
        macd = ta.trend.MACD(df["close"], window_slow=26, window_fast=12, window_sign=9)
        df["macd_hist"] = macd.macd_diff()
        df["vol_sma"] = ta.trend.SMAIndicator(df["volume"], window=20).sma_indicator()
        
        # Sinyal taraması
        for i in range(WARMUP, len(df) - 1):
            df_slice = df.iloc[max(0, i - 300):i]
            comp, trend, entry_, sl_, atr_, vol_ok_ = score_slice_v2(df_slice)
            
            if comp < 4.5 or trend == "NEUTRAL" or entry_ is None: continue
            if _trend_1d(df_slice) != trend: continue
            if not vol_ok_: continue
                
            sl_dist = abs(entry_ - sl_) / entry_
            if not (0.005 < sl_dist <= 0.10): continue
            
            close_px = float(df["close"].iloc[i])
            vol_sma = float(df["vol_sma"].iloc[i])
            
            features = {
                "comp_score": comp,
                "is_bullish": 1 if trend == "BULLISH" else 0,
                "atr_pct": atr_ / close_px * 100,
                "rsi": float(df["rsi"].iloc[i]),
                "macd_hist_norm": float(df["macd_hist"].iloc[i]) / close_px * 1000,
                "vol_ratio": float(df["volume"].iloc[i]) / vol_sma if vol_sma > 0 else 1.0,
                "label": get_label(df, i, trend, entry_, sl_, atr_)
            }
            dataset.append(features)

    df_out = pd.DataFrame(dataset)
    df_out.dropna(inplace=True)
    df_out.to_csv("ml_dataset_12m.csv", index=False)
    
    print(f"\n✅ Veri seti oluşturuldu: ml_dataset_12m.csv ({len(df_out)} işlem örneği)")
    print(f"Başarılı İşlemler (Label=1): {df_out['label'].sum()}")

if __name__ == "__main__":
    build_dataset()
