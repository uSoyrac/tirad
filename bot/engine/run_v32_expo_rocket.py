import pandas as pd
import numpy as np
import xgboost as xgb
import os
import ta

COMMISSION = 0.0004
SLIPPAGE = 0.0005
START_BALANCE = 100.0

def run_v32_expo_rocket():
    features_dir = 'bot/engine/features_v31'
    files = [f for f in os.listdir(features_dir) if f.endswith('.csv')]
    
    all_data = []
    print("V32 Eksponansiyel Roket Başlatılıyor...")
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
    
    split_date = pd.to_datetime('2025-06-01')
    
    train_df = combined_df[combined_df['ts'] < split_date].copy()
    test_df = combined_df[combined_df['ts'] >= split_date].copy()
    
    features = [c for c in combined_df.columns if c not in ['ts', 'open', 'high', 'low', 'close', 'volume', 'target', 'symbol', 'adx_14']]
    
    train_df.dropna(subset=features + ['target'], inplace=True)
    
    X_train = train_df[features]
    y_train = train_df['target']
    
    print("XGBoost Modeli Eğitiliyor...")
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
    
    print("Saf Kör Test (V32 Maksimum Büyüme) Başlıyor. Başlangıç Kasası: $100")
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
                    
                # V32 KURALI: Geniş Trailing Stop (3.5 ATR)
                if pos['is_breakeven_hit']:
                    potential_sl = high - (3.5 * pos['atr_val'])
                    if potential_sl > pos['sl_price']:
                        pos['sl_price'] = potential_sl
                
                if (ts - pos['entry_time']).total_seconds() / 3600 >= 144: # 6 days max hold to let runners run
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
        
        if len(group) > 0:
            X_test = group[features]
            probs = model.predict_proba(X_test)[:, 1]
            
            candidates = []
            for i, row in group.reset_index(drop=True).iterrows():
                prob = probs[i]
                
                # V32 KURALI: Erken Ateşleme (ADX > 15)
                if prob > 0.55 and row['adx_14'] > 15:
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
                
                # V32 KURALI: Dinamik Risk (Kelly Fraction)
                # Olasılık %50-%100 arasında. (prob - 0.5) * 0.5 -> max %25 risk
                risk_pct = min(0.25, max(0.01, (prob - 0.50) * 0.50))
                
                entry_price = row['close']
                atr = (row['atr_14_pct'] / 100) * entry_price
                
                sl_price = entry_price - (1.5 * atr)
                breakeven_target = entry_price + (2.0 * atr)
                
                risk_usd = balance * risk_pct
                sl_pct = (entry_price - sl_price) / entry_price
                position_size = risk_usd / sl_pct
                
                # Sınırsız agresif büyüme için max exposure kuralını esnet: Max 10x kasa pozisyonu
                max_pos_size = balance * 10
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
                        'win_prob': prob,
                        'risk_pct': risk_pct
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
    
    print("\nSimülasyon Tamamlandı. V32 Eksponansiyel Rapor Oluşturuluyor...\n")
    
    if len(trades_df) == 0:
         print("Sistem hiç işlem açmadı!")
         return
         
    trades_df['exit_time'] = pd.to_datetime(trades_df['exit_time'])
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
            'Kâr/Zarar ($)': round(weekly_pnl, 2),
            'Getiri (%)': round(weekly_ret, 2),
            'Kasa ($)': round(end_balance, 2)
        })
        
    weekly_df = pd.DataFrame(weekly_summary)
    print(weekly_df.to_string(index=False))
    
    print("\n--- V32 EKSPONANSİYEL ROKET ÖZETİ (1 YIL KÖR TEST) ---")
    print(f"Eğitim: 2023-2025 | Test: 2025-2026")
    print(f"Toplam İşlem: {len(trades_df)}")
    print(f"Başlangıç: $100.00")
    print(f"Bitiş: ${balance:.2f}")

if __name__ == "__main__":
    run_v32_expo_rocket()
