#!/usr/bin/env python3
import os, sys, warnings
import pandas as pd
import ta

warnings.filterwarnings("ignore")
from backtest_multi_tf import score_slice_v2, WARMUP, _trend_1d

COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]
TIMEFRAME = "4h"

def get_fast_label(df_full, start_idx, trend, entry, sl, atr):
    # Look ahead 30 bars (5 days)
    end_idx = min(start_idx + 30, len(df_full))
    slice_ahead = df_full.iloc[start_idx:end_idx]
    
    tp = entry + atr * 2 if trend == "BULLISH" else entry - atr * 2
    
    for _, row in slice_ahead.iterrows():
        high, low = row["high"], row["low"]
        
        if trend == "BULLISH":
            if low <= sl: return 0
            if high >= tp: return 1
        else:
            if high >= sl: return 0
            if low <= tp: return 1
            
    return 0 # Timeout/No hit

def main():
    print("="*60)
    print("  🚀 HIZLI ML FEATURE EXTRACTOR")
    print("="*60)
    
    dataset = []
    
    for i, coin in enumerate(COINS):
        print(f"\n[{i+1}/5] {coin}/USDT işleniyor...")
        csv_path = f"data/historical/{coin}_USDT_{TIMEFRAME}.csv"
        if not os.path.exists(csv_path): continue
            
        df = pd.read_csv(csv_path)
        if len(df) < WARMUP + 50: continue
            
        df["ts"] = pd.to_datetime(df["ts"])
        df.set_index("ts", inplace=True)
        df = df.sort_index()
        df = df.tail(2190)
        
        try:
            df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
            macd = ta.trend.MACD(df["close"], window_slow=26, window_fast=12, window_sign=9)
            df["macd_hist"] = macd.macd_diff()
            df["vol_sma"] = ta.trend.SMAIndicator(df["volume"], window=20).sma_indicator()
        except:
            continue
            
        signals_found = 0
        for i in range(WARMUP, len(df) - 1):
            df_slice = df.iloc[max(0, i - 300):i]
            comp, trend, entry_, sl_, atr_, vol_ok_ = score_slice_v2(df_slice)
            
            if comp < 4.5 or trend == "NEUTRAL" or entry_ is None: continue
            if _trend_1d(df_slice) != trend: continue
            if not vol_ok_: continue
                
            sl_dist = abs(entry_ - sl_) / entry_
            if not (0.005 < sl_dist <= 0.10): continue
            
            bar_ts = df.index[i]
            close_px = float(df["close"].iloc[i])
            vol_sma = float(df["vol_sma"].iloc[i])
            
            features = {
                "coin": coin,
                "comp_score": comp,
                "is_bullish": 1 if trend == "BULLISH" else 0,
                "atr_pct": atr_ / close_px * 100,
                "rsi": float(df["rsi"].iloc[i]),
                "macd_hist_norm": float(df["macd_hist"].iloc[i]) / close_px * 1000,
                "vol_ratio": float(df["volume"].iloc[i]) / vol_sma if vol_sma > 0 else 1.0,
                "hour": bar_ts.hour,
                "day_of_week": bar_ts.dayofweek
            }
            
            label = get_fast_label(df, i, trend, entry_, sl_, atr_)
            features["label"] = label
            dataset.append(features)
            signals_found += 1
            
        print(f"Sinyal Sayısı: {signals_found}")

    if dataset:
        pd.DataFrame(dataset).to_csv("ml_dataset.csv", index=False)
        print(f"\n✅ Veri seti kaydedildi: ml_dataset.csv ({len(dataset)} satır)")

if __name__ == "__main__":
    main()
