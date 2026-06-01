import pandas as pd
import numpy as np
import xgboost as xgb
import os

COMMISSION = 0.0004
SLIPPAGE = 0.0005
START_BALANCE = 100.0

def run_v38_mega_bull():
    features_dir = 'bot/engine/features_v37'
    files = [f for f in os.listdir(features_dir) if f.endswith('.csv')]
    
    all_data = []
    print("V38 Mega Boğa Simülasyonu (Zaman Makinesi) Başlatılıyor...")
    print("Veriler yükleniyor...")
    for f in files:
        df = pd.read_csv(os.path.join(features_dir, f), parse_dates=['ts'])
        df['symbol'] = f.replace('.csv', '')
        all_data.append(df)
        
    combined_df = pd.concat(all_data)
    combined_df.sort_values(by='ts', inplace=True)
    combined_df.reset_index(drop=True, inplace=True)
    
    # Zaman Makinesi: Reverse Walk-Forward Split
    split_date = pd.to_datetime('2024-06-01')
    
    # Yapay zeka 2024-2026 testere (kâbus) dönemini ezberler
    train_df = combined_df[combined_df['ts'] >= split_date].copy()
    
    # Kör Test 2023-2024 Mega Boğa dönemine gönderilir
    test_df = combined_df[combined_df['ts'] < split_date].copy()
    
    features = [c for c in combined_df.columns if c not in [
        'ts', 'open', 'high', 'low', 'close', 'volume', 'symbol',
        'target', 'target_is_trend'
    ]]
    
    train_df.dropna(subset=features + ['target', 'target_is_trend'], inplace=True)
    
    X_train = train_df[features]
    y_train_trend = train_df['target_is_trend']
    y_train_sniper = train_df['target']
    
    print("Ajan 1 Eğitiliyor: Gözcü (2024-2026 Testeresini Öğreniyor)...")
    model_watcher = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric='logloss',
        tree_method='hist'
    )
    model_watcher.fit(X_train, y_train_trend)
    
    print("Ajan 2 Eğitiliyor: Keskin Nişancı (Sadece Gerçek Kırılımlar)...")
    model_sniper = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric='logloss',
        tree_method='hist'
    )
    model_sniper.fit(X_train, y_train_sniper)
    print("Zaman Makinesi Hazır. Sistem 2023 Yılına Işınlanıyor!")
    
    balance = START_BALANCE
    open_positions = []
    trade_history = []
    
    print("\nSaf Kör Test (2023-2024 Mega Boğa OOS) Başlıyor. Başlangıç Kasası: $100")
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
            
            # Ajan 3: Risk Yöneticisi (İz Süren Stop ile Eksponansiyel Taşıma)
            if high > pos['highest_reached']:
                pos['highest_reached'] = high
                potential_sl = pos['highest_reached'] - (3.0 * pos['atr_val'])
                if potential_sl > pos['sl_price']:
                    pos['sl_price'] = potential_sl
            
            if low <= pos['sl_price']:
                exit_price = pos['sl_price']
                pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price']
                net_pnl_pct = pnl_pct - (COMMISSION * 2) - SLIPPAGE
                pnl_usd = pos['position_size'] * net_pnl_pct
                
                balance += pnl_usd
                pos['exit_price'] = exit_price
                pos['exit_time'] = ts
                pos['pnl_usd'] = pnl_usd
                pos['net_pnl_pct'] = net_pnl_pct
                pos['status'] = "TRAIL_STOP"
                pos['balance_after'] = balance
                trade_history.append(pos)
            else:
                # Maksimum bekleme süresi (Mega Boğada trendler uzundur: 30 Gün)
                if (ts - pos['entry_time']).total_seconds() / 3600 >= 720:
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
            probs_trend = model_watcher.predict_proba(X_test)[:, 1]
            probs_sniper = model_sniper.predict_proba(X_test)[:, 1]
            
            candidates = []
            for i, row in group.reset_index(drop=True).iterrows():
                sym = row['symbol']
                if any(p['symbol'] == sym for p in open_positions):
                    continue
                    
                prob_trend = probs_trend[i]
                prob_sniper = probs_sniper[i]
                
                # Ajan 1 Onayı: Piyasa Chop Değil! (> %65 İhtimal)
                if prob_trend > 0.65:
                    # Ajan 2 Onayı: Temiz Kırılım (Breakout) Var! (> %60 İhtimal)
                    if prob_sniper > 0.60:
                        candidates.append((sym, row, prob_sniper))
                        
            if candidates:
                candidates.sort(key=lambda x: x[2], reverse=True)
                best_candidate = candidates[0]
                
                sym = best_candidate[0]
                row = best_candidate[1]
                prob = best_candidate[2]
                
                # Ajan 3: Risk Yöneticisi
                # Kelly (Max %20)
                risk_pct = min(0.20, max(0.02, (prob - 0.50) * 0.50))
                
                entry_price = row['close']
                atr = (row['atr_14_pct'] / 100) * entry_price
                sl_price = entry_price - (2.0 * atr)
                
                risk_usd = balance * risk_pct
                sl_pct = (entry_price - sl_price) / entry_price
                if sl_pct < 0.005: sl_pct = 0.005
                position_size = risk_usd / sl_pct
                
                max_pos_size = balance * 10
                current_exposure = sum(p['position_size'] for p in open_positions)
                
                if current_exposure + position_size <= max_pos_size and len(open_positions) < 2:
                    open_positions.append({
                        'symbol': sym,
                        'entry_time': ts,
                        'entry_price': entry_price,
                        'sl_price': sl_price,
                        'highest_reached': entry_price,
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
    
    print("\nSimülasyon Tamamlandı. V38 Mega Boğa Raporu Oluşturuluyor...\n")
    
    if len(trades_df) == 0:
         print("Sistem hiç işlem açmadı!")
         return
         
    # Haftalık (veya Aylık) raporlama için başlangıç zamanını test periyodunun başına alalım
    start_test_date = trades_df['entry_time'].min()
    trades_df['exit_time'] = pd.to_datetime(trades_df['exit_time'])
    trades_df['week'] = ((trades_df['exit_time'] - start_test_date).dt.days // 7) + 1
    
    weekly_summary = []
    
    for week_num, group in trades_df.groupby('week'):
        num_trades = len(group)
        weekly_pnl = group['pnl_usd'].sum()
        end_balance = group['balance_after'].iloc[-1]
        
        if len(weekly_summary) == 0:
            prev_balance = START_BALANCE
        else:
            prev_balance = weekly_summary[-1]['Kasa ($)']
            
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
            'K/Z ($)': round(weekly_pnl, 2),
            'Getiri (%)': round(weekly_ret, 2),
            'Kasa ($)': round(end_balance, 2)
        })
        
    weekly_df = pd.DataFrame(weekly_summary)
    print(weekly_df.to_string(index=False))
    
    print("\n--- V38 MEGA BOĞA SİMÜLASYONU ÖZETİ ---")
    print(f"Eğitim: 2024-2026 (Chop) | Test (OOS): 2023-2024 (Boğa)")
    print(f"Toplam İşlem: {len(trades_df)}")
    print(f"Başlangıç: $100.00")
    print(f"Bitiş: ${balance:.2f}")

if __name__ == "__main__":
    run_v38_mega_bull()
