#!/usr/bin/env python3
import sys, os
import pandas as pd
import numpy as np
import ccxt
import xgboost as xgb
import warnings
import ta

warnings.filterwarnings("ignore")

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "uyg", "src"))
from backtest_multi_tf import score_slice_v2, _trend_1d
from realistic_limit_backtester import get_entry_levels

COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]
TIMEFRAME = "4h"

def get_binance_data(symbol, limit=500):
    exchange = ccxt.binance()
    try:
        ohlcv = exchange.fetch_ohlcv(f"{symbol}/USDT", TIMEFRAME, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
        df['ts'] = pd.to_datetime(df['ts'], unit='ms')
        return df
    except Exception as e:
        print(f"Veri çekme hatası ({symbol}): {e}")
        return None

def run_30_day_test():
    print("="*70)
    print(" 🚀 CANLI BOT (LIVE SCANNER) - GERÇEK YAPAY ZEKA 30 GÜN TESTİ")
    print("="*70)
    
    # Gerçek Modeli Yükle
    model_path = "optimal_xgb_model.json"
    if not os.path.exists(model_path):
        print(f"HATA: {model_path} bulunamadı!")
        return
        
    xgb_model = xgb.XGBClassifier()
    xgb_model.load_model(model_path)
    
    # 30 gün = 180 adet 4 Saatlik mum
    test_bars = 180
    
    total_signals = 0
    passed_ml = 0
    
    for coin in COINS:
        print(f"\n[Analiz Ediliyor]: {coin}/USDT")
        # Bizim ısınma için 300 muma, test için 180 muma ihtiyacımız var (Toplam 480)
        df = get_binance_data(coin, limit=500)
        if df is None or len(df) < 480:
            continue
            
        # Vektörel İndikatörleri ekleyelim (Feature Extract)
        df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
        macd = ta.trend.MACD(df["close"], window_slow=26, window_fast=12, window_sign=9)
        df["macd_hist"] = macd.macd_diff()
        df["vol_sma"] = ta.trend.SMAIndicator(df["volume"], window=20).sma_indicator()
            
        for i in range(len(df) - test_bars, len(df)):
            df_slice = df.iloc[i-300:i].copy()
            current_time = df.iloc[i-1]['ts']
            close_px = float(df_slice["close"].iloc[-1])
            
            comp, trend, entry_, sl_, atr_, vol_ok_ = score_slice_v2(df_slice)
            
            if comp < 4.5 or trend == "NEUTRAL" or entry_ is None: continue
            if _trend_1d(df_slice) != trend: continue
            if not vol_ok_: continue
                
            sl_dist = abs(entry_ - sl_) / entry_
            if not (0.005 < sl_dist <= 0.10): continue
                
            total_signals += 1
            ob_high, ob_mid, ob_low = get_entry_levels(df_slice, trend, atr_)
            
            # Sinyal Bulundu
            print(f"  [{current_time}] ⚠️ Klasik Sinyal: {trend} | Skor: {comp:.1f} | Fiyat: ${close_px:,.2f}")
            
            # Gerçek XGBoost Feature Setini Oluştur
            vol_sma = float(df["vol_sma"].iloc[i-1])
            features_dict = {
                "comp_score": [comp],
                "is_bullish": [1 if trend == "BULLISH" else 0],
                "atr_pct": [(atr_ / close_px) * 100],
                "rsi": [float(df["rsi"].iloc[i-1])],
                "macd_hist_norm": [(float(df["macd_hist"].iloc[i-1]) / close_px) * 1000],
                "vol_ratio": [float(df["volume"].iloc[i-1]) / vol_sma if vol_sma > 0 else 1.0]
            }
            
            X_live = pd.DataFrame(features_dict)
            
            # Gerçek Yapay Zeka Tahmini
            ml_prob = xgb_model.predict_proba(X_live)[0][1]
            
            if ml_prob >= 0.60:
                passed_ml += 1
                print(f"      ✅ YZ ONAYI: İşlem Keskin! (Kazanma İhtimali: %{ml_prob*100:.1f})")
                print(f"         > Emir 1: ${ob_high:,.2f} | Emir 2: ${ob_mid:,.2f} | SL: ${sl_:,.2f}")
            else:
                print(f"      ❌ YZ REDDİ: Tehlikeli İşlem! (İhtimal: %{ml_prob*100:.1f} < %60) -> İptal.")

    print("\n" + "="*70)
    print(f"📊 GERÇEK YAPAY ZEKALI 30 GÜNLÜK ÖZET RAPOR:")
    print(f"Toplam Bulunan Klasik Sinyal : {total_signals}")
    print(f"Yapay Zekadan Geçip İşleme Giren: {passed_ml} (%{passed_ml/total_signals*100 if total_signals>0 else 0:.1f})")
    print("="*70)

if __name__ == "__main__":
    run_30_day_test()
