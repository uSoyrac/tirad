import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split
import os
import ta

ENTRY_FEE = 0.0009
TP_FEE = 0.0001
SL_FEE = 0.0009

START_BALANCE = 100.0
LEVERAGE = 10
BET_FRACTION = 0.20
TP_PCT = 0.020
SL_PCT = 0.010

def load_and_merge_mtf_data():
    features_15m_dir = 'bot/engine/features_v62'
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
        
        # 1H ADX Hesaplama (Makro Filtre için)
        adx_ind = ta.trend.ADXIndicator(df_1h['high'], df_1h['low'], df_1h['close'], window=14)
        df_1h['adx_1h'] = adx_ind.adx()
        df_1h['ema_50_1h'] = df_1h['close'].ewm(span=50, adjust=False).mean()
        
        df_1h_features = df_1h[['ts', 'close', 'ema_50_1h', 'adx_1h']].copy()
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
        df_15m.dropna(subset=['ema_50_1h', 'ema_50_4h', 'adx_1h'], inplace=True)
        all_data.append(df_15m)
        
    combined_df = pd.concat(all_data)
    combined_df.sort_values(by='ts', inplace=True)
    combined_df.reset_index(drop=True, inplace=True)
    return combined_df

def run_v62_holy_grail():
    print("🏆 V62 Kutsal Kâse: Eksponansiyel Optimizasyon Motoru Başlıyor...")
    print("Filtre: 1H ADX > 20 (Ölü piyasalarda işlem açmak YASAK)")
    
    combined_df = load_and_merge_mtf_data()
    bull_df = combined_df[(combined_df['ts'] >= '2024-01-01') & (combined_df['ts'] < '2025-01-01')].copy()
    
    features = [
        'vol_derivative', 'smart_money_spike', 'body_ratio', 
        'upper_wick_ratio', 'lower_wick_ratio', 'dist_ema50', 
        'dist_ema200', 'macd_diff', 'rsi', 'hour_sin', 'hour_cos'
    ]
    
    valid_df = combined_df.dropna(subset=features + ['target'])
    
    target_count = valid_df['target'].sum()
    total_count = len(valid_df)
    scale_pos = (total_count - target_count) / target_count
    
    X_train, _, y_train, _ = train_test_split(valid_df[features], valid_df['target'], test_size=0.2, random_state=42)
    
    print(f"Ajan 4 (Yapay Zeka Dedektifi) Dev Trendleri Öğreniyor...")
    model_ai = xgb.XGBClassifier(
        n_estimators=400, max_depth=7, learning_rate=0.02, 
        subsample=0.8, colsample_bytree=0.8, random_state=42, 
        eval_metric='logloss', tree_method='hist',
        scale_pos_weight=scale_pos
    )
    model_ai.fit(X_train, y_train)
    
    print("\n--- AI THRESHOLD (EŞİK) GRID SEARCH BAŞLIYOR ---")
    thresholds = [0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85]
    best_balance = 0
    best_threshold = 0
    best_trades_df = None
    
    # Pre-calculate AI probabilities for the whole bull_df to save immense time
    print("Tüm 2024 boğası için yapay zeka olasılıkları hesaplanıyor...")
    bull_features = bull_df[features]
    # Check for NaNs
    bull_features = bull_features.fillna(0)
    ai_probs = model_ai.predict_proba(bull_features)[:, 1]
    bull_df['ai_prob'] = ai_probs
    
    # Pre-filter macro logic to save time
    bull_df['macro_ok'] = (
        (bull_df['supertrend_dir'] == 1) & 
        (bull_df['close'] > bull_df['kc_upper']) & 
        (bull_df['macd_diff'] > 0) & 
        (bull_df['close_1h'] > bull_df['ema_50_1h']) & 
        (bull_df['close_4h'] > bull_df['ema_50_4h']) & 
        (bull_df['ts'].dt.weekday < 5) & 
        (bull_df['ts'].dt.hour.isin([13, 14, 15, 16, 17, 18, 19, 20])) &
        (bull_df['adx_1h'] > 20) # YENİ MAKRO FİLTRE
    )
    
    for thresh in thresholds:
        balance = START_BALANCE
        open_positions = []
        trade_history = []
        
        grouped = bull_df.groupby('ts')
        
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
                    else: 
                        net_pnl_pct = -SL_PCT - (ENTRY_FEE + SL_FEE)
                        
                    pnl_usd = pos['margin_usd'] * LEVERAGE * net_pnl_pct
                    balance += pnl_usd
                    pos['exit_time'] = ts
                    pos['pnl_usd'] = pnl_usd
                    pos['roe_pct'] = net_pnl_pct * LEVERAGE * 100
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
                        pos['roe_pct'] = net_pnl_pct * LEVERAGE * 100
                        trade_history.append(pos)
                    else:
                        still_open.append(pos)
                        
            open_positions = still_open
            
            if len(group) > 0 and len(open_positions) < 1:
                # Find valid candidates
                valid_candidates = group[(group['macro_ok'] == True) & (group['ai_prob'] > thresh)]
                
                if len(valid_candidates) > 0:
                    best_candidate = valid_candidates.sort_values(by='ai_prob', ascending=False).iloc[0]
                    
                    entry_price = best_candidate['close']
                    margin_usd = balance * BET_FRACTION 
                    
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
            last_row = bull_df[bull_df['symbol'] == sym].iloc[-1]
            exit_price = last_row['close']
            pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price']
            net_pnl_pct = pnl_pct - (ENTRY_FEE + SL_FEE)
            pnl_usd = pos['margin_usd'] * LEVERAGE * net_pnl_pct
            balance += pnl_usd
            pos['pnl_usd'] = pnl_usd
            trade_history.append(pos)
            
        trades_df = pd.DataFrame(trade_history)
        win_rate = 0
        if len(trades_df) > 0:
            win_rate = len(trades_df[trades_df['pnl_usd'] > 0]) / len(trades_df) * 100
            
        print(f"[Threshold {thresh:.2f}] İşlem: {len(trades_df):>4} | Kasa: ${balance:>8.2f} | Win-Rate: %{win_rate:.1f}")
        
        if balance > best_balance:
            best_balance = balance
            best_threshold = thresh
            best_trades_df = trades_df

    print(f"\n🏆 KUTSAL KÂSE BULUNDU! Optimal Threshold: {best_threshold:.2f}")
    
    if len(best_trades_df) == 0:
        print("Hiç işlem açılmadı.")
        return
        
    best_trades_df['week_start'] = best_trades_df['exit_time'].dt.to_period('W').dt.start_time
    weekly_stats = best_trades_df.groupby('week_start').agg(
        trades_count=('symbol', 'count'),
        weekly_pnl=('pnl_usd', 'sum')
    ).reset_index()
    
    print("--- 2024 MEGA BOĞA (10X KALDIRAÇ) HAFTALIK BİLEŞİK BÜYÜME (COMPOUND) ---")
    current_balance = START_BALANCE
    report_rows = []
    
    for i, row in weekly_stats.iterrows():
        current_balance += row['weekly_pnl']
        week_num = i + 1
        date_str = row['week_start'].strftime('%Y-%m-%d')
        report_rows.append(f"Hafta {week_num:>2} [{date_str}]: {row['trades_count']:>2} İşlem | K/Z: ${row['weekly_pnl']:>8.2f} | Kasa: ${current_balance:>10.2f}")
            
    print("\n".join(report_rows))
    
    win_rate = len(best_trades_df[best_trades_df['pnl_usd'] > 0]) / len(best_trades_df) * 100
    avg_roe = best_trades_df['roe_pct'].mean()
    
    print(f"\n--- V62 KUTSAL KÂSE ÖZETİ ---")
    print(f"Optimum AI Threshold: {best_threshold:.2f}")
    print(f"ADX Trend Filtresi: 1H ADX > 20")
    print(f"Kasa Kullanımı (Bet): %{BET_FRACTION*100:.0f} (Kasanın %20'si riske edilir)")
    print(f"Hedeflenen Kaldıraç: {LEVERAGE}x")
    print(f"Başlangıç Bakiyesi: $100.00")
    print(f"Bitiş Bakiyesi: ${best_balance:.2f} (x{best_balance/100:.2f} KATLAMA)")
    print(f"Net Kâr: +%{(best_balance - 100.0):.1f}")
    print(f"Toplam İşlem: {len(best_trades_df)}")
    print(f"Kazanma Oranı (Win Rate): %{win_rate:.1f}")
    print(f"İşlem Başı Ortalama ROE: %{avg_roe:.2f}")

if __name__ == "__main__":
    run_v62_holy_grail()
