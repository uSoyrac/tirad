import pandas as pd
import numpy as np
import xgboost as xgb
import os
import json
from datetime import datetime, timedelta

COMMISSION = 0.0004  # 0.04% per trade
SLIPPAGE = 0.0005    # 0.05% slippage on exit
RISK_PER_TRADE = 0.02
START_BALANCE = 10000.0

def run_v27():
    features_dir = 'bot/engine/features_v27'
    files = [f for f in os.listdir(features_dir) if f.endswith('.csv')]
    
    all_data = []
    for f in files:
        df = pd.read_csv(os.path.join(features_dir, f), parse_dates=['ts'])
        df['symbol'] = f.replace('.csv', '')
        all_data.append(df)
        
    combined_df = pd.concat(all_data)
    combined_df.sort_values(by='ts', inplace=True)
    combined_df.reset_index(drop=True, inplace=True)
    
    # 9 Months Train, 3 Months Test (1H data: ~8760 candles per year, ~2190 per 3 months)
    split_date = combined_df['ts'].max() - timedelta(days=90)
    
    train_df = combined_df[combined_df['ts'] < split_date].copy()
    test_df = combined_df[combined_df['ts'] >= split_date].copy()
    
    print(f"V27 1H Train Set: {len(train_df)} samples")
    print(f"V27 1H Test Set: {len(test_df)} samples")
    
    # Train
    y_train = train_df['target'].astype(int)
    features = [c for c in train_df.columns if c not in ['target', 'open', 'high', 'low', 'close', 'volume', 'signed_volume', 'ts', 'symbol']]
    X_train = train_df[features]
    
    scale_pos_weight = len(y_train[y_train == 0]) / max(len(y_train[y_train == 1]), 1)
    
    model = xgb.XGBClassifier(
        objective='binary:logistic',
        n_estimators=200,
        learning_rate=0.05,
        max_depth=4,
        subsample=0.8,
        scale_pos_weight=scale_pos_weight,
        tree_method='hist'
    )
    
    print("V27 1H Eğitimi Başlıyor (High R:R)...")
    model.fit(X_train, y_train)
    model.save_model("bot/engine/v27_xgb_model.json")
    
    meta = {"features": features}
    with open("bot/engine/v27_xgb_meta.json", "w") as f:
        json.dump(meta, f)
        
    print("V27 Eğitimi Tamamlandı. Simülasyon Başlıyor...")
    
    # Backtest
    balance = START_BALANCE
    open_positions = []
    trade_history = []
    
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
            hit_tp = row['high'] >= pos['tp_price']
            hit_sl = row['low'] <= pos['sl_price']
            
            if hit_tp or hit_sl:
                if hit_tp and hit_sl:
                    exit_price = pos['sl_price']
                    status = "LOSS (Wick)"
                elif hit_tp:
                    exit_price = pos['tp_price']
                    status = "WIN"
                else:
                    exit_price = pos['sl_price']
                    status = "LOSS"
                    
                pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price']
                net_pnl_pct = pnl_pct - (COMMISSION * 2) - SLIPPAGE
                pnl_usd = pos['position_size'] * net_pnl_pct
                
                balance += pnl_usd
                pos['exit_price'] = exit_price
                pos['exit_time'] = ts
                pos['pnl_usd'] = pnl_usd
                pos['net_pnl_pct'] = net_pnl_pct
                pos['status'] = status
                pos['balance_after'] = balance
                trade_history.append(pos)
            else:
                if (ts - pos['entry_time']).total_seconds() / 3600 >= 36:
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
        
        X_test = group[features]
        probs = model.predict_proba(X_test)[:, 1]
        
        for i, row in group.iterrows():
            prob = probs[group.index.get_loc(i)]
            
            # Eşik Olasılığı: (Scale_pos_weight kullanıldığı için threshold genellikle 0.5'tir)
            if prob > 0.55: # Daha seçici bir threshold (3.5 ATR zor bir hedeftir)
                sym = row['symbol']
                
                if any(p['symbol'] == sym for p in open_positions):
                    continue
                    
                entry_price = row['close']
                atr = (row['atr_14_pct'] / 100) * entry_price
                
                tp_price = entry_price + (atr * 3.5) # YENİ HEDEF
                sl_price = entry_price - (atr * 1.5)
                
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
                        'tp_price': tp_price,
                        'sl_price': sl_price,
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
    if len(trades_df) > 0:
        win_rate = len(trades_df[trades_df['status'] == 'WIN']) / len(trades_df) * 100
        total_pnl = trades_df['pnl_usd'].sum()
        
        balances = [START_BALANCE] + trades_df['balance_after'].tolist()
        peak = balances[0]
        max_dd = 0
        for b in balances:
            if b > peak: peak = b
            dd = (peak - b) / peak * 100
            if dd > max_dd: max_dd = dd
            
        print("\n=== V27 ASİMETRİK R:R (1H) OOS BACKTEST ===")
        print(f"Toplam İşlem: {len(trades_df)}")
        print(f"Kazanma Oranı (Sadece WIN): %{win_rate:.2f}")
        print(f"Pozitif İşlem Oranı (Kârlı Çıkış): %{len(trades_df[trades_df['pnl_usd'] > 0]) / len(trades_df) * 100:.2f}")
        print(f"Max Drawdown: %{max_dd:.2f}")
        print(f"Bitiş Bakiyesi: ${balance:.2f} (Net Kâr: ${total_pnl:.2f})")
        print(f"Net Getiri: %{((balance - START_BALANCE)/START_BALANCE)*100:.2f}")
        
        print("\nKoin Bazlı Kâr/Zarar:")
        print(trades_df.groupby('symbol')['pnl_usd'].sum().sort_values(ascending=False))

if __name__ == "__main__":
    run_v27()
