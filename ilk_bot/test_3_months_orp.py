#!/usr/bin/env python3
import sys, os
import pandas as pd
import numpy as np
import xgboost as xgb
import warnings
import ta

warnings.filterwarnings("ignore")

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "uyg", "src"))
from backtest_multi_tf import score_slice_v2, _trend_1d
from realistic_limit_backtester import get_entry_levels
from dynamic_optimizer import run_orp_dynamic

COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]
TIMEFRAME = "4h"

def get_trade_result(df, start_idx, trend, l1, l2, sl):
    end_idx = min(start_idx + 60, len(df)) # lookahead ~10 days
    slice_ahead = df.iloc[start_idx:end_idx]
    
    avg_entry = (l1 + l2) / 2
    risk_dist = abs(avg_entry - sl)
    tp = avg_entry + (risk_dist * 2) if trend == "BULLISH" else avg_entry - (risk_dist * 2)
    
    filled = False
    for _, row in slice_ahead.iterrows():
        high, low = row["high"], row["low"]
        
        if trend == "BULLISH":
            if not filled and low <= l1: filled = True
            if filled:
                if low <= sl: return -1.0 # Hit SL -> -1R
                if high >= tp: return 2.0 # Hit TP -> +2R
        else:
            if not filled and high >= l1: filled = True
            if filled:
                if high >= sl: return -1.0
                if low <= tp: return 2.0
    return 0.0 # Timeout / No fill

def run_3_month_test():
    print("="*60)
    print(" 🚀 3 AYLIK GERÇEK AI + ORP BİLEŞİK BÜYÜME TESTİ 🚀")
    print("="*60)
    
    model_path = "optimal_xgb_model.json"
    if not os.path.exists(model_path):
        print(f"HATA: {model_path} bulunamadı!")
        return
        
    xgb_model = xgb.XGBClassifier()
    xgb_model.load_model(model_path)
    
    # 3 Months = 90 days = 540 bars (4H). Need 300 for warmup = 840.
    test_bars = 540
    
    all_trades = []
    
    for coin in COINS:
        csv_path = f"../../tirad_backtest/data/historical/{coin}_USDT_4h.csv"
        if not os.path.exists(csv_path): continue
            
        df = pd.read_csv(csv_path)
        df["ts"] = pd.to_datetime(df["ts"])
        df.sort_values("ts", inplace=True)
        df.reset_index(drop=True, inplace=True)
        
        df = df.tail(840).reset_index(drop=True)
        if len(df) < 500: continue
            
        df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
        macd = ta.trend.MACD(df["close"], window_slow=26, window_fast=12, window_sign=9)
        df["macd_hist"] = macd.macd_diff()
        df["vol_sma"] = ta.trend.SMAIndicator(df["volume"], window=20).sma_indicator()
            
        for i in range(len(df) - test_bars, len(df) - 60):
            df_slice = df.iloc[i-300:i].copy()
            current_time = df.iloc[i-1]['ts']
            close_px = float(df_slice["close"].iloc[-1])
            
            comp, trend, entry_, sl_, atr_, vol_ok_ = score_slice_v2(df_slice)
            if comp < 4.5 or trend == "NEUTRAL" or entry_ is None: continue
            if _trend_1d(df_slice) != trend: continue
            if not vol_ok_: continue
                
            sl_dist = abs(entry_ - sl_) / entry_
            if not (0.005 < sl_dist <= 0.10): continue
                
            ob_high, ob_mid, ob_low = get_entry_levels(df_slice, trend, atr_)
            vol_sma = float(df["vol_sma"].iloc[i-1])
            features = pd.DataFrame({
                "comp_score": [comp],
                "is_bullish": [1 if trend == "BULLISH" else 0],
                "atr_pct": [(atr_ / close_px) * 100],
                "rsi": [float(df["rsi"].iloc[i-1])],
                "macd_hist_norm": [(float(df["macd_hist"].iloc[i-1]) / close_px) * 1000],
                "vol_ratio": [float(df["volume"].iloc[i-1]) / vol_sma if vol_sma > 0 else 1.0]
            })
            
            ml_prob = xgb_model.predict_proba(features)[0][1]
            if ml_prob >= 0.60:
                result_r = get_trade_result(df, i, trend, ob_high, ob_mid, sl_)
                if result_r != 0.0:
                    all_trades.append({
                        "coin": coin,
                        "date": current_time,
                        "r_mult": result_r,
                        "sl_pct": sl_dist * 100,
                        "prob": ml_prob
                    })
    
    # Sıralama: İşlemleri tarihsel sıraya koy (ORP için kronoloji şart)
    all_trades = sorted(all_trades, key=lambda x: x["date"])
    
    print(f"\n✅ Toplam Bulunan ve Sonuçlanan Yapay Zeka Onaylı İşlem: {len(all_trades)}")
    wins = sum(1 for t in all_trades if t["r_mult"] > 0)
    print(f"✅ Başarılı İşlem: {wins} | ❌ Başarısız İşlem: {len(all_trades)-wins}")
    win_rate = (wins / len(all_trades)) * 100 if all_trades else 0
    print(f"📊 NET WIN RATE: %{win_rate:.1f}\n")
    
    # ORP Simülasyonu
    params = {
        "cycle_target_pct": 0.10,
        "recovery_factor": 1.0,
        "max_risk_cap": 0.20,
        "base_risk_pct": 0.04,
        "max_leverage": 10.0,
        "dynamic_recovery": False,
        "dd_scaling": False,
        "start_capital": 100.0
    }
    
    res = run_orp_dynamic(all_trades, params)
    
    print("="*60)
    print(" 💵 3 AYLIK $100 KASA BÜYÜME SONUCU (ORP) 💵")
    print("="*60)
    print(f"Başlangıç Kasası : $100.00")
    print(f"3 Ay Sonraki Kasa: ${res['final_eq']:,.2f}  (~{res['final_eq']*33:,.0f} TL)")
    print(f"Büyüme Çarpanı   : {res['total_growth']:.2f}x")
    print(f"Maksimum Drawdown: %{res['max_drawdown']:.1f}")
    print(f"Tamamlanan Döngü : {res['steps_achieved']}")
    print("="*60)

if __name__ == "__main__":
    run_3_month_test()
