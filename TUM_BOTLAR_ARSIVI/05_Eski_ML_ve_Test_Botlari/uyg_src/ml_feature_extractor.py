#!/usr/bin/env python3
import os, sys, time, warnings
import pandas as pd
import numpy as np
import ta

warnings.filterwarnings("ignore")

# Import necessary components from the existing framework
from backtest_multi_tf import score_slice_v2, WARMUP, _trend_1d
from realistic_limit_backtester import get_entry_levels, run_backtest_strategy

COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]
TIMEFRAME = "4h"

def precalculate_signals_with_features(df_full):
    total = len(df_full)
    signals = {}
    
    try:
        df_full["rsi"] = ta.momentum.RSIIndicator(df_full["close"], window=14).rsi()
        macd = ta.trend.MACD(df_full["close"], window_slow=26, window_fast=12, window_sign=9)
        df_full["macd_hist"] = macd.macd_diff()
        df_full["vol_sma"] = ta.trend.SMAIndicator(df_full["volume"], window=20).sma_indicator()
    except Exception as e:
        df_full["rsi"] = 50.0
        df_full["macd_hist"] = 0.0
        df_full["vol_sma"] = 0.0
        
    for i in range(WARMUP, total - 1):
        if i % 100 == 0:
            sys.stdout.write(".")
            sys.stdout.flush()
            
        df_slice = df_full.iloc[max(0, i - 300):i]
        comp, trend, entry_, sl_, atr_, vol_ok_ = score_slice_v2(df_slice)
        
        if comp < 4.5 or trend == "NEUTRAL" or entry_ is None:
            continue
            
        trend_1d = _trend_1d(df_slice)
        if trend_1d != "NEUTRAL" and trend_1d != trend:
            continue
            
        if not vol_ok_:
            continue
            
        sl_dist = abs(entry_ - sl_) / entry_
        if not (0.005 < sl_dist <= 0.10):
            continue
            
        ob_high, ob_mid, ob_low = get_entry_levels(df_slice, trend, atr_)
        
        # --- FEATURE EXTRACTION ---
        bar_ts = df_full.index[i]
        rsi = float(df_full["rsi"].iloc[i])
        macd_h = float(df_full["macd_hist"].iloc[i])
        vol = float(df_full["volume"].iloc[i])
        vol_sma = float(df_full["vol_sma"].iloc[i])
        close_px = float(df_full["close"].iloc[i])
        
        features = {
            "comp_score": comp,
            "is_bullish": 1 if trend == "BULLISH" else 0,
            "atr_pct": atr_ / close_px * 100,
            "rsi": rsi,
            "macd_hist_norm": macd_h / close_px * 1000,
            "vol_ratio": vol / vol_sma if vol_sma > 0 else 1.0,
            "hour": bar_ts.hour,
            "day_of_week": bar_ts.dayofweek
        }
        
        signals[i] = {
            "comp": comp,
            "trend": trend,
            "entry_": entry_,
            "sl_": sl_,
            "atr_": atr_,
            "ob_high": ob_high,
            "ob_mid": ob_mid,
            "ob_low": ob_low,
            "features": features,
            "bar_ts": str(bar_ts) # Store TS to match with trades
        }
    print(" Done!")
    return signals

def main():
    print("="*80)
    print("  🚀 ML FEATURE EXTRACTOR (XGBoost Veri Seti Hazırlığı)")
    print("="*80)
    
    dataset = []
    
    for i, coin in enumerate(COINS):
        print(f"\n  [{i+1}/{len(COINS)}] {coin}/USDT ({TIMEFRAME}) işleniyor...")
        csv_path = f"data/historical/{coin}_USDT_{TIMEFRAME}.csv"
        if not os.path.exists(csv_path): continue
            
        df = pd.read_csv(csv_path)
        if len(df) < WARMUP + 50: continue
            
        df["ts"] = pd.to_datetime(df["ts"])
        df.set_index("ts", inplace=True)
        df = df.sort_index()
        # Ensure we have enough data (e.g. 2190 bars = 1 year 4H)
        df = df.tail(2190)
        
        print("   Özellikler (Features) hesaplanıyor...")
        signals = precalculate_signals_with_features(df)
        print(f"   Sinyal sayısı: {len(signals)}")
        
        # Test scale-in to see WHICH signals actually filled and their results
        trades = run_backtest_strategy(coin, df, signals, strategy_type="scale_in")
        
        # Match trades back to signals
        # trades list dict has 'entry_date' which matches signal 'bar_ts' or 'entry_date' + delay
        # But wait, run_backtest_strategy stores t_entry_date as str(bar_ts)[:16].
        
        # To accurately map them, we can check the exit_date or entry_date in trades
        # Or even better, we can just match by score or just modify the trades to carry the signal ID!
        # Since we cannot easily rewrite run_backtest_strategy here without copying it, 
        # we can match by 'score' and 'entry_date' string approximation.
        
        filled_count = 0
        for t in trades:
            t_score = t["score"]
            t_entry_dt = pd.to_datetime(t["entry_date"]).date() # rough match
            
            # Find the corresponding signal
            matched_sig = None
            for idx, sig in signals.items():
                sig_dt = pd.to_datetime(sig["bar_ts"]).date()
                if abs(sig["comp"] - t_score) < 0.01 and abs((sig_dt - t_entry_dt).days) <= 2:
                    matched_sig = sig
                    break
            
            if matched_sig:
                # 1 if trade ended in profit (TP1/TP2/TP3/Trail), 0 if stopped out (-1R)
                label = 1 if t["r_mult"] > 0 else 0
                
                row = matched_sig["features"].copy()
                row["coin"] = coin
                row["r_mult"] = t["r_mult"]
                row["label"] = label
                dataset.append(row)
                filled_count += 1
                
        print(f"   Eşleşen İşlem (Label): {filled_count}")

    if dataset:
        df_out = pd.DataFrame(dataset)
        df_out.to_csv("ml_dataset.csv", index=False)
        print(f"\n✅ Veri seti kaydedildi: ml_dataset.csv ({len(df_out)} satır)")
    else:
        print("\n❌ Eşleşen işlem bulunamadı, veri seti boş.")

if __name__ == "__main__":
    main()
