#!/usr/bin/env python3
import sys, os
import pandas as pd
import numpy as np
import ccxt
import time
from datetime import datetime, timedelta

# Önceki yazdığımız core motoru kullanmak için path ekliyoruz
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "uyg", "src"))
from backtest_multi_tf import score_slice_v2, _trend_1d
from realistic_limit_backtester import get_entry_levels

COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]
TIMEFRAME = "4h"

def get_binance_data(symbol, limit=400):
    """CCXT kullanarak halka açık (API keysiz) canlı Binance verisi çeker"""
    exchange = ccxt.binance()
    try:
        ohlcv = exchange.fetch_ohlcv(f"{symbol}/USDT", TIMEFRAME, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
        df['ts'] = pd.to_datetime(df['ts'], unit='ms')
        return df
    except Exception as e:
        print(f"Veri çekme hatası ({symbol}): {e}")
        return None

def mock_xgboost_predict(comp_score, atr_pct, trend):
    """
    Eğittiğimiz XGBoost modelinin simülasyonu.
    Gerçek botta xgb_model.json yüklenecek. 
    Kazanma ihtimalini döner (0.0 ile 1.0 arası).
    """
    # Basit bir mock: Skor yüksekse ve trend bullish ise ihtimal artar
    base_prob = 0.50
    if comp_score >= 6.0: base_prob += 0.10
    if comp_score >= 8.0: base_prob += 0.05
    if trend == "BULLISH": base_prob += 0.05
    return min(0.95, base_prob)

def run_7_day_test():
    print("="*70)
    print(" 🚀 CANLI BOT (LIVE SCANNER) - SON 7 GÜN SİMÜLASYONU")
    print("="*70)
    
    # 7 gün = 42 adet 4 Saatlik mum
    test_bars = 42
    
    total_signals = 0
    passed_ml = 0
    
    for coin in COINS:
        print(f"\n[Analiz Ediliyor]: {coin}/USDT")
        df = get_binance_data(coin, limit=400 + test_bars)
        if df is None or len(df) < 300:
            continue
            
        # Son 7 günün her bir 4H mum kapanışında bot ne karar verirdi?
        for i in range(len(df) - test_bars, len(df)):
            df_slice = df.iloc[i-300:i].copy()
            current_time = df.iloc[i-1]['ts']
            close_px = float(df_slice["close"].iloc[-1])
            
            comp, trend, entry_, sl_, atr_, vol_ok_ = score_slice_v2(df_slice)
            
            if comp < 4.5 or trend == "NEUTRAL" or entry_ is None:
                continue
            if _trend_1d(df_slice) != trend:
                continue
            if not vol_ok_:
                continue
                
            sl_dist = abs(entry_ - sl_) / entry_
            if not (0.005 < sl_dist <= 0.10):
                continue
                
            total_signals += 1
            ob_high, ob_mid, ob_low = get_entry_levels(df_slice, trend, atr_)
            
            # 1. Aşama: SMC Sinyali Bulundu!
            print(f"  [{current_time}] ⚠️ SİNYAL: {trend} | Skor: {comp:.1f} | Fiyat: ${close_px:,.2f}")
            
            # 2. Aşama: XGBoost (Yapay Zeka) Filtresi
            atr_pct = (atr_ / close_px) * 100
            ml_prob = mock_xgboost_predict(comp, atr_pct, trend)
            
            if ml_prob >= 0.60:
                passed_ml += 1
                print(f"      ✅ AI ONAYI ALINDI! (Kazanma İhtimali: %{ml_prob*100:.1f})")
                print(f"      👉 AKSİYON: {coin} için Scale-In Limit Emirler Borsaya İletiliyor...")
                print(f"         - %50 Limit Emir: ${ob_high:,.2f} (OB Üst)")
                print(f"         - %50 Limit Emir: ${ob_mid:,.2f} (OB Orta)")
                print(f"         - Stop-Loss: ${sl_:,.2f}")
            else:
                print(f"      ❌ AI REDDETTİ! (İhtimal: %{ml_prob*100:.1f} < %60) -> Emir Atılmadı.")

    print("\n" + "="*70)
    print(f"📊 7 GÜNLÜK ÖZET RAPOR:")
    print(f"Toplam Bulunan Klasik Sinyal : {total_signals}")
    print(f"Yapay Zekadan Geçip İşleme Giren: {passed_ml}")
    if total_signals == 0:
        print("Son 7 günde kriterlere uyan hiçbir Setup oluşmamış (Piyasa yatay veya çok gürültülü).")
    print("="*70)

if __name__ == "__main__":
    run_7_day_test()
