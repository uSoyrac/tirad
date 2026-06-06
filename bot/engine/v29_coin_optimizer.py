import pandas as pd
import numpy as np
import xgboost as xgb
import os
import json
import ta
from datetime import timedelta

COMMISSION = 0.0004
SLIPPAGE = 0.0005
RISK_PER_TRADE = 0.02
START_BALANCE = 10000.0

def simulate_trade_with_trailing(df, start_idx, entry_price, sl_price, tp_price, position_size, atr_val):
    """
    Simulates a trade with a Trailing Stop.
    Breakeven hit when price reaches entry_price + 2*ATR.
    Trailing Stop trails by 2*ATR from highest high after breakeven.
    Max holding time: 72 bars (72 hours).
    """
    sl = sl_price
    breakeven_target = entry_price + (2.0 * atr_val)
    is_breakeven_hit = False
    
    for i in range(1, 73):
        if start_idx + i >= len(df):
            break
            
        row = df.iloc[start_idx + i]
        high = row['high']
        low = row['low']
        
        # Check SL hit
        if low <= sl:
            return sl, i, "LOSS (or Trailing Stop)"
            
        # Check TP hit (if fixed TP is used, but we want infinite TP)
        # Actually, let's use TP as an initial target but allow it to trail.
        # So we won't strictly exit at TP. We only exit on SL.
        
        # Check Breakeven / Trailing
        if high >= breakeven_target:
            is_breakeven_hit = True
            
        if is_breakeven_hit:
            # Trailing stop trails by 2.0 ATR from the current high
            potential_sl = high - (2.0 * atr_val)
            if potential_sl > sl:
                sl = potential_sl # Move SL up
                
    # Time Exit
    if start_idx + 72 < len(df):
        return df.iloc[start_idx + 72]['close'], 72, "TIME_EXIT"
    
    return df.iloc[-1]['close'], len(df)-start_idx-1, "FORCE_CLOSE"


def optimize_coins():
    features_dir = 'bot/engine/features_v27'
    files = [f for f in os.listdir(features_dir) if f.endswith('.csv')]
    
    model = xgb.XGBClassifier()
    model.load_model("bot/engine/v27_xgb_model.json")
    with open("bot/engine/v27_xgb_meta.json", "r") as f:
        meta = json.load(f)
    features = meta["features"]
    
    optimal_params = {}
    
    adx_thresholds = [20, 25, 30, 35]
    tp_mults = [2.5, 3.5, 5.0] # Initial tp_mult doesn't matter much for trailing, but used for risk calc
    
    for f in files:
        df = pd.read_csv(os.path.join(features_dir, f), parse_dates=['ts'])
        sym = f.replace('.csv', '')
        
        adx_ind = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
        df['adx_14'] = adx_ind.adx()
        
        # Train Period Only!
        split_date = df['ts'].max() - timedelta(days=90)
        train_df = df[df['ts'] < split_date].copy().reset_index(drop=True)
        
        X = train_df[features]
        probs = model.predict_proba(X)[:, 1]
        
        best_pnl = -999999
        best_param = None
        
        print(f"Optimizing {sym}...")
        for adx_th in adx_thresholds:
            for tp_m in tp_mults:
                balance = START_BALANCE
                for i in range(len(train_df) - 73): # Leave room for holding
                    prob = probs[i]
                    row = train_df.iloc[i]
                    
                    if prob > 0.55 and row['adx_14'] > adx_th:
                        entry = row['close']
                        atr = (row['atr_14_pct'] / 100) * entry
                        sl = entry - (1.5 * atr)
                        tp = entry + (tp_m * atr) # For risk calc
                        
                        risk_usd = balance * RISK_PER_TRADE
                        sl_pct = (entry - sl) / entry
                        pos_size = risk_usd / sl_pct
                        
                        # Simulate trade
                        exit_price, duration, status = simulate_trade_with_trailing(
                            train_df, i, entry, sl, tp, pos_size, atr
                        )
                        
                        pnl_pct = (exit_price - entry) / entry
                        net_pnl_pct = pnl_pct - (COMMISSION * 2) - SLIPPAGE
                        balance += pos_size * net_pnl_pct
                        
                if balance > best_pnl:
                    best_pnl = balance
                    best_param = {"adx_threshold": adx_th, "tp_mult": tp_m}
                    
        print(f"  Best {sym}: ADX > {best_param['adx_threshold']}, TP={best_param['tp_mult']} -> PnL: ${best_pnl - START_BALANCE:.2f}")
        optimal_params[sym] = best_param
        
    with open("bot/engine/v29_coin_params.json", "w") as f:
        json.dump(optimal_params, f, indent=4)

if __name__ == "__main__":
    optimize_coins()
