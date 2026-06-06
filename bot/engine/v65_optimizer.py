import pandas as pd
import numpy as np
import xgboost as xgb
import os
import ta

ENTRY_FEE = 0.0009
TP_FEE = 0.0001
SL_FEE = 0.0009
START_BALANCE = 100.0
LEVERAGE = 10
TP_PCT = 0.020
SL_PCT = 0.010

def prepare_mtf_data(df):
    df = df.copy()
    
    df_1h = df.set_index('ts').resample('1h').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
    }).dropna().reset_index()
    
    df_1h['ema_50_1h'] = df_1h['close'].ewm(span=50, adjust=False).mean()
    
    df_1h_feat = df_1h[['ts', 'close', 'ema_50_1h']].copy()
    df_1h_feat.rename(columns={'close': 'close_1h'}, inplace=True)
    
    df = pd.merge_asof(df.sort_values('ts'), df_1h_feat.sort_values('ts'), on='ts', direction='backward')
    return df

def run_v65_optimizer():
    features_dir = 'bot/engine/features_v63'
    files = [f for f in os.listdir(features_dir) if f.endswith('.csv')]
    
    all_data = []
    for f in files:
        sym = f.replace('.csv', '')
        df = pd.read_csv(os.path.join(features_dir, f), parse_dates=['ts'])
        df = prepare_mtf_data(df)
        df['symbol'] = sym
        all_data.append(df)
        
    full_df = pd.concat(all_data)
    full_df.sort_values(by='ts', inplace=True)
    full_df.reset_index(drop=True, inplace=True)
    
    features = [
        'whale_anomaly', 'taker_buy_surge', 'trade_size', 'taker_buy_ratio',
        'dist_ema50', 'macd_diff', 'rsi', 'hour_sin', 'hour_cos'
    ]
    
    valid_df = full_df.dropna(subset=features + ['target', 'ema_50_1h'])
    
    train_df = valid_df[valid_df['ts'] < '2025-07-01']
    test_df = valid_df[valid_df['ts'] >= '2025-07-01']
    
    target_count = train_df['target'].sum()
    total_count = len(train_df)
    scale_pos = (total_count - target_count) / target_count
    
    X_train = train_df[features]
    y_train = train_df['target']
    
    model_ai = xgb.XGBClassifier(
        n_estimators=400, max_depth=7, learning_rate=0.02, 
        subsample=0.8, colsample_bytree=0.8, random_state=42, 
        eval_metric='logloss', tree_method='hist',
        scale_pos_weight=scale_pos
    )
    model_ai.fit(X_train, y_train)
    
    test_features = test_df[features].fillna(0)
    test_df['ai_prob'] = model_ai.predict_proba(test_features)[:, 1]
    
    # Hafifletilmiş Makro Filtre (ADX yok, sadece 1H EMA ve 15M Supertrend)
    test_df['macro_ok'] = (
        (test_df['supertrend_dir'] == 1) & 
        (test_df['macd_diff'] > 0) &
        (test_df['close_1h'] > test_df['ema_50_1h'])
    )
    
    thresholds = [0.60, 0.62, 0.64, 0.66, 0.68, 0.70]
    
    for thresh in thresholds:
        balance = START_BALANCE
        open_positions = []
        trade_history = []
        in_recovery_mode = False
        
        grouped = test_df.groupby('ts')
        
        for ts, group in grouped:
            still_open = []
            for pos in open_positions:
                sym = pos['symbol']
                sym_data = group[group['symbol'] == sym]
                if len(sym_data) == 0:
                    still_open.append(pos)
                    continue
                    
                row = sym_data.iloc[0]
                hit_tp = row['high'] >= pos['tp_price']
                hit_sl = row['low'] <= pos['sl_price']
                
                if hit_sl or hit_tp:
                    if hit_tp and not hit_sl:
                        net_pnl_pct = TP_PCT - (ENTRY_FEE + TP_FEE)
                        in_recovery_mode = False
                    else: 
                        net_pnl_pct = -SL_PCT - (ENTRY_FEE + SL_FEE)
                        in_recovery_mode = True
                        
                    pnl_usd = pos['margin_usd'] * LEVERAGE * net_pnl_pct
                    balance += pnl_usd
                    pos['pnl_usd'] = pnl_usd
                    trade_history.append(pos)
                else:
                    if (ts - pos['entry_time']).total_seconds() / 60 >= (15 * 32):
                        exit_price = row['close']
                        net_pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price'] - (ENTRY_FEE + SL_FEE)
                        pnl_usd = pos['margin_usd'] * LEVERAGE * net_pnl_pct
                        balance += pnl_usd
                        pos['pnl_usd'] = pnl_usd
                        in_recovery_mode = (pnl_usd < 0)
                        trade_history.append(pos)
                    else:
                        still_open.append(pos)
            
            open_positions = still_open
            
            if len(group) > 0 and len(open_positions) < 1:
                req_thresh = (thresh + 0.05) if in_recovery_mode else thresh
                valid_candidates = group[(group['macro_ok'] == True) & (group['ai_prob'] > req_thresh)]
                
                if len(valid_candidates) > 0:
                    best_candidate = valid_candidates.sort_values(by='ai_prob', ascending=False).iloc[0]
                    bet_pct = 0.50 if in_recovery_mode else 0.25
                    
                    open_positions.append({
                        'symbol': best_candidate['symbol'],
                        'entry_time': ts,
                        'entry_price': best_candidate['close'],
                        'sl_price': best_candidate['close'] * (1 - SL_PCT),
                        'tp_price': best_candidate['close'] * (1 + TP_PCT),
                        'margin_usd': balance * bet_pct
                    })

        for pos in open_positions:
            last_row = test_df[test_df['symbol'] == pos['symbol']].iloc[-1]
            net_pnl_pct = (last_row['close'] - pos['entry_price']) / pos['entry_price'] - (ENTRY_FEE + SL_FEE)
            balance += pos['margin_usd'] * LEVERAGE * net_pnl_pct
            pos['pnl_usd'] = pos['margin_usd'] * LEVERAGE * net_pnl_pct
            trade_history.append(pos)
            
        tdf = pd.DataFrame(trade_history)
        if len(tdf) > 0:
            win_rate = len(tdf[tdf['pnl_usd'] > 0]) / len(tdf) * 100
            print(f"[Thresh {thresh:.2f}] İşlem: {len(tdf):>4} | Kasa: ${balance:>8.2f} | WinRate: %{win_rate:.1f}")

if __name__ == "__main__":
    run_v65_optimizer()
