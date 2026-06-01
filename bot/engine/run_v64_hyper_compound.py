import pandas as pd
import numpy as np
import xgboost as xgb
import os

ENTRY_FEE = 0.0009
TP_FEE = 0.0001
SL_FEE = 0.0009

START_BALANCE = 100.0
LEVERAGE = 10
TP_PCT = 0.020
SL_PCT = 0.010

# HIPER-BÜYÜME AYARLARI (User's request for "Uçurması gerekmez mi")
NORMAL_BET_FRACTION = 0.40   # Kasanın %40'ı ile gir!
RECOVERY_BET_FRACTION = 0.80 # Zararda kasanın %80'i ile girip intikam al!
OPTIMAL_THRESHOLD = 0.60     # Eşiği düşür! Sadece mükemmeli değil, 'çok iyi'leri de al (Daha çok işlem)
RECOVERY_THRESHOLD = 0.65    # Kurtarma için biraz daha emin ol

def run_v64_hyper_compound():
    print("🚀 V64 HYPER COMPOUND: Hedef Daha Çok İşlem ve Uçuş...")
    
    features_dir = 'bot/engine/features_v63'
    files = [f for f in os.listdir(features_dir) if f.endswith('.csv')]
    
    all_data = []
    for f in files:
        sym = f.replace('.csv', '')
        df = pd.read_csv(os.path.join(features_dir, f), parse_dates=['ts'])
        df['symbol'] = sym
        all_data.append(df)
        
    full_df = pd.concat(all_data)
    full_df.sort_values(by='ts', inplace=True)
    full_df.reset_index(drop=True, inplace=True)
    
    features = [
        'whale_anomaly', 'taker_buy_surge', 'trade_size', 'taker_buy_ratio',
        'dist_ema50', 'macd_diff', 'rsi', 'hour_sin', 'hour_cos'
    ]
    
    valid_df = full_df.dropna(subset=features + ['target'])
    train_df = valid_df[valid_df['ts'] < '2024-07-01']
    
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
    
    full_features = full_df[features].fillna(0)
    ai_probs = model_ai.predict_proba(full_features)[:, 1]
    full_df['ai_prob'] = ai_probs
    
    # Makro filtreyi biraz daha gevşetelim (Daha çok işlem için)
    full_df['macro_ok'] = (
        (full_df['supertrend_dir'] == 1) & 
        (full_df['macd_diff'] > 0)
    )
    
    balance = START_BALANCE
    open_positions = []
    trade_history = []
    in_recovery_mode = False
    grouped = full_df.groupby('ts')
    
    for ts, group in grouped:
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
            
            hit_tp = False
            hit_sl = False
            
            if low <= pos['sl_price']:
                hit_sl = True
            elif high >= pos['tp_price']:
                hit_tp = True
                
            if hit_sl or hit_tp:
                if hit_tp and not hit_sl:
                    net_pnl_pct = TP_PCT - (ENTRY_FEE + TP_FEE)
                    in_recovery_mode = False
                else: 
                    net_pnl_pct = -SL_PCT - (ENTRY_FEE + SL_FEE)
                    in_recovery_mode = True
                    
                pnl_usd = pos['margin_usd'] * LEVERAGE * net_pnl_pct
                balance += pnl_usd
                pos['exit_time'] = ts
                pos['pnl_usd'] = pnl_usd
                trade_history.append(pos)
            else:
                if (ts - pos['entry_time']).total_seconds() / 60 >= (15 * 32):
                    exit_price = row['close']
                    pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price']
                    net_pnl_pct = pnl_pct - (ENTRY_FEE + SL_FEE)
                    pnl_usd = pos['margin_usd'] * LEVERAGE * net_pnl_pct
                    
                    balance += pnl_usd
                    pos['exit_time'] = ts
                    pos['pnl_usd'] = pnl_usd
                    if pnl_usd < 0:
                        in_recovery_mode = True
                    else:
                        in_recovery_mode = False
                    trade_history.append(pos)
                else:
                    still_open.append(pos)
                    
        open_positions = still_open
        
        if len(group) > 0 and len(open_positions) < 1:
            required_threshold = RECOVERY_THRESHOLD if in_recovery_mode else OPTIMAL_THRESHOLD
            valid_candidates = group[(group['macro_ok'] == True) & (group['ai_prob'] > required_threshold)]
            
            if len(valid_candidates) > 0:
                best_candidate = valid_candidates.sort_values(by='ai_prob', ascending=False).iloc[0]
                
                entry_price = best_candidate['close']
                bet_pct = RECOVERY_BET_FRACTION if in_recovery_mode else NORMAL_BET_FRACTION
                margin_usd = balance * bet_pct 
                
                open_positions.append({
                    'symbol': best_candidate['symbol'],
                    'entry_time': ts,
                    'entry_price': entry_price,
                    'sl_price': entry_price * (1 - SL_PCT),
                    'tp_price': entry_price * (1 + TP_PCT),
                    'margin_usd': margin_usd
                })

    for pos in open_positions:
        sym = pos['symbol']
        last_row = full_df[full_df['symbol'] == sym].iloc[-1]
        exit_price = last_row['close']
        pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price']
        net_pnl_pct = pnl_pct - (ENTRY_FEE + SL_FEE)
        pnl_usd = pos['margin_usd'] * LEVERAGE * net_pnl_pct
        balance += pnl_usd
        pos['pnl_usd'] = pnl_usd
        trade_history.append(pos)
        
    trades_df = pd.DataFrame(trade_history)
    if len(trades_df) == 0:
        print("Hiç işlem açılmadı.")
        return
        
    win_rate = len(trades_df[trades_df['pnl_usd'] > 0]) / len(trades_df) * 100
    
    print(f"\n🚀 V64 HIPER COMPOUND ÖZET (Uçuş Modu) 🚀")
    print(f"Normal Bet: %{NORMAL_BET_FRACTION*100} (Threshold: {OPTIMAL_THRESHOLD})")
    print(f"Recovery Bet: %{RECOVERY_BET_FRACTION*100} (Threshold: {RECOVERY_THRESHOLD})")
    print(f"Başlangıç Bakiyesi: ${START_BALANCE:.2f}")
    print(f"Bitiş Bakiyesi: ${balance:.2f} (x{balance/START_BALANCE:.2f} KATLAMA)")
    print(f"Toplam İşlem: {len(trades_df)}")
    print(f"Kazanma Oranı (Win Rate): %{win_rate:.1f}")

if __name__ == "__main__":
    run_v64_hyper_compound()
