import pandas as pd
import numpy as np
import xgboost as xgb
import os

COMMISSION = 0.0004
SLIPPAGE = 0.0005
START_BALANCE = 100.0

def run_v35_omni_convexity():
    features_dir = 'bot/engine/features_v33'
    files = [f for f in os.listdir(features_dir) if f.endswith('.csv')]
    
    all_data = []
    print("V35 Omni-Convexity (Çift Yönlü Çarpan) Başlatılıyor...")
    print("Veriler yükleniyor...")
    for f in files:
        df = pd.read_csv(os.path.join(features_dir, f), parse_dates=['ts'])
        df['symbol'] = f.replace('.csv', '')
        
        import ta
        adx_ind = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
        df['adx_14'] = adx_ind.adx()
        
        all_data.append(df)
        
    combined_df = pd.concat(all_data)
    combined_df.sort_values(by='ts', inplace=True)
    combined_df.reset_index(drop=True, inplace=True)
    
    split_date = pd.to_datetime('2025-06-01')
    
    train_df = combined_df[combined_df['ts'] < split_date].copy()
    test_df = combined_df[combined_df['ts'] >= split_date].copy()
    
    # Hedefler V33 datasetinde target_dir olarak mevcut (-1 Short, 0 Flat, 1 Long)
    features = [c for c in combined_df.columns if c not in [
        'ts', 'open', 'high', 'low', 'close', 'volume', 'symbol',
        'target_dir', 'target_max_up', 'target_max_down', 'target'
    ]]
    
    train_df.dropna(subset=features + ['target_dir'], inplace=True)
    
    X_train = train_df[features]
    y_train = train_df['target_dir'].map({-1.0: 0, 0.0: 1, 1.0: 2})
    
    print("XGBoost Omni Modeli Eğitiliyor (Long/Short/Flat)...")
    model = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric='mlogloss',
        tree_method='hist'
    )
    model.fit(X_train, y_train)
    print("Model Eğitimi Tamamlandı.")
    
    balance = START_BALANCE
    open_positions = []
    trade_history = []
    
    print("\nSaf Kör Test (V35 Omni-Convexity OOS) Başlıyor. Başlangıç Kasası: $100")
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
            
            # İz Süren (Trailing) Maksimum/Minimum Fiyat
            if pos['direction'] == 'LONG':
                if high > pos['extreme_reached']:
                    pos['extreme_reached'] = high
                    potential_sl = pos['extreme_reached'] - (3.0 * pos['atr_val'])
                    if potential_sl > pos['sl_price']:
                        pos['sl_price'] = potential_sl
                        
                # Pyramiding (LONG)
                pyramid_threshold = pos['initial_entry'] + (1.5 * pos['atr_val'])
                if pos['extreme_reached'] >= pyramid_threshold and pos['pyramid_count'] < 1:
                    add_usd = pos['risk_usd'] * 0.5
                    add_price = row['close']
                    pos['position_size'] += add_usd / (add_price * 0.02)
                    pos['pyramid_count'] += 1
                    if pos['sl_price'] < pos['initial_entry']:
                        pos['sl_price'] = pos['initial_entry']
                        
                # SL Hit (LONG)
                hit_sl = low <= pos['sl_price']
                if hit_sl:
                    exit_price = pos['sl_price']
            else:
                # SHORT
                if low < pos['extreme_reached']:
                    pos['extreme_reached'] = low
                    potential_sl = pos['extreme_reached'] + (3.0 * pos['atr_val'])
                    if potential_sl < pos['sl_price']:
                        pos['sl_price'] = potential_sl
                        
                # Pyramiding (SHORT)
                pyramid_threshold = pos['initial_entry'] - (1.5 * pos['atr_val'])
                if pos['extreme_reached'] <= pyramid_threshold and pos['pyramid_count'] < 1:
                    add_usd = pos['risk_usd'] * 0.5
                    add_price = row['close']
                    pos['position_size'] += add_usd / (add_price * 0.02)
                    pos['pyramid_count'] += 1
                    if pos['sl_price'] > pos['initial_entry']:
                        pos['sl_price'] = pos['initial_entry']
                        
                # SL Hit (SHORT)
                hit_sl = high >= pos['sl_price']
                if hit_sl:
                    exit_price = pos['sl_price']
            
            if hit_sl:
                if pos['direction'] == 'LONG':
                    pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price']
                else:
                    pnl_pct = (pos['entry_price'] - exit_price) / pos['entry_price']
                    
                net_pnl_pct = pnl_pct - (COMMISSION * 2) - SLIPPAGE
                pnl_usd = pos['position_size'] * net_pnl_pct
                
                balance += pnl_usd
                pos['exit_price'] = exit_price
                pos['exit_time'] = ts
                pos['pnl_usd'] = pnl_usd
                pos['net_pnl_pct'] = net_pnl_pct
                
                if pos['pyramid_count'] > 0 and pnl_usd > 0:
                    pos['status'] = "PYRAMID_WIN_TRAIL"
                elif pos['pyramid_count'] > 0 and pnl_usd <= 0:
                    pos['status'] = "PYRAMID_BREAKEVEN"
                else:
                    pos['status'] = "TRAIL_STOP"
                    
                pos['balance_after'] = balance
                trade_history.append(pos)
            else:
                # Time Exit (Trend yakalayamazsak 10 gün sonra çık)
                if (ts - pos['entry_time']).total_seconds() / 3600 >= 240:
                    exit_price = row['close']
                    if pos['direction'] == 'LONG':
                        pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price']
                    else:
                        pnl_pct = (pos['entry_price'] - exit_price) / pos['entry_price']
                        
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
            probs = model.predict_proba(X_test)
            
            candidates = []
            for i, row in group.reset_index(drop=True).iterrows():
                prob_short = probs[i][0]
                prob_long = probs[i][2]
                
                # REJİM FİLTRESİ: Kalkan ADX > 25 ise Trend var.
                if row['adx_14'] > 25:
                    sym = row['symbol']
                    if any(p['symbol'] == sym for p in open_positions):
                        continue
                        
                    if prob_long > 0.60:
                        candidates.append((sym, row, prob_long, 'LONG'))
                    elif prob_short > 0.60:
                        candidates.append((sym, row, prob_short, 'SHORT'))
                    
            if candidates:
                # LONG ise momentumu en pozitif olanı, SHORT ise en negatif olanı seç
                # Biz en güçlü trendi seçeceğiz (Mutlak değere göre)
                candidates.sort(key=lambda x: abs(x[1]['slope_10_pct']), reverse=True)
                best_candidate = candidates[0]
                
                sym = best_candidate[0]
                row = best_candidate[1]
                prob = best_candidate[2]
                direction = best_candidate[3]
                
                # Dinamik Risk (Kelly): Maksimum %15 Risk
                risk_pct = min(0.15, max(0.02, (prob - 0.50) * 0.50))
                
                entry_price = row['close']
                atr = (row['atr_14_pct'] / 100) * entry_price
                
                if direction == 'LONG':
                    sl_price = entry_price - (1.5 * atr)
                else:
                    sl_price = entry_price + (1.5 * atr)
                
                risk_usd = balance * risk_pct
                sl_pct = abs(entry_price - sl_price) / entry_price
                if sl_pct < 0.005: sl_pct = 0.005
                position_size = risk_usd / sl_pct
                
                max_pos_size = balance * 5
                current_exposure = sum(p['position_size'] for p in open_positions)
                
                if current_exposure + position_size <= max_pos_size and len(open_positions) < 2:
                    open_positions.append({
                        'symbol': sym,
                        'direction': direction,
                        'entry_time': ts,
                        'entry_price': entry_price,
                        'initial_entry': entry_price,
                        'sl_price': sl_price,
                        'extreme_reached': entry_price,
                        'atr_val': atr,
                        'position_size': position_size,
                        'risk_usd': risk_usd,
                        'win_prob': prob,
                        'risk_pct': risk_pct,
                        'pyramid_count': 0
                    })

    for pos in open_positions:
        sym = pos['symbol']
        last_row = test_df[test_df['symbol'] == sym].iloc[-1]
        exit_price = last_row['close']
        
        if pos['direction'] == 'LONG':
            pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price']
        else:
            pnl_pct = (pos['entry_price'] - exit_price) / pos['entry_price']
            
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
    
    print("\nSimülasyon Tamamlandı. V35 Omni-Convexity Raporu Oluşturuluyor...\n")
    
    if len(trades_df) == 0:
         print("Sistem hiç işlem açmadı!")
         return
         
    trades_df['exit_time'] = pd.to_datetime(trades_df['exit_time'])
    trades_df['week'] = ((trades_df['exit_time'] - split_date).dt.days // 7) + 1
    
    weekly_summary = []
    
    for week_num, group in trades_df.groupby('week'):
        num_trades = len(group)
        num_shorts = len(group[group['direction'] == 'SHORT'])
        num_longs = len(group[group['direction'] == 'LONG'])
        pyramids = len(group[group['pyramid_count'] > 0])
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
            'L/S': f"{num_longs}/{num_shorts}",
            'Piramit': pyramids,
            'K/Z ($)': round(weekly_pnl, 2),
            'Getiri (%)': round(weekly_ret, 2),
            'Kasa ($)': round(end_balance, 2)
        })
        
    weekly_df = pd.DataFrame(weekly_summary)
    print(weekly_df.to_string(index=False))
    
    print("\n--- V35 OMNI-CONVEXITY ÖZETİ (1 YIL KÖR TEST) ---")
    print(f"Eğitim: 2023-2025 | Test: 2025-2026")
    print(f"Toplam İşlem: {len(trades_df)} (Long: {len(trades_df[trades_df['direction'] == 'LONG'])}, Short: {len(trades_df[trades_df['direction'] == 'SHORT'])})")
    print(f"Piramit Atılan (Eksponansiyel) İşlem: {len(trades_df[trades_df['pyramid_count'] > 0])}")
    print(f"Başlangıç: $100.00")
    print(f"Bitiş: ${balance:.2f}")

if __name__ == "__main__":
    run_v35_omni_convexity()
