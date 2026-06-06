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

def run_v29_multi_asset():
    features_dir = 'bot/engine/features_v27'
    files = [f for f in os.listdir(features_dir) if f.endswith('.csv')]
    
    all_data = []
    for f in files:
        df = pd.read_csv(os.path.join(features_dir, f), parse_dates=['ts'])
        df['symbol'] = f.replace('.csv', '')
        adx_ind = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
        df['adx_14'] = adx_ind.adx()
        all_data.append(df)
        
    combined_df = pd.concat(all_data)
    combined_df.sort_values(by='ts', inplace=True)
    combined_df.reset_index(drop=True, inplace=True)
    
    split_date = combined_df['ts'].max() - timedelta(days=90)
    test_df = combined_df[combined_df['ts'] >= split_date].copy()
    
    model = xgb.XGBClassifier()
    model.load_model("bot/engine/v27_xgb_model.json")
    with open("bot/engine/v27_xgb_meta.json", "r") as f:
        meta = json.load(f)
    features = meta["features"]
    
    balance = START_BALANCE
    open_positions = []
    trade_history = []
    
    grouped = test_df.groupby('ts')
    
    for ts, group in grouped:
        # 1. Manage existing positions (Trailing Stop Check)
        still_open = []
        for pos in open_positions:
            sym = pos['symbol']
            sym_data = group[group['symbol'] == sym]
            
            if len(sym_data) == 0:
                still_open.append(pos)
                continue
                
            row = sym_data.iloc[0]
            high = row['high']
            low = row['low']
            
            hit_sl = low <= pos['sl_price']
            
            if hit_sl:
                exit_price = pos['sl_price']
                pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price']
                net_pnl_pct = pnl_pct - (COMMISSION * 2) - SLIPPAGE
                pnl_usd = pos['position_size'] * net_pnl_pct
                
                balance += pnl_usd
                pos['exit_price'] = exit_price
                pos['exit_time'] = ts
                pos['pnl_usd'] = pnl_usd
                pos['net_pnl_pct'] = net_pnl_pct
                pos['status'] = "CLOSED"
                pos['balance_after'] = balance
                trade_history.append(pos)
            else:
                # Update Trailing Stop
                if high >= pos['breakeven_target']:
                    pos['is_breakeven_hit'] = True
                    
                if pos['is_breakeven_hit']:
                    potential_sl = high - (2.0 * pos['atr_val'])
                    if potential_sl > pos['sl_price']:
                        pos['sl_price'] = potential_sl
                
                if (ts - pos['entry_time']).total_seconds() / 3600 >= 72:
                    exit_price = row['close']
                    pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price']
                    net_pnl_pct = pnl_pct - (COMMISSION * 2) - SLIPPAGE
                    pnl_usd = pos['position_size'] * net_pnl_pct
                    balance += pnl_usd
                    pos['exit_price'] = exit_price
                    pos['exit_time'] = ts
                    pos['pnl_usd'] = pnl_usd
                    pos['net_pnl_pct'] = net_pnl_pct
                    pos['status'] = "TIME_EXIT"
                    pos['balance_after'] = balance
                    trade_history.append(pos)
                else:
                    still_open.append(pos)
                    
        open_positions = still_open
        
        # 2. Look for new signals
        X_test = group[features]
        probs = model.predict_proba(X_test)[:, 1]
        
        candidates = []
        for i, row in group.iterrows():
            prob = probs[group.index.get_loc(i)]
            
            # Use specific ADX limits (found ADX>20 in train)
            if prob > 0.55 and row['adx_14'] > 20:
                sym = row['symbol']
                if any(p['symbol'] == sym for p in open_positions):
                    continue
                # Add momentum score to choose the best one
                candidates.append((sym, row, prob))
                
        # CROSS-SECTIONAL ALPHA: If multiple signals, pick the one with highest momentum
        if candidates:
            # Sort by slope_10 (momentum) descending
            candidates.sort(key=lambda x: x[1]['slope_10_pct'], reverse=True)
            best_candidate = candidates[0]
            
            sym = best_candidate[0]
            row = best_candidate[1]
            prob = best_candidate[2]
            
            entry_price = row['close']
            atr = (row['atr_14_pct'] / 100) * entry_price
            
            sl_price = entry_price - (1.5 * atr)
            breakeven_target = entry_price + (2.0 * atr)
            
            risk_usd = balance * RISK_PER_TRADE
            sl_pct = (entry_price - sl_price) / entry_price
            position_size = risk_usd / sl_pct
            
            max_pos_size = balance * 5
            current_exposure = sum(p['position_size'] for p in open_positions)
            
            if current_exposure + position_size <= max_pos_size:
                open_positions.append({
                    'symbol': sym,
                    'entry_time': ts,
                    'entry_price': entry_price,
                    'sl_price': sl_price,
                    'breakeven_target': breakeven_target,
                    'is_breakeven_hit': False,
                    'atr_val': atr,
                    'position_size': position_size,
                    'risk_usd': risk_usd,
                    'win_prob': prob
                })

    # Close remaining
    for pos in open_positions:
        sym = pos['symbol']
        last_row = test_df[test_df['symbol'] == sym].iloc[-1]
        exit_price = last_row['close']
        pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price']
        net_pnl_pct = pnl_pct - (COMMISSION * 2) - SLIPPAGE
        pnl_usd = pos['position_size'] * net_pnl_pct
        balance += pnl_usd
        pos['exit_price'] = exit_price
        pos['exit_time'] = last_row['ts']
        pos['pnl_usd'] = pnl_usd
        pos['net_pnl_pct'] = net_pnl_pct
        pos['status'] = "FORCE_CLOSE"
        pos['balance_after'] = balance
        trade_history.append(pos)
        
    trades_df = pd.DataFrame(trade_history)
    if len(trades_df) > 0:
        win_rate = len(trades_df[trades_df['pnl_usd'] > 0]) / len(trades_df) * 100
        total_pnl = trades_df['pnl_usd'].sum()
        
        balances = [START_BALANCE] + trades_df['balance_after'].tolist()
        peak = balances[0]
        max_dd = 0
        for b in balances:
            if b > peak: peak = b
            dd = (peak - b) / peak * 100
            if dd > max_dd: max_dd = dd
            
        print("\n=== V29 EXPONENTIAL ALPHA (MULTI-COIN) OOS BACKTEST ===")
        print(f"Toplam İşlem: {len(trades_df)}")
        print(f"Kârlı İşlem Oranı: %{win_rate:.2f}")
        print(f"Max Drawdown: %{max_dd:.2f}")
        print(f"Bitiş Bakiyesi: ${balance:.2f} (Net Kâr: ${total_pnl:.2f})")
        print(f"Net Getiri (OOS 3 Ay): %{((balance - START_BALANCE)/START_BALANCE)*100:.2f}")
        
        print("\nKoin Bazlı Kâr/Zarar:")
        print(trades_df.groupby('symbol')['pnl_usd'].sum().sort_values(ascending=False))
        
        best_trade = trades_df.loc[trades_df['pnl_usd'].idxmax()]
        print(f"\nEn Kazançlı İşlem: {best_trade['symbol']} -> +${best_trade['pnl_usd']:.2f}")

if __name__ == "__main__":
    run_v29_multi_asset()
