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

def get_binance_history(exchange, symbol, timeframe, limit=1500):
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
    print(" 🚀 BINANCE API İLE %100 GERÇEK YZ TESTİ (BTC-ONLY FAST) 🚀")
    print("="*70)
    exchange = ccxt.binance({'enableRateLimit': True})
    model_path = "optimal_xgb_model.json"
    xgb_model = xgb.XGBClassifier()
    xgb_model.load_model(model_path)
    
    test_bars = 1080 # 6 months
    raw_signals = []
    
    coin = "BTC"
    symbol = f"{coin}/USDT"
    print(f"🔄 Binance API'den çekiliyor: {symbol}...", flush=True)
    df = get_binance_history(exchange, symbol, "4h", limit=1500)
    
    df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
    macd = ta.trend.MACD(df["close"], window_slow=26, window_fast=12, window_sign=9)
    df["macd_hist"] = macd.macd_diff()
    df["vol_sma"] = ta.trend.SMAIndicator(df["volume"], window=20).sma_indicator()
        
    for i in range(len(df) - test_bars, len(df) - 60):
        df_slice = df.iloc[i-300:i].copy()
        comp, trend, entry_, sl_, atr_, vol_ok_ = score_slice_v2(df_slice)
        if comp < 4.5 or trend == "NEUTRAL" or entry_ is None: continue
        if _trend_1d(df_slice) != trend: continue
        if not vol_ok_: continue
        sl_dist = abs(entry_ - sl_) / entry_
        if not (0.005 < sl_dist <= 0.10): continue
        
        close_px = float(df_slice["close"].iloc[-1])
        ob_high, ob_mid, ob_low = get_entry_levels(df_slice, trend, atr_)
        vol_sma = float(df["vol_sma"].iloc[i-1])
        
        raw_signals.append({
            "coin": coin, "date": df.iloc[i-1]['ts'], "df_idx": i, "df_ref": df,
            "trend": trend, "l1": ob_high, "l2": ob_mid, "sl": sl_, "sl_pct": sl_dist * 100,
            "comp_score": comp, "is_bullish": 1 if trend == "BULLISH" else 0,
            "atr_pct": (atr_ / close_px) * 100, "rsi": float(df["rsi"].iloc[i-1]),
            "macd_hist_norm": (float(df["macd_hist"].iloc[i-1]) / close_px) * 1000,
            "vol_ratio": float(df["volume"].iloc[i-1]) / vol_sma if vol_sma > 0 else 1.0
        })

    features_df = pd.DataFrame(raw_signals)[["comp_score", "is_bullish", "atr_pct", "rsi", "macd_hist_norm", "vol_ratio"]]
    probs = xgb_model.predict_proba(features_df)[:, 1]
    
    all_trades = []
    rejected = 0
    for sig, prob in zip(raw_signals, probs):
        if prob >= 0.65: # EŞİK 0.65'E ÇIKARILDI
            result_r = get_trade_result(sig["df_ref"], sig["df_idx"], sig["trend"], sig["l1"], sig["l2"], sig["sl"])
            if result_r != 0.0:
                all_trades.append({"coin": sig["coin"], "date": sig["date"], "r_mult": result_r, "sl_pct": sig["sl_pct"], "prob": prob})
        else: rejected += 1
                
    all_trades = sorted(all_trades, key=lambda x: x["date"])
    print("\n✅ BINANCE TARAMASI TAMAMLANDI!")
    print(f"Yapay Zekanın Çöpe Attığı Sinyal: {rejected}")
    print(f"Gerçekleşen İşlem: {len(all_trades)}")
    
    wins = sum(1 for t in all_trades if t["r_mult"] > 0)
    win_rate = (wins / len(all_trades)) * 100 if all_trades else 0
    print(f"Başarılı İşlem: {wins} | Başarısız: {len(all_trades)-wins}")
    print(f"📊 GERÇEK PİYASA WIN RATE: %{win_rate:.1f}\n")

if __name__ == "__main__":
    run_real_binance_test()
