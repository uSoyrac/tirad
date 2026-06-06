import sys, os
import pandas as pd
import numpy as np
import warnings
import ta

warnings.filterwarnings("ignore")

COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]
TIMEFRAME = "4h"

def calculate_supertrend(df, period=14, multiplier=3.5):
    high, low, close = df['high'], df['low'], df['close']
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.DataFrame({'tr1': tr1, 'tr2': tr2, 'tr3': tr3}).max(axis=1)
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    hl2 = (high + low) / 2
    basic_ub = hl2 + (multiplier * atr)
    basic_lb = hl2 - (multiplier * atr)
    ub = basic_ub.copy().values
    lb = basic_lb.copy().values
    c = close.values
    st = np.zeros(len(df))
    t = np.ones(len(df))
    for i in range(1, len(df)):
        if ub[i] > ub[i-1] and c[i-1] <= ub[i-1]: ub[i] = ub[i-1]
        if lb[i] < lb[i-1] and c[i-1] >= lb[i-1]: lb[i] = lb[i-1]
        if c[i] > ub[i-1]: t[i] = 1
        elif c[i] < lb[i-1]: t[i] = -1
        else: t[i] = t[i-1]
        if t[i] == 1: st[i] = lb[i]
        else: st[i] = ub[i]
    df['atr'] = atr
    df['st'] = st
    df['st_trend'] = t
    return df

def get_trade_result(df, start_idx, trend, entry, atr):
    tp_mult, sl_mult = 4.0, 2.5
    end_idx = min(start_idx + 100, len(df))
    slice_ahead = df.iloc[start_idx:end_idx]
    initial_sl = entry - (atr * sl_mult) if trend == 1 else entry + (atr * sl_mult)
    tp = entry + (atr * tp_mult) if trend == 1 else entry - (atr * tp_mult)
    risk_dist = abs(entry - initial_sl)
    rr = tp_mult / sl_mult
    be_dist = risk_dist * 1.25
    be_trigger = entry + be_dist if trend == 1 else entry - be_dist
    current_sl, is_breakeven, filled = initial_sl, False, False
    for _, row in slice_ahead.iterrows():
        high, low = row["high"], row["low"]
        if trend == 1:
            if not filled and low <= entry: filled = True
            if filled:
                if high >= tp: return rr, risk_dist/entry*100
                if high >= be_trigger and not is_breakeven: current_sl, is_breakeven = entry, True
                if low <= current_sl: return (0.0 if is_breakeven else -1.0), risk_dist/entry*100
        else:
            if not filled and high >= entry: filled = True
            if filled:
                if low <= tp: return rr, risk_dist/entry*100
                if low <= be_trigger and not is_breakeven: current_sl, is_breakeven = entry, True
                if high >= current_sl: return (0.0 if is_breakeven else -1.0), risk_dist/entry*100
    return 0.0, 0.0

def build_dataset():
    print("="*80)
    print(" 🛠️ V20 DATASET BUILDER (XGBOOST FEATURE EXTRACTION)")
    print("="*80)
    
    dataset = []
    
    for coin in COINS:
        csv_path = f"/Users/uygar/.gemini/antigravity/scratch/tirad/uyg/src/data/{coin}_USDT_{TIMEFRAME}_2yr.csv"
        if not os.path.exists(csv_path):
            print(f"❌ DATA NOT FOUND: {csv_path}")
            continue
            
        df = pd.read_csv(csv_path)
        df["ts"] = pd.to_datetime(df["ts"])
        print(f"📊 İşleniyor: {coin} ({len(df)} mum)")
        
        # Temel Sinyal İndikatörleri
        df = calculate_supertrend(df, 14, 3.5)
        df["ema_250"] = ta.trend.EMAIndicator(df["close"], window=250).ema_indicator()
        
        # Makine Öğrenmesi İçin Extra Features
        df['adx'] = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14).adx()
        df['vol_sma'] = df['volume'].rolling(20).mean()
        df['vol_ratio'] = df['volume'] / df['vol_sma']
        df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
        macd = ta.trend.MACD(df['close'], window_slow=26, window_fast=12, window_sign=9)
        df['macd_hist'] = macd.macd_diff()
        df['atr_pct'] = (df['atr'] / df['close']) * 100
        df['dist_ema250_pct'] = ((df['close'] - df['ema_250']) / df['ema_250']) * 100
        
        for i in range(250, len(df) - 100):
            trend = df["st_trend"].iloc[i-1]
            prev_trend = df["st_trend"].iloc[i-2]
            close = df["close"].iloc[i-1]
            low_p, high_p = df["low"].iloc[i-1], df["high"].iloc[i-1]
            st, atr = df["st"].iloc[i-1], df["atr"].iloc[i-1]
            ema250 = df["ema_250"].iloc[i-1]
            
            # Feature Snapshot
            features = {
                "adx": df["adx"].iloc[i-1],
                "vol_ratio": df["vol_ratio"].iloc[i-1],
                "rsi": df["rsi"].iloc[i-1],
                "macd_hist": df["macd_hist"].iloc[i-1],
                "atr_pct": df["atr_pct"].iloc[i-1],
                "dist_ema250_pct": df["dist_ema250_pct"].iloc[i-1],
                "trend_dir": trend
            }
            
            # Base V18/V19 Filters
            is_signal = False
            if trend == 1:
                if prev_trend == -1 or low_p <= st + (atr * 0.5): is_signal = True
            else:
                if prev_trend == 1 or high_p >= st - (atr * 0.5): is_signal = True
                
            if not is_signal: continue
            if trend == 1 and close < ema250: continue
            if trend == -1 and close > ema250: continue
            
            # Ön Filtre: ADX>40 ve Vol>3.0 çok ekstrem balina tuzakları, onları sete dahi sokmuyoruz.
            # (Çünkü bunları XGBoost zaten kesin reddedecek, veri setini kirletmeye gerek yok)
            if features["adx"] > 40 or features["vol_ratio"] > 3.0: continue
            
            res_r, sl_pct = get_trade_result(df, i, trend, close, atr)
            if res_r == 0.0 and sl_pct == 0.0: continue
            
            # Hedef Etiket: Win(1) veya Loss(0)
            # Breakeven işlemleri 0 kabul ediyoruz ki model tam kazananları bulsun
            is_win = 1 if res_r > 0 else 0
            
            row = features.copy()
            row["is_win"] = is_win
            row["coin"] = coin
            row["date"] = df["ts"].iloc[i]
            
            dataset.append(row)
            
    df_out = pd.DataFrame(dataset)
    out_path = "/Users/uygar/.gemini/antigravity/scratch/tirad/uyg/src/data/ml_dataset_2yr.csv"
    df_out.to_csv(out_path, index=False)
    
    print("\n✅ Veri Seti Oluşturuldu!")
    print(f"Toplam Örnek: {len(df_out)}")
    wins = len(df_out[df_out['is_win'] == 1])
    losses = len(df_out) - wins
    print(f"Kazanma Oranı (Base WR): %{wins/len(df_out)*100:.1f} ({wins} Kazanç / {losses} Kayıp)")
    print(f"Dosya: {out_path}")

if __name__ == "__main__":
    build_dataset()
