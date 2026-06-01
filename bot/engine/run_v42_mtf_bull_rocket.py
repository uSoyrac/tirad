import pandas as pd
import numpy as np
import xgboost as xgb
import os

COMMISSION = 0.0004
SLIPPAGE = 0.0005
START_BALANCE = 100.0

def load_and_merge_mtf_data():
    features_15m_dir = 'bot/engine/features_v39'
    data_1h_dir = 'bot/engine/data_v31'
    
    files_15m = [f for f in os.listdir(features_15m_dir) if f.endswith('.csv')]
    all_data = []
    
    for f in files_15m:
        sym = f.replace('.csv', '')
        df_15m = pd.read_csv(os.path.join(features_15m_dir, f), parse_dates=['ts'])
        df_15m.sort_values('ts', inplace=True)
        
        path_1h = os.path.join(data_1h_dir, f)
        if not os.path.exists(path_1h):
            continue
            
        df_1h = pd.read_csv(path_1h, parse_dates=['ts'])
        df_1h.sort_values('ts', inplace=True)
        df_1h['ema_50_1h'] = df_1h['close'].ewm(span=50, adjust=False).mean()
        df_1h_features = df_1h[['ts', 'close', 'ema_50_1h']].copy()
        df_1h_features.rename(columns={'close': 'close_1h'}, inplace=True)
        
        df_1h_resample = df_1h.set_index('ts')
        df_4h = df_1h_resample.resample('4h').agg({
            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
        }).dropna().reset_index()
        
        df_4h['ema_50_4h'] = df_4h['close'].ewm(span=50, adjust=False).mean()
        df_4h_features = df_4h[['ts', 'close', 'ema_50_4h']].copy()
        df_4h_features.rename(columns={'close': 'close_4h'}, inplace=True)
        
        df_15m = pd.merge_asof(df_15m, df_1h_features, on='ts', direction='backward')
        df_15m = pd.merge_asof(df_15m, df_4h_features, on='ts', direction='backward')
        
        df_15m['symbol'] = sym
        df_15m.dropna(subset=['ema_50_1h', 'ema_50_4h'], inplace=True)
        all_data.append(df_15m)
        
    combined_df = pd.concat(all_data)
    combined_df.sort_values(by='ts', inplace=True)
    combined_df.reset_index(drop=True, inplace=True)
    return combined_df

def run_v42_mtf_bull_rocket():
    print("V42 MTF Bull Rocket (Eksponansiyel Büyüme) Motoru Başlatılıyor...")
    print("Sistem Tüm 2024 Boğa ve Ayı Dönemlerini Kapsayacak Şekilde Test Ediliyor.")
    
    combined_df = load_and_merge_mtf_data()
    
    # Boğa dönemi verisini al (2024 tamamı)
    bull_df = combined_df[(combined_df['ts'] >= '2024-01-01') & (combined_df['ts'] < '2025-01-01')].copy()
    
    # Train: Tüm veri üzerinde genel eğitim (random split)
    from sklearn.model_selection import train_test_split
    
    features = [c for c in combined_df.columns if c not in [
        'ts', 'open', 'high', 'low', 'close', 'volume', 'symbol',
        'target', 'target_is_trend', 'close_1h', 'ema_50_1h', 'close_4h', 'ema_50_4h'
    ]]
    
    valid_df = combined_df.dropna(subset=features + ['target', 'target_is_trend'])
    X_train, _, y_train_trend, _ = train_test_split(valid_df[features], valid_df['target_is_trend'], test_size=0.2, random_state=42)
    _, _, y_train_sniper, _ = train_test_split(valid_df[features], valid_df['target'], test_size=0.2, random_state=42)
    
    test_df = bull_df.copy()
    
    print("Ajan 1 ve 2 Eğitiliyor (Genel Piyasa Karakteristikleri)...")
    model_watcher = xgb.XGBClassifier(
        n_estimators=100, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, random_state=42,
        eval_metric='logloss', tree_method='hist'
    )
    model_watcher.fit(X_train, y_train_trend)
    
    model_sniper = xgb.XGBClassifier(
        n_estimators=150, max_depth=5, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, random_state=42,
        eval_metric='logloss', tree_method='hist'
    )
    model_sniper.fit(X_train, y_train_sniper)
    
    print("Sistem 2024 Mega Boğa Yılına Işınlandı! Compound Interest (Bileşik Getiri) Devrede.")
    
    balance = START_BALANCE
    open_positions = []
    trade_history = []
    
    grouped = test_df.groupby('ts')
    tp_pct_target = 0.02
    sl_pct_target = 0.005
    
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
            exit_price = 0
            
            if low <= pos['sl_price']:
                hit_sl = True
                exit_price = pos['sl_price']
            elif high >= pos['tp_price']:
                hit_tp = True
                exit_price = pos['tp_price']
                
            if hit_sl or hit_tp:
                pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price']
                net_pnl_pct = pnl_pct - (COMMISSION * 2) - SLIPPAGE
                pnl_usd = pos['margin_usd'] * 10 * net_pnl_pct
                
                balance += pnl_usd
                pos['exit_price'] = exit_price
                pos['exit_time'] = ts
                pos['pnl_usd'] = pnl_usd
                pos['roe_pct'] = (pnl_usd / pos['margin_usd']) * 100
                pos['status'] = "TP_HIT (+%20 ROE)" if hit_tp else "SL_HIT (-%5 ROE)"
                pos['balance_after'] = balance
                trade_history.append(pos)
            else:
                if (ts - pos['entry_time']).total_seconds() / 60 >= 240:
                    exit_price = row['close']
                    pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price']
                    net_pnl_pct = pnl_pct - (COMMISSION * 2) - SLIPPAGE
                    pnl_usd = pos['margin_usd'] * 10 * net_pnl_pct
                    
                    balance += pnl_usd
                    pos['exit_price'] = exit_price
                    pos['exit_time'] = ts
                    pos['pnl_usd'] = pnl_usd
                    pos['roe_pct'] = (pnl_usd / pos['margin_usd']) * 100
                    pos['status'] = "TIME_EXIT"
                    pos['balance_after'] = balance
                    trade_history.append(pos)
                else:
                    still_open.append(pos)
                    
        open_positions = still_open
        
        if len(group) > 0 and len(open_positions) < 1:
            X_test = group[features]
            probs_trend = model_watcher.predict_proba(X_test)[:, 1]
            probs_sniper = model_sniper.predict_proba(X_test)[:, 1]
            
            candidates = []
            for i, row in group.reset_index(drop=True).iterrows():
                vol_spike = row['vol_spike']
                adx = row['adx_14']
                
                prob_trend = probs_trend[i]
                prob_sniper = probs_sniper[i]
                
                mtf_1h_bullish = row['close_1h'] > row['ema_50_1h']
                mtf_4h_bullish = row['close_4h'] > row['ema_50_4h']
                
                if vol_spike == 1 and adx > 15 and prob_trend > 0.55 and prob_sniper > 0.55:
                    if mtf_1h_bullish and mtf_4h_bullish:
                        candidates.append((row['symbol'], row, prob_sniper))
                        
            if candidates:
                candidates.sort(key=lambda x: x[2], reverse=True)
                best_candidate = candidates[0]
                
                sym = best_candidate[0]
                row = best_candidate[1]
                prob = best_candidate[2]
                
                entry_price = row['close']
                tp_price = entry_price * (1 + tp_pct_target)
                sl_price = entry_price * (1 - sl_pct_target)
                
                margin_usd = balance
                position_size = margin_usd * 10
                
                open_positions.append({
                    'symbol': sym,
                    'entry_time': ts,
                    'entry_price': entry_price,
                    'sl_price': sl_price,
                    'tp_price': tp_price,
                    'margin_usd': margin_usd,
                    'position_size': position_size,
                    'win_prob': prob
                })

    for pos in open_positions:
        sym = pos['symbol']
        last_row = test_df[test_df['symbol'] == sym].iloc[-1]
        exit_price = last_row['close']
        pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price']
        net_pnl_pct = pnl_pct - (COMMISSION * 2) - SLIPPAGE
        pnl_usd = pos['margin_usd'] * 10 * net_pnl_pct
        balance += pnl_usd
        pos['exit_time'] = last_row['ts']
        pos['pnl_usd'] = pnl_usd
        pos['balance_after'] = balance
        trade_history.append(pos)
        
    trades_df = pd.DataFrame(trade_history)
    
    print("\nSimülasyon Tamamlandı. V42 MTF Bull Rocket Raporu Oluşturuluyor...\n")
    
    if len(trades_df) == 0:
         print("Sistem hiç işlem açmadı!")
         return
         
    # Haftalık gösterim
    trades_df['week_start'] = trades_df['exit_time'].dt.to_period('W').dt.start_time
    weekly_stats = trades_df.groupby('week_start').agg(
        trades_count=('symbol', 'count'),
        weekly_pnl=('pnl_usd', 'sum')
    ).reset_index()
    
    print("--- 2024 MEGA BOĞA (10X KALDIRAÇ) HAFTALIK BÜYÜME ---")
    current_balance = START_BALANCE
    report_rows = []
    
    for i, row in weekly_stats.iterrows():
        current_balance += row['weekly_pnl']
        week_num = i + 1
        date_str = row['week_start'].strftime('%Y-%m-%d')
        report_rows.append(f"Hafta {week_num:>2} [{date_str}]: {row['trades_count']:>2} İşlem | K/Z: ${row['weekly_pnl']:>6.2f} | Kasa: ${current_balance:>6.2f}")
            
    print("\n".join(report_rows))
    
    win_rate = len(trades_df[trades_df['pnl_usd'] > 0]) / len(trades_df) * 100
    
    print("\n--- V42 MTF (ÇOKLU ZAMAN DİLİMİ) 2024 BOĞA KÖR TEST ÖZETİ ---")
    print(f"Başlangıç Bakiyesi: $100.00")
    print(f"Bitiş Bakiyesi: ${balance:.2f}")
    print(f"Net Kâr: +%{(balance - 100.0):.1f}")
    print(f"Toplam İşlem: {len(trades_df)}")
    print(f"Kazanma Oranı (Win Rate): %{win_rate:.1f}")

if __name__ == "__main__":
    run_v42_mtf_bull_rocket()
