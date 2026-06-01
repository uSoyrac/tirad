import pandas as pd
import numpy as np
import xgboost as xgb
import os

COMMISSION = 0.0004
SLIPPAGE = 0.0005
START_BALANCE = 100.0

def run_v33_omniscient():
    features_dir = 'bot/engine/features_v33'
    files = [f for f in os.listdir(features_dir) if f.endswith('.csv')]
    
    all_data = []
    print("V33 Her Şeyi Bilen Yapay Zeka (Omniscient AI) Başlatılıyor...")
    for f in files:
        df = pd.read_csv(os.path.join(features_dir, f), parse_dates=['ts'])
        df['symbol'] = f.replace('.csv', '')
        all_data.append(df)
        
    combined_df = pd.concat(all_data)
    combined_df.sort_values(by='ts', inplace=True)
    combined_df.reset_index(drop=True, inplace=True)
    
    split_date = pd.to_datetime('2025-06-01')
    
    train_df = combined_df[combined_df['ts'] < split_date].copy()
    test_df = combined_df[combined_df['ts'] >= split_date].copy()
    
    features = [c for c in combined_df.columns if c not in [
        'ts', 'open', 'high', 'low', 'close', 'volume', 'symbol',
        'target_dir', 'target_max_up', 'target_max_down', 'target'
    ]]
    
    train_df.dropna(subset=features + ['target_dir', 'target_max_up', 'target_max_down'], inplace=True)
    
    X_train = train_df[features]
    
    # 1. Yön Modeli (Classifier: -1 -> 0, 0 -> 1, 1 -> 2)
    y_train_dir = train_df['target_dir'].map({-1.0: 0, 0.0: 1, 1.0: 2})
    
    # 2. TP Modeli (Regressor)
    y_train_tp = train_df['target_max_up']
    
    # 3. SL Modeli (Regressor)
    y_train_sl = train_df['target_max_down']
    
    print("3 Ayrı Yapay Zeka Modeli Eğitiliyor (Sınıflandırma ve 2x Regresyon)...")
    
    model_dir = xgb.XGBClassifier(n_estimators=200, max_depth=5, learning_rate=0.05, 
                                  subsample=0.8, colsample_bytree=0.8, random_state=42, 
                                  eval_metric='mlogloss', tree_method='hist')
    model_dir.fit(X_train, y_train_dir)
    print(" 1/3: Yön Modeli Eğitildi (LONG/SHORT/FLAT).")
    
    model_tp = xgb.XGBRegressor(n_estimators=200, max_depth=5, learning_rate=0.05, 
                                subsample=0.8, colsample_bytree=0.8, random_state=42, 
                                eval_metric='rmse', tree_method='hist')
    model_tp.fit(X_train, y_train_tp)
    print(" 2/3: Dinamik Kâr (TP) Modeli Eğitildi.")
    
    model_sl = xgb.XGBRegressor(n_estimators=200, max_depth=5, learning_rate=0.05, 
                                subsample=0.8, colsample_bytree=0.8, random_state=42, 
                                eval_metric='rmse', tree_method='hist')
    model_sl.fit(X_train, y_train_sl)
    print(" 3/3: Dinamik Zarar (SL) Modeli Eğitildi.")
    
    balance = START_BALANCE
    open_positions = []
    trade_history = []
    
    print("\nSaf Kör Test (OOS) Başlıyor. Başlangıç Kasası: $100")
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
            
            # Dinamik Olarak Belirlenmiş TP ve SL seviyelerini kontrol et
            hit_tp = False
            hit_sl = False
            exit_price = 0
            
            if pos['direction'] == 'LONG':
                if low <= pos['sl_price']:
                    hit_sl = True
                    exit_price = pos['sl_price']
                elif high >= pos['tp_price']:
                    hit_tp = True
                    exit_price = pos['tp_price']
            else: # SHORT
                if high >= pos['sl_price']:
                    hit_sl = True
                    exit_price = pos['sl_price']
                elif low <= pos['tp_price']:
                    hit_tp = True
                    exit_price = pos['tp_price']
            
            if hit_tp or hit_sl:
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
                pos['status'] = "HIT_TP" if hit_tp else "HIT_SL"
                pos['balance_after'] = balance
                trade_history.append(pos)
            else:
                # Time exit (24 bars max limit)
                if (ts - pos['entry_time']).total_seconds() / 3600 >= 24:
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
            
            # Predict
            probs_dir = model_dir.predict_proba(X_test) # shape: (n_samples, 3) [0=Short, 1=Flat, 2=Long]
            pred_tp = model_tp.predict(X_test) # % olarak up
            pred_sl = model_sl.predict(X_test) # % olarak down (pozitif sayılar)
            
            candidates = []
            for i, row in group.reset_index(drop=True).iterrows():
                sym = row['symbol']
                if any(p['symbol'] == sym for p in open_positions):
                    continue
                    
                prob_short = probs_dir[i][0]
                prob_long = probs_dir[i][2]
                
                tp_pct = pred_tp[i]
                sl_pct = pred_sl[i]
                
                # LONG Şartı
                if prob_long > 0.55 and tp_pct > (1.5 * sl_pct) and tp_pct > 1.5:
                    candidates.append((sym, row, prob_long, 'LONG', tp_pct, sl_pct))
                    
                # SHORT Şartı (Düşüş ihtimali > %55, Düşüş Marjı > 1.5 * Yükseliş Marjı)
                elif prob_short > 0.55 and sl_pct > (1.5 * tp_pct) and sl_pct > 1.5:
                    candidates.append((sym, row, prob_short, 'SHORT', sl_pct, tp_pct))
                    
            if candidates:
                # Olasılığı ve Risk/Ödül oranı en yüksek olanı seç
                # R:R = Potential Profit / Potential Loss
                candidates.sort(key=lambda x: x[2] * (x[4] / (x[5]+1e-5)), reverse=True)
                best = candidates[0]
                
                sym = best[0]
                row = best[1]
                prob = best[2]
                direction = best[3]
                pred_profit_pct = best[4]
                pred_loss_pct = best[5]
                
                entry_price = row['close']
                
                if direction == 'LONG':
                    tp_price = entry_price * (1 + (pred_profit_pct / 100))
                    sl_price = entry_price * (1 - (pred_loss_pct / 100))
                else: # SHORT
                    # Short için profit, fiyatın düşmesidir (pred_profit_pct = target_max_down)
                    tp_price = entry_price * (1 - (pred_profit_pct / 100))
                    sl_price = entry_price * (1 + (pred_loss_pct / 100))
                
                # Kelly (Max %20 risk)
                risk_pct = min(0.20, max(0.01, (prob - 0.50) * 0.50))
                risk_usd = balance * risk_pct
                
                sl_distance_pct = abs(entry_price - sl_price) / entry_price
                if sl_distance_pct < 0.005: # Çok dar stopları engelle
                    sl_distance_pct = 0.005
                    
                position_size = risk_usd / sl_distance_pct
                
                max_pos_size = balance * 10
                current_exposure = sum(p['position_size'] for p in open_positions)
                
                if current_exposure + position_size <= max_pos_size:
                    open_positions.append({
                        'symbol': sym,
                        'direction': direction,
                        'entry_time': ts,
                        'entry_price': entry_price,
                        'sl_price': sl_price,
                        'tp_price': tp_price,
                        'position_size': position_size,
                        'risk_usd': risk_usd,
                        'win_prob': prob,
                        'risk_pct': risk_pct
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
    
    print("\nSimülasyon Tamamlandı. V33 Omniscient (Long/Short) Rapor Oluşturuluyor...\n")
    
    if len(trades_df) == 0:
         print("Sistem hiç işlem açmadı!")
         return
         
    trades_df['exit_time'] = pd.to_datetime(trades_df['exit_time'])
    trades_df['week'] = ((trades_df['exit_time'] - split_date).dt.days // 7) + 1
    
    weekly_summary = []
    
    for week_num, group in trades_df.groupby('week'):
        num_trades = len(group)
        num_longs = len(group[group['direction'] == 'LONG'])
        num_shorts = len(group[group['direction'] == 'SHORT'])
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
            
        start_date = group['exit_time'].min().strftime('%m-%d')
        end_date = group['exit_time'].max().strftime('%m-%d')
        
        weekly_summary.append({
            'Hft': int(week_num),
            'Tarih': f"{start_date}/{end_date}",
            'İşlem': num_trades,
            'L/S': f"{num_longs}/{num_shorts}",
            'K/Z ($)': round(weekly_pnl, 2),
            'Getiri (%)': round(weekly_ret, 2),
            'Kasa ($)': round(end_balance, 2)
        })
        
    weekly_df = pd.DataFrame(weekly_summary)
    print(weekly_df.to_string(index=False))
    
    print("\n--- V33 HER ŞEYİ BİLEN YAPAY ZEKA ÖZETİ (1 YIL OOS) ---")
    print(f"Toplam İşlem: {len(trades_df)} (Long: {len(trades_df[trades_df['direction'] == 'LONG'])}, Short: {len(trades_df[trades_df['direction'] == 'SHORT'])})")
    wins = len(trades_df[trades_df['pnl_usd'] > 0])
    print(f"Kazanma Oranı: %{wins/len(trades_df)*100:.1f}")
    print(f"Başlangıç: $100.00")
    print(f"Bitiş: ${balance:.2f}")

if __name__ == "__main__":
    run_v33_omniscient()
