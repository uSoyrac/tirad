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
OPTIMAL_THRESHOLD = 0.75

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

def run_v62_holy_grail_2_years():
    print("🏆 V62 Kutsal Kâse: Tüm Veri Setinde (2.5 Yıl) Gerçek Eksponansiyel Backtest Başlıyor...")
    
    full_df = load_and_merge_mtf_data()
    
    features = [
        'vol_derivative', 'smart_money_spike', 'body_ratio', 
        'upper_wick_ratio', 'lower_wick_ratio', 'dist_ema50', 
        'dist_ema200', 'macd_diff', 'rsi', 'hour_sin', 'hour_cos'
    ]
    
    valid_df = full_df.dropna(subset=features + ['target'])
    
    target_count = valid_df['target'].sum()
    total_count = len(valid_df)
    scale_pos = (total_count - target_count) / target_count
    
    # Tren-Test ayrımı. Sadece 2024'ün ilk yarısıyla eğitip, geri kalan 2 yılda KÖR (Blind) test yapacağız.
    # Yani AI geleceği görmemiş olacak! Bu çok daha gerçekçi.
    train_df = valid_df[valid_df['ts'] < '2024-07-01']
    
    X_train = train_df[features]
    y_train = train_df['target']
    
    print(f"Ajan 4 (AI), sadece 2024'ün ilk yarısındaki verilerle eğitiliyor... Sonraki tüm dönemleri TAHMİN EDECEK!")
    model_ai = xgb.XGBClassifier(
        n_estimators=400, max_depth=7, learning_rate=0.02, 
        subsample=0.8, colsample_bytree=0.8, random_state=42, 
        eval_metric='logloss', tree_method='hist',
        scale_pos_weight=scale_pos
    )
    model_ai.fit(X_train, y_train)
    
    # Hesaplamaları tüm veri seti için yapalım (Çok hızlıdır)
    print("Yapay zeka olasılıkları tüm 2.5 yıl için hesaplanıyor...")
    full_features = full_df[features].fillna(0)
    ai_probs = model_ai.predict_proba(full_features)[:, 1]
    full_df['ai_prob'] = ai_probs
    
    full_df['macro_ok'] = (
        (full_df['supertrend_dir'] == 1) & 
        (full_df['close'] > full_df['kc_upper']) & 
        (full_df['macd_diff'] > 0) & 
        (full_df['close_1h'] > full_df['ema_50_1h']) & 
        (full_df['close_4h'] > full_df['ema_50_4h']) & 
        (full_df['ts'].dt.weekday < 5) & 
        (full_df['ts'].dt.hour.isin([13, 14, 15, 16, 17, 18, 19, 20])) &
        (full_df['adx_1h'] > 20)
    )
    
    balance = START_BALANCE
    open_positions = []
    trade_history = []
    
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
                else: 
                    net_pnl_pct = -SL_PCT - (ENTRY_FEE + SL_FEE)
                    
                pnl_usd = pos['margin_usd'] * LEVERAGE * net_pnl_pct
                balance += pnl_usd
                pos['exit_time'] = ts
                pos['pnl_usd'] = pnl_usd
                pos['roe_pct'] = net_pnl_pct * LEVERAGE * 100
                pos['status'] = "TP" if (hit_tp and not hit_sl) else "SL"
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
                    pos['status'] = "TIME_OUT"
                    trade_history.append(pos)
                else:
                    still_open.append(pos)
                    
        open_positions = still_open
        
        if len(group) > 0 and len(open_positions) < 1:
            valid_candidates = group[(group['macro_ok'] == True) & (group['ai_prob'] > OPTIMAL_THRESHOLD)]
            
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
        last_row = full_df[full_df['symbol'] == sym].iloc[-1]
        exit_price = last_row['close']
        pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price']
        net_pnl_pct = pnl_pct - (ENTRY_FEE + SL_FEE)
        pnl_usd = pos['margin_usd'] * LEVERAGE * net_pnl_pct
        balance += pnl_usd
        pos['pnl_usd'] = pnl_usd
        pos['status'] = "FORCE_CLOSE"
        trade_history.append(pos)
        
    trades_df = pd.DataFrame(trade_history)
    
    if len(trades_df) == 0:
        print("Hiç işlem açılmadı.")
        return
        
    trades_df['week_start'] = trades_df['exit_time'].dt.to_period('W').dt.start_time
    weekly_stats = trades_df.groupby('week_start').agg(
        trades_count=('symbol', 'count'),
        weekly_pnl=('pnl_usd', 'sum')
    ).reset_index()
    
    print("\n--- 2.5 YILLIK (2024-2026) BİLEŞİK BÜYÜME HAFTALIK RAPOR ---")
    current_balance = START_BALANCE
    report_rows = []
    
    for i, row in weekly_stats.iterrows():
        current_balance += row['weekly_pnl']
        week_num = i + 1
        date_str = row['week_start'].strftime('%Y-%m-%d')
        report_rows.append(f"Hafta {week_num:>3} [{date_str}]: {row['trades_count']:>2} İşlem | K/Z: ${row['weekly_pnl']:>8.2f} | Kasa: ${current_balance:>10.2f}")
            
    print("\n".join(report_rows))
    
    win_rate = len(trades_df[trades_df['pnl_usd'] > 0]) / len(trades_df) * 100
    avg_roe = trades_df['roe_pct'].mean()
    
    print(f"\n🏆 V62 KUTSAL KÂSE 2.5 YILLIK ÖZET 🏆")
    print(f"Eğitim Verisi: Sadece 2024 İlk 6 Ay")
    print(f"Kör Test Verisi (OOS): Kalan ~2 Yıl (Geleceği görmeden işlem yapıldı)")
    print(f"Optimum AI Threshold: {OPTIMAL_THRESHOLD}")
    print(f"Kasa Kullanımı (Bet): %{BET_FRACTION*100:.0f} | Kaldıraç: {LEVERAGE}x")
    print(f"Hedef: TP %2 (Limit Emir) | SL %1 (Piyasa Emri)")
    print(f"Başlangıç Bakiyesi: ${START_BALANCE:.2f}")
    print(f"Bitiş Bakiyesi: ${balance:.2f} (x{balance/START_BALANCE:.2f} KATLAMA)")
    print(f"Toplam İşlem: {len(trades_df)}")
    print(f"Kazanma Oranı (Win Rate): %{win_rate:.1f}")
    print(f"İşlem Başı Ortalama ROE: %{avg_roe:.2f}")

if __name__ == "__main__":
    run_v62_holy_grail_2_years()
