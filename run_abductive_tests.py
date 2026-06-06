import sys, os
import pandas as pd
import numpy as np
import warnings
import json
import ta

warnings.filterwarnings("ignore")

COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]
TIMEFRAME = "4h"
FRICTION_RATE = 0.0006

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

def apply_multi_regime_filters(df):
    # 1. Base Indicators
    df['ema_50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
    df['ema_20'] = ta.trend.EMAIndicator(df['close'], window=20).ema_indicator()
    
    # 2. CVD Proxy
    df['candle_shape'] = (df['close'] - df['open']) / (df['high'] - df['low'] + 1e-8)
    df['vol_delta'] = df['candle_shape'] * df['volume']
    df['cvd'] = df['vol_delta'].cumsum()
    df['cvd_10'] = df['vol_delta'].rolling(window=10).sum()
    df['cvd_bullish'] = df['cvd_10'] > 0
    df['cvd_bearish'] = df['cvd_10'] < 0
    
    # 3. TTM Squeeze
    length = 20
    mult_bb = 2.0
    mult_kc = 1.5
    df['basis'] = df['close'].rolling(length).mean()
    df['dev'] = df['close'].rolling(length).std() * mult_bb
    df['bb_upper'] = df['basis'] + df['dev']
    df['bb_lower'] = df['basis'] - df['dev']
    df['kc_upper'] = df['basis'] + df['atr'] * mult_kc
    df['kc_lower'] = df['basis'] - df['atr'] * mult_kc
    df['squeeze_on'] = (df['bb_lower'] > df['kc_lower']) & (df['bb_upper'] < df['kc_upper'])
    df['squeeze_release'] = (~df['squeeze_on']) & df['squeeze_on'].shift(1).rolling(3).max().astype(bool)
    
    # 4. ADX Regime (Pullbacks)
    adx_ind = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
    df['ADX'] = adx_ind.adx()
    df['DI_plus'] = adx_ind.adx_pos()
    df['DI_minus'] = adx_ind.adx_neg()
        
    df['is_strong_uptrend'] = (df['ADX'] >= 25) & (df['DI_plus'] > df['DI_minus']) & (df['close'] > df['ema_50'])
    df['is_strong_downtrend'] = (df['ADX'] >= 25) & (df['DI_minus'] > df['DI_plus']) & (df['close'] < df['ema_50'])
    
    # RSI for pullbacks
    df['rsi_14'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
    
    # Pullback Logic
    df['bull_pullback'] = df['is_strong_uptrend'] & (df['low'] <= df['ema_20']) & (df['close'] > df['ema_20']) & (df['rsi_14'] < 50) & df['cvd_bullish']
    df['bear_pullback'] = df['is_strong_downtrend'] & (df['high'] >= df['ema_20']) & (df['close'] < df['ema_20']) & (df['rsi_14'] > 50) & df['cvd_bearish']
    
    # 5. V-Bottom Sweep (Capitulation)
    bbands_wide = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2.5)
    df['BBL_wide'] = bbands_wide.bollinger_lband()
    df['BBU_wide'] = bbands_wide.bollinger_hband()
        
    df['vol_ma'] = df['volume'].rolling(window=20).mean()
    df['vol_spike'] = df['volume'] > (df['vol_ma'] * 2.0)
    df['candle_range'] = df['high'] - df['low']
    
    # Long Sweep: Dropped below BBL, closed in upper half, huge volume
    df['v_bottom_sweep'] = (df['low'] < df['BBL_wide']) & ((df['close'] - df['low']) > (df['candle_range'] * 0.5)) & df['vol_spike']
    # Short Sweep: Shot above BBU, closed in lower half, huge volume
    df['v_top_sweep'] = (df['high'] > df['BBU_wide']) & ((df['high'] - df['close']) > (df['candle_range'] * 0.5)) & df['vol_spike']
    
    # 6. Momentum Ignition
    df['recent_high'] = df['high'].rolling(10).max().shift(1)
    df['recent_low'] = df['low'].rolling(10).min().shift(1)
    df['ignition_long'] = (df['candle_range'] >= df['atr'] * 1.5) & (df['close'] > df['recent_high']) & ((df['high'] - df['close']) < (df['candle_range'] * 0.2)) & df['cvd_bullish']
    df['ignition_short'] = (df['candle_range'] >= df['atr'] * 1.5) & (df['close'] < df['recent_low']) & ((df['close'] - df['low']) < (df['candle_range'] * 0.2)) & df['cvd_bearish']

    return df

def get_trade_result(df, start_idx, trend, entry, atr):
    tp_mult, sl_mult = 4.0, 2.0 
    end_idx = min(start_idx + 100, len(df))
    slice_ahead = df.iloc[start_idx:end_idx]
    initial_sl = entry - (atr * sl_mult) if trend == 1 else entry + (atr * sl_mult)
    tp = entry + (atr * tp_mult) if trend == 1 else entry - (atr * tp_mult)
    risk_dist = abs(entry - initial_sl)
    rr = tp_mult / sl_mult
    
    current_sl, filled = initial_sl, False
    for _, row in slice_ahead.iterrows():
        high, low = row["high"], row["low"]
        if trend == 1:
            if not filled and low <= entry: filled = True
            if filled:
                if high >= tp: return rr, risk_dist/entry
                if low <= current_sl: return -1.0, risk_dist/entry
        else:
            if not filled and high >= entry: filled = True
            if filled:
                if low <= tp: return rr, risk_dist/entry
                if high >= current_sl: return -1.0, risk_dist/entry
    return 0.0, 0.0

def run_simulation(all_dfs, strategy_name, regime_flags):
    all_trades = []
    for coin, df in all_dfs.items():
        for i in range(250, len(df) - 100):
            trend = df["st_trend"].iloc[i-1]
            prev_trend = df["st_trend"].iloc[i-2]
            close = df["close"].iloc[i-1]
            low_p, high_p = df["low"].iloc[i-1], df["high"].iloc[i-1]
            st, atr = df["st"].iloc[i-1], df["atr"].iloc[i-1]
            
            # Base logic: Supertrend
            base_long = False
            base_short = False
            if trend == 1 and (prev_trend == -1 or low_p <= st + (atr * 0.5)): base_long = True
            if trend == -1 and (prev_trend == 1 or high_p >= st - (atr * 0.5)): base_short = True
            
            if not base_long and not base_short: continue
            
            # REGIME FILTERS
            is_valid = False
            row = df.iloc[i-1]
            
            # 1. Strict Squeeze
            if regime_flags.get("squeeze", False):
                if row['squeeze_release']:
                    if base_long and row['cvd_bullish']: is_valid = True
                    if base_short and row['cvd_bearish']: is_valid = True
                    
            # 2. Trend Pullback
            if regime_flags.get("pullback", False):
                if base_long and row['bull_pullback']: is_valid = True
                if base_short and row['bear_pullback']: is_valid = True
                
            # 3. V-Bottom/Top Sweep
            if regime_flags.get("sweep", False):
                if base_long and row['v_bottom_sweep']: is_valid = True
                if base_short and row['v_top_sweep']: is_valid = True
                
            # 4. Momentum Ignition
            if regime_flags.get("ignition", False):
                if base_long and row['ignition_long']: is_valid = True
                if base_short and row['ignition_short']: is_valid = True

            if not is_valid: continue
            
            res_r, sl_pct = get_trade_result(df, i, trend, close, atr)
            if res_r != 0.0 or (res_r == 0.0 and sl_pct > 0.0):
                all_trades.append({"date": df.iloc[i]['ts'], "r_mult": res_r, "sl_pct": sl_pct})
                
    trades = sorted(all_trades, key=lambda x: x["date"])
    
    # Binance simulation
    equity = 1000.0
    gross_leverage = 0.75
    wins, losses = 0, 0
    for t in trades:
        sl_f = max(t["sl_pct"], 0.01)
        act_lev = min(gross_leverage, 10.0) 
        act_risk = min(act_lev * equity * sl_f, equity * 0.05)
        friction = (act_lev * equity) * FRICTION_RATE
        pnl = (act_risk * t["r_mult"]) - friction
        equity += pnl
        if pnl > 0: wins += 1
        else: losses += 1
        if equity <= 0: break
        
    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
    
    print(f"\n--- Strategy: {strategy_name} ---")
    print(f"Total Trades: {len(trades)}")
    print(f"Wins: {wins} | Losses: {losses} | Win Rate: {win_rate:.1f}%")
    print(f"Final Equity: ${equity:.2f}")

def main():
    print("Loading datasets for Multi-Regime Research...")
    all_dfs = {}
    for coin in COINS:
        csv_path = f"/Users/uygar/.gemini/antigravity/scratch/tirad/uyg/src/data/{coin}_USDT_4h_2yr.csv"
        df = pd.read_csv(csv_path)
        df["ts"] = pd.to_datetime(df["ts"])
        one_year_ago = df["ts"].max() - pd.DateOffset(months=12)
        df = df[df["ts"] >= one_year_ago].reset_index(drop=True)
        
        df = calculate_supertrend(df, 14, 3.5)
        df = apply_multi_regime_filters(df)
        all_dfs[coin] = df
        
    print("\n[A] Old Strict Model (Squeeze Only)")
    run_simulation(all_dfs, "Squeeze + CVD Only", {"squeeze": True})
    
    print("\n[B] Multi-Regime (Squeeze OR Pullback OR Sweep OR Ignition)")
    run_simulation(all_dfs, "Ultimate Multi-Regime System", {"squeeze": True, "pullback": True, "sweep": True, "ignition": True})

if __name__ == "__main__":
    main()
