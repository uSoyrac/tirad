import pandas as pd
import numpy as np
import xgboost as xgb
import os

ENTRY_FEE = 0.0009
TP_FEE = 0.0001
SL_FEE = 0.0009

START_BALANCE = 100.0
LEVERAGE = 10
TP_PCT = 0.050  # Kullanıcının talebi: %5 Take Profit
SL_PCT = 0.050  # Kullanıcının talebi: %5 Stop Loss

BASE_BET_FRACTION = 0.10 # Başlangıçta kasanın %10'u
MARTINGALE_MULTIPLIER = 2.0 # Zarar edilirse beti 2'ye katla
MAX_BET_FRACTION = 0.80 # Kasanın %80'inden fazlasını tek işleme basma

OPTIMAL_THRESHOLD = 0.70

def apply_dynamic_targets(df, horizon=192, tp_pct=0.050, sl_pct=0.050):
    df = df.copy()
    targets = np.zeros(len(df))
    close_prices = df['close'].values
    high_prices = df['high'].values
    low_prices = df['low'].values
    
    for i in range(len(df) - horizon):
        entry_price = close_prices[i]
        if pd.isna(entry_price):
            continue
            
        tp_price = entry_price * (1 + tp_pct)
        sl_price = entry_price * (1 - sl_pct)
        
        hit_tp = False
        hit_sl = False
        
        for j in range(1, horizon + 1):
            if low_prices[i + j] <= sl_price:
                hit_sl = True
                break
            if high_prices[i + j] >= tp_price:
                hit_tp = True
                break
                
        if hit_tp and not hit_sl:
            targets[i] = 1
            
    df['target_5_5'] = targets
    df.loc[df.index[-horizon:], 'target_5_5'] = np.nan
    return df

def run_v63_martingale():
    print(f"💣 V63-MARTINGALE: %{TP_PCT*100} TP / %{SL_PCT*100} SL & KATLAMALI BAHİS BAŞLIYOR...")
    
    features_dir = 'bot/engine/features_v63'
    files = ['BTC_USDT.csv', 'ETH_USDT.csv', 'SOL_USDT.csv']
    
    all_data = []
    for f in files:
        sym = f.replace('.csv', '')
        path = os.path.join(features_dir, f)
        if not os.path.exists(path):
            continue
        df = pd.read_csv(path, parse_dates=['ts'])
        # 192 Mum (48 Saat) ufuk çizgisi
        df = apply_dynamic_targets(df, horizon=192, tp_pct=TP_PCT, sl_pct=SL_PCT)
        df['symbol'] = sym
        all_data.append(df)
        
    full_df = pd.concat(all_data)
    full_df.sort_values(by='ts', inplace=True)
    full_df.reset_index(drop=True, inplace=True)
    
    features = [
        'whale_anomaly', 'taker_buy_surge', 'trade_size', 'taker_buy_ratio',
        'dist_ema50', 'macd_diff', 'rsi', 'hour_sin', 'hour_cos'
    ]
    
    valid_df = full_df.dropna(subset=features + ['target_5_5'])
    train_df = valid_df[valid_df['ts'] < '2024-07-01']
    test_df = valid_df[valid_df['ts'] >= '2024-07-01']
    
    target_count = train_df['target_5_5'].sum()
    total_count = len(train_df)
    
    scale_pos = (total_count - target_count) / target_count
    print(f"Eğitim Verisi: {total_count} mum. {target_count} tanesi %5 TP'ye (Önce -%5'e düşmeden) ulaştı.")
    
    X_train = train_df[features]
    y_train = train_df['target_5_5']
    
    print("Yapay Zeka (AI) Eğitiliyor...")
    model_ai = xgb.XGBClassifier(
        n_estimators=400, max_depth=7, learning_rate=0.02, 
        subsample=0.8, colsample_bytree=0.8, random_state=42, 
        eval_metric='logloss', tree_method='hist',
        scale_pos_weight=scale_pos
    )
    model_ai.fit(X_train, y_train)
    
    print("2 Yıllık Kör Test (Martingale Simülasyonu) Hesaplanıyor...")
    test_features = test_df[features].fillna(0)
    ai_probs = model_ai.predict_proba(test_features)[:, 1]
    
    test_df = test_df.copy()
    test_df['ai_prob'] = ai_probs
    
    test_df['macro_ok'] = (
        (test_df['supertrend_dir'] == 1) & 
        (test_df['close'] > test_df['kc_upper']) & 
        (test_df['macd_diff'] > 0)
    )
    
    balance = START_BALANCE
    open_positions = []
    trade_history = []
    
    # MARTINGALE STATE
    current_bet_fraction = BASE_BET_FRACTION
    
    grouped = test_df.groupby('ts')
    
    for ts, group in grouped:
        if balance <= 5.0: # Kasa sıfırlandı sayılır
            break
            
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
                    # MARTINGALE RESET (Kazanıldı)
                    current_bet_fraction = BASE_BET_FRACTION
                else: 
                    net_pnl_pct = -SL_PCT - (ENTRY_FEE + SL_FEE)
                    # MARTINGALE MULTIPLY (Kaybedildi, beti ikiye katla)
                    current_bet_fraction = min(current_bet_fraction * MARTINGALE_MULTIPLIER, MAX_BET_FRACTION)
                    
                pnl_usd = pos['margin_usd'] * LEVERAGE * net_pnl_pct
                balance += pnl_usd
                pos['exit_time'] = ts
                pos['pnl_usd'] = pnl_usd
                pos['status'] = "TP" if (hit_tp and not hit_sl) else "SL"
                pos['balance_after'] = balance
                trade_history.append(pos)
            else:
                if (ts - pos['entry_time']).total_seconds() / 60 >= (15 * 192): # 48 Saat time-out
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
                        current_bet_fraction = min(current_bet_fraction * MARTINGALE_MULTIPLIER, MAX_BET_FRACTION)
                    else:
                        current_bet_fraction = BASE_BET_FRACTION
                        
                    trade_history.append(pos)
                else:
                    still_open.append(pos)
                    
        open_positions = still_open
        
        if len(group) > 0 and len(open_positions) < 1:
            valid_candidates = group[(group['macro_ok'] == True) & (group['ai_prob'] > OPTIMAL_THRESHOLD)]
            
            if len(valid_candidates) > 0:
                best_candidate = valid_candidates.sort_values(by='ai_prob', ascending=False).iloc[0]
                
                entry_price = best_candidate['close']
                margin_usd = balance * current_bet_fraction 
                
                open_positions.append({
                    'symbol': best_candidate['symbol'],
                    'entry_time': ts,
                    'entry_price': entry_price,
                    'sl_price': entry_price * (1 - SL_PCT),
                    'tp_price': entry_price * (1 + TP_PCT),
                    'margin_usd': margin_usd,
                    'bet_fraction_used': current_bet_fraction
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
        
    win_rate = len(trades_df[trades_df['pnl_usd'] > 0]) / len(trades_df) * 100
    
    print(f"\n💣 V63-MARTINGALE ÖZETİ (%{TP_PCT*100} TP / %{SL_PCT*100} SL) 💣")
    print(f"Başlangıç Bakiyesi: ${START_BALANCE:.2f}")
    print(f"Bitiş Bakiyesi: ${balance:.2f}")
    print(f"Toplam İşlem: {len(trades_df)}")
    print(f"Kazanma Oranı (Win Rate): %{win_rate:.1f}")
    print(f"\nÖrnek İşlemler (Martingale Katlamalarını İncele):")
    print(trades_df[['entry_time', 'symbol', 'status', 'bet_fraction_used', 'pnl_usd', 'balance_after']].head(15))

if __name__ == "__main__":
    run_v63_martingale()
