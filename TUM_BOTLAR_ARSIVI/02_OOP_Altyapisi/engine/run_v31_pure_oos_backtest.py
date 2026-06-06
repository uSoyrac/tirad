import pandas as pd
import numpy as np
import xgboost as xgb
import os
import ta

COMMISSION = 0.0004
SLIPPAGE = 0.0005
RISK_PER_TRADE = 0.02
START_BALANCE = 100.0

def run_v31_backtest():
    features_dir = 'bot/engine/features_v31'
    files = [f for f in os.listdir(features_dir) if f.endswith('.csv')]
    
    all_data = []
    print("Veriler yükleniyor ve ADX hesaplanıyor...")
    for f in files:
        df = pd.read_csv(os.path.join(features_dir, f), parse_dates=['ts'])
        df['symbol'] = f.replace('.csv', '')
        adx_ind = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
        df['adx_14'] = adx_ind.adx()
        all_data.append(df)
        
    combined_df = pd.concat(all_data)
    combined_df.sort_values(by='ts', inplace=True)
    combined_df.reset_index(drop=True, inplace=True)
    
    # Split Train (İlk 2 Yıl) ve Test (Son 1 Yıl)
    # Veri zaten 2023-06-01 ile 2026-06-01 arasında
    split_date = pd.to_datetime('2025-06-01')
    
    train_df = combined_df[combined_df['ts'] < split_date].copy()
    test_df = combined_df[combined_df['ts'] >= split_date].copy()
    
    features = [c for c in combined_df.columns if c not in ['ts', 'open', 'high', 'low', 'close', 'volume', 'target', 'symbol', 'adx_14']]
    
    # NaN temizliği
    train_df.dropna(subset=features + ['target'], inplace=True)
    
    X_train = train_df[features]
    y_train = train_df['target']
    
    print(f"Eğitim Seti (İlk 2 Yıl): {len(train_df)} mum")
    print(f"Kör Test Seti (Son 1 Yıl): {len(test_df)} mum")
    print("XGBoost Modeli Eğitiliyor (Bu işlem birkaç dakika sürebilir)...")
    
    model = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric='logloss',
        tree_method='hist'
    )
    model.fit(X_train, y_train)
    print("Model Eğitimi Tamamlandı.")
    
    balance = START_BALANCE
    open_positions = []
    trade_history = []
    
    print("Saf Kör Test (Out-of-Sample) Başlıyor. Başlangıç Kasası: $100")
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
        
        # Batch Predict for speed
        if len(group) > 0:
            X_test = group[features]
            # XGBoost requires columns to be in same order without missing if possible, 
            # but we ensured that in feature extraction
            probs = model.predict_proba(X_test)[:, 1]
            
            candidates = []
            for i, row in group.reset_index(drop=True).iterrows():
                prob = probs[i]
                
                if prob > 0.55 and row['adx_14'] > 20:
                    sym = row['symbol']
                    if any(p['symbol'] == sym for p in open_positions):
                        continue
                    candidates.append((sym, row, prob))
                    
            if candidates:
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
    
    print("\nSimülasyon Tamamlandı. Saf Kör (OOS) Haftalık Rapor Oluşturuluyor...\n")
    
    if len(trades_df) == 0:
         print("Sistem hiç işlem açmadı!")
         return
         
    trades_df['exit_time'] = pd.to_datetime(trades_df['exit_time'])
    
    # Week calculation based on split_date to ensure Week 1 starts exactly at the start of OOS test
    trades_df['week'] = ((trades_df['exit_time'] - split_date).dt.days // 7) + 1
    
    weekly_summary = []
    
    for week_num, group in trades_df.groupby('week'):
        num_trades = len(group)
        weekly_pnl = group['pnl_usd'].sum()
        end_balance = group['balance_after'].iloc[-1]
        
        if week_num == 1:
            prev_balance = START_BALANCE
        else:
            prev_balance = end_balance - weekly_pnl
            
        if prev_balance > 0:
            weekly_ret = (weekly_pnl / prev_balance) * 100
        else:
            weekly_ret = 0.0
            
        start_date = group['exit_time'].min().strftime('%Y-%m-%d')
        end_date = group['exit_time'].max().strftime('%Y-%m-%d')
        
        weekly_summary.append({
            'Hafta': int(week_num),
            'Tarih': f"{start_date} / {end_date}",
            'İşlem': num_trades,
            'Haftalık Kâr/Zarar ($)': round(weekly_pnl, 2),
            'Haftalık Getiri (%)': round(weekly_ret, 2),
            'Kasa ($)': round(end_balance, 2)
        })
        
    weekly_df = pd.DataFrame(weekly_summary)
    
    print(weekly_df.to_string(index=False))
    
    print("\n--- KUSURSUZ TEST ÖZETİ (1 YIL OOS) ---")
    print(f"Eğitim: 2023-2025 | Test: 2025-2026")
    print(f"Toplam İşlem: {len(trades_df)}")
    print(f"Başlangıç: $100.00")
    print(f"Bitiş: ${balance:.2f}")

if __name__ == "__main__":
    run_v31_backtest()
