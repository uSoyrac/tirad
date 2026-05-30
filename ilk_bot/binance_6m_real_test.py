import sys, os, time
import pandas as pd
import numpy as np
import xgboost as xgb
import ccxt
import warnings
import ta

warnings.filterwarnings("ignore")

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "uyg", "src"))
from backtest_multi_tf import score_slice_v2, _trend_1d
from realistic_limit_backtester import get_entry_levels
from dynamic_optimizer import run_orp_dynamic

COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]
TIMEFRAME = "4h"

def get_binance_history(exchange, symbol, timeframe, limit=1500):
    try:
        # ccxt'nin public apisini kullanarak ana veriyi çekiyoruz
        recent_ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=1000)
        if not recent_ohlcv: return None
        
        earliest_ts = recent_ohlcv[0][0]
        start_ts = earliest_ts - (500 * 14400000)
        older_ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=start_ts, limit=500)
        
        full_ohlcv = older_ohlcv + recent_ohlcv
        
        df = pd.DataFrame(full_ohlcv, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
        df.drop_duplicates(subset=['ts'], inplace=True)
        df.sort_values('ts', inplace=True)
        df['ts'] = pd.to_datetime(df['ts'], unit='ms')
        return df.tail(1500).reset_index(drop=True)
    except Exception as e:
        print(f"Veri çekme hatası ({symbol}): {e}")
        return None

def get_trade_result(df, start_idx, trend, l1, l2, sl):
    end_idx = min(start_idx + 60, len(df))
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
                if low <= sl: return -1.0
                if high >= tp: return 2.0
        else:
            if not filled and high >= l1: filled = True
            if filled:
                if high >= sl: return -1.0
                if low <= tp: return 2.0
    return 0.0

def run_real_binance_test():
    print("="*70)
    print(" 🚀 BINANCE API İLE %100 GERÇEK 6 AYLIK YZ TESTİ BAŞLIYOR 🚀")
    print("="*70)
    
    # API anahtarları hatalı olduğu için (Invalid API Key) veriyi Public (Anonim) çekiyoruz.
    # İşlem geçmişini çekmek için API key gerekmez.
    exchange = ccxt.binance({
        'enableRateLimit': True,
    })
    
    model_path = "optimal_xgb_model.json"
    if not os.path.exists(model_path): return
        
    xgb_model = xgb.XGBClassifier()
    xgb_model.load_model(model_path)
    
    test_bars = 1080
    raw_signals = []
    
    for coin in COINS:
        symbol = f"{coin}/USDT"
        print(f"🔄 Binance API'den anlık olarak çekiliyor: {symbol}...", flush=True)
        df = get_binance_history(exchange, symbol, TIMEFRAME, limit=1500)
        
        if df is None or len(df) < 1300:
            print(f"Yetersiz veri: {symbol}")
            continue
            
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
            
            raw_signals.append({
                "coin": coin,
                "date": current_time,
                "df_idx": i,
                "df_ref": df,
                "trend": trend,
                "l1": ob_high,
                "l2": ob_mid,
                "sl": sl_,
                "sl_pct": sl_dist * 100,
                "comp_score": comp,
                "is_bullish": 1 if trend == "BULLISH" else 0,
                "atr_pct": (atr_ / close_px) * 100,
                "rsi": float(df["rsi"].iloc[i-1]),
                "macd_hist_norm": (float(df["macd_hist"].iloc[i-1]) / close_px) * 1000,
                "vol_ratio": float(df["volume"].iloc[i-1]) / vol_sma if vol_sma > 0 else 1.0
            })

    if not raw_signals: return
        
    print(f"\n📊 Toplam {len(raw_signals)} standart sinyal bulundu. YZ'den geçiriliyor...")
    
    features_df = pd.DataFrame(raw_signals)[["comp_score", "is_bullish", "atr_pct", "rsi", "macd_hist_norm", "vol_ratio"]]
    probs = xgb_model.predict_proba(features_df)[:, 1]
    
    all_trades = []
    rejected = 0
    for sig, prob in zip(raw_signals, probs):
        if prob >= 0.60:
            result_r = get_trade_result(sig["df_ref"], sig["df_idx"], sig["trend"], sig["l1"], sig["l2"], sig["sl"])
            if result_r != 0.0:
                all_trades.append({
                    "coin": sig["coin"],
                    "date": sig["date"],
                    "r_mult": result_r,
                    "sl_pct": sig["sl_pct"],
                    "prob": prob
                })
        else:
            rejected += 1
                
    all_trades = sorted(all_trades, key=lambda x: x["date"])
    
    print("\n✅ BINANCE TARAMASI TAMAMLANDI!")
    print(f"Yapay Zekanın Çöpe Attığı (Engellediği) İşlem Sayısı: {rejected}")
    print(f"Yapay Zeka Onaylı ve Borsada Gerçekleşen İşlem: {len(all_trades)}")
    
    wins = sum(1 for t in all_trades if t["r_mult"] > 0)
    win_rate = (wins / len(all_trades)) * 100 if all_trades else 0
    print(f"Başarılı İşlem: {wins} | Başarısız İşlem (Stop): {len(all_trades)-wins}")
    print(f"📊 GERÇEK PİYASA WIN RATE: %{win_rate:.1f}\n")
    
    if not all_trades: return
    
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
    
    print("="*70)
    print(" 💵 6 AYLIK BINANCE GERÇEK PİYASA $100 KASA BÜYÜME SONUCU (ORP) 💵")
    print("="*70)
    print(f"Başlangıç Kasası : $100.00")
    print(f"6 Ay Sonraki Kasa: ${res['final_eq']:,.2f}  (~{res['final_eq']*33:,.0f} TL)")
    print(f"Net Büyüme Oranı : %{((res['final_eq']/100)-1)*100:.1f}")
    print(f"Büyüme Çarpanı   : {res['total_growth']:.2f}x")
    print(f"Maksimum Drawdown: %{res['max_drawdown']:.1f}")
    print(f"Tamamlanan Döngü : {res['steps_achieved']}")
    print("="*70)

if __name__ == "__main__":
    run_real_binance_test()
