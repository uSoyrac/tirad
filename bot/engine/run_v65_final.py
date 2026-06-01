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

# 6-AYLIK "FLY" MODU İÇİN OPTİMİZE EDİLMİŞ AYARLAR
NORMAL_BET_FRACTION = 0.35
RECOVERY_BET_FRACTION = 0.70
OPTIMAL_THRESHOLD = 0.68
RECOVERY_THRESHOLD = 0.73

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

def run_v65_final_6_months():
    print("🌟 V65 TOP-5 COIN: 6-AYLIK UÇUŞ (FLY) SİMÜLASYONU BAŞLIYOR...")
    
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
    
    # 2026 öncesini eğit
    train_df = valid_df[valid_df['ts'] < '2026-01-01']
    # Sadece 2026'nın ilk 6 ayını test et (Ocak - Haziran 2026)
    test_df = valid_df[valid_df['ts'] >= '2026-01-01']
    
    target_count = train_df['target'].sum()
    total_count = len(train_df)
    scale_pos = (total_count - target_count) / target_count
    
    X_train = train_df[features]
    y_train = train_df['target']
    
    print("Yapay Zeka Tüm Geçmiş Veriyle (Top 5 Coin) Eğitiliyor...")
    model_ai = xgb.XGBClassifier(
        n_estimators=400, max_depth=7, learning_rate=0.02, 
        subsample=0.8, colsample_bytree=0.8, random_state=42, 
        eval_metric='logloss', tree_method='hist',
        scale_pos_weight=scale_pos
    )
    model_ai.fit(X_train, y_train)
    
    print("Son 6 ay (2026 Ocak - 2026 Haziran) OOS Kör Test Hesaplanıyor...")
    test_features = test_df[features].fillna(0)
    ai_probs = model_ai.predict_proba(test_features)[:, 1]
    
    test_df = test_df.copy()
    test_df['ai_prob'] = ai_probs
    
    test_df['macro_ok'] = (
        (test_df['supertrend_dir'] == 1) & 
        (test_df['macd_diff'] > 0) &
        (test_df['close_1h'] > test_df['ema_50_1h'])
    )
    
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
                pos['status'] = "TP" if (hit_tp and not hit_sl) else "SL"
                pos['balance_after'] = balance
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
                    pos['status'] = "TIME_OUT"
                    pos['balance_after'] = balance
                    
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
                    'margin_usd': margin_usd,
                    'bet_mode': "RECOVERY" if in_recovery_mode else "NORMAL"
                })

    for pos in open_positions:
        sym = pos['symbol']
        last_row = test_df[test_df['symbol'] == sym].iloc[-1]
        exit_price = last_row['close']
        pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price']
        net_pnl_pct = pnl_pct - (ENTRY_FEE + SL_FEE)
        pnl_usd = pos['margin_usd'] * LEVERAGE * net_pnl_pct
        balance += pnl_usd
        pos['pnl_usd'] = pnl_usd
        pos['status'] = "FORCE_CLOSE"
        pos['balance_after'] = balance
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
    
    print("\n--- V65 TOP-5 COIN: 6 AYLIK UÇUŞ (FLY) RAPORU ---")
    current_balance = START_BALANCE
    report_rows = []
    for i, row in weekly_stats.iterrows():
        current_balance += row['weekly_pnl']
        week_num = i + 1
        date_str = row['week_start'].strftime('%Y-%m-%d')
        report_rows.append(f"Hafta {week_num:>2} [{date_str}]: {row['trades_count']:>2} İşlem | K/Z: ${row['weekly_pnl']:>8.2f} | Kasa: ${current_balance:>10.2f}")
    print("\n".join(report_rows))
    
    win_rate = len(trades_df[trades_df['pnl_usd'] > 0]) / len(trades_df) * 100
    
    print(f"\n🏆 V65 'UÇUŞ' MODU (6-AYLIK) ÖZETİ 🏆")
    print(f"Pariteler: BTC, ETH, SOL, BNB, XRP")
    print(f"Normal Risk: %{NORMAL_BET_FRACTION*100} (Threshold: {OPTIMAL_THRESHOLD})")
    print(f"Recovery Risk: %{RECOVERY_BET_FRACTION*100} (Threshold: {RECOVERY_THRESHOLD})")
    print(f"Başlangıç Bakiyesi: ${START_BALANCE:.2f}")
    print(f"Bitiş Bakiyesi: ${balance:.2f} (x{balance/START_BALANCE:.2f} KATLAMA)")
    print(f"Toplam İşlem: {len(trades_df)} (6 ayda)")
    print(f"Kazanma Oranı (Win Rate): %{win_rate:.1f}")

if __name__ == "__main__":
    run_v65_final_6_months()
