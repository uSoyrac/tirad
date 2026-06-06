import pandas as pd
import numpy as np
import xgboost as xgb
import os
from datetime import datetime, timedelta

COMMISSION = 0.0004  # 0.04% per trade (0.08% round trip)
SLIPPAGE = 0.0005    # 0.05% slippage on exit
RISK_PER_TRADE = 0.02 # Riske edilen bakiye
START_BALANCE = 10000.0

def run_realistic_backtest():
    features_dir = 'bot/engine/features_v26'
    files = [f for f in os.listdir(features_dir) if f.endswith('.csv')]
    
    all_data = []
    for f in files:
        df = pd.read_csv(os.path.join(features_dir, f), parse_dates=['ts'])
        df['symbol'] = f.replace('.csv', '')
        all_data.append(df)
        
    combined_df = pd.concat(all_data)
    combined_df.sort_values(by='ts', inplace=True)
    combined_df.reset_index(drop=True, inplace=True)
    
    # Split into Train (First 9 Months) and Test (Last 3 Months)
    # Using specific dates since we fetched from 2025-06-01 to 2026-06-01
    split_date = combined_df['ts'].max() - timedelta(days=90)
    
    train_df = combined_df[combined_df['ts'] < split_date].copy()
    test_df = combined_df[combined_df['ts'] >= split_date].copy()
    
    print(f"Train Set: {len(train_df)} samples (until {split_date})")
    print(f"Test Set (Out of Sample): {len(test_df)} samples (after {split_date})")
    
    # Train the Model
    y_train = train_df['target'].astype(int)
    exclude = ['target', 'open', 'high', 'low', 'close', 'volume', 'signed_volume', 'ts', 'symbol']
    features = [c for c in train_df.columns if c not in exclude]
    
    X_train = train_df[features]
    
    model = xgb.XGBClassifier(
        objective='binary:logistic',
        n_estimators=200,
        learning_rate=0.05,
        max_depth=4,
        subsample=0.8,
        tree_method='hist'
    )
    
    print("Eğitim başlıyor (9 Ay)...")
    model.fit(X_train, y_train)
    print("Eğitim tamamlandı.")
    
    # Walk-Forward Backtest on Test Set
    balance = START_BALANCE
    open_positions = [] # list of dicts
    trade_history = []
    
    # Group test data by timestamp
    grouped = test_df.groupby('ts')
    
    for ts, group in grouped:
        # 1. Update Open Positions (Check High/Low for TP/SL)
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
            
            hit_tp = high >= pos['tp_price']
            hit_sl = low <= pos['sl_price']
            
            if hit_tp or hit_sl:
                # If both hit in the same 4H candle, we assume SL was hit first to be pessimistic
                if hit_tp and hit_sl:
                    exit_price = pos['sl_price']
                    status = "LOSS (Wick)"
                elif hit_tp:
                    exit_price = pos['tp_price']
                    status = "WIN"
                else:
                    exit_price = pos['sl_price']
                    status = "LOSS"
                    
                # Calculate PnL
                pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price']
                
                # Deduct Slippage & Commission (Round trip: entry commission was not deducted, deduct both here)
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
                # Vade süresi doldu mu? (Zaman Bariyeri: 24 bar = 96 saat)
                if (ts - pos['entry_time']).total_seconds() / 3600 >= 96:
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
        
        # 2. Look for new entries
        X_test = group[features]
        probs = model.predict_proba(X_test)[:, 1]
        
        for i, row in group.iterrows():
            prob = probs[group.index.get_loc(i)]
            
            # Gerçekçi Eşik: Olasılık yüksekse
            if prob > 0.44:
                sym = row['symbol']
                
                # Aynı coinde açık pozisyon varsa girme
                if any(p['symbol'] == sym for p in open_positions):
                    continue
                    
                entry_price = row['close']
                atr = (row['atr_14_pct'] / 100) * entry_price
                
                tp_price = entry_price + (atr * 2.5)
                sl_price = entry_price - (atr * 1.5)
                
                risk_usd = balance * RISK_PER_TRADE
                sl_pct = (entry_price - sl_price) / entry_price
                
                # Slippage yüzünden risk biraz daha büyük olabilir ama formül sabit kalıyor
                position_size = risk_usd / sl_pct
                
                # Marjin kontrolü (En fazla 5x kaldıraç)
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
                    
    # Simulate closing remaining open positions at the very end
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
        
    # Raporlama
    trades_df = pd.DataFrame(trade_history)
    if len(trades_df) > 0:
        win_rate = len(trades_df[trades_df['pnl_usd'] > 0]) / len(trades_df) * 100
        total_pnl = trades_df['pnl_usd'].sum()
        
        # Max Drawdown
        balances = [START_BALANCE] + trades_df['balance_after'].tolist()
        peak = balances[0]
        max_dd = 0
        for b in balances:
            if b > peak: peak = b
            dd = (peak - b) / peak * 100
            if dd > max_dd: max_dd = dd
            
        print("\n=== V26 ACI ALIMASIZ (REALISTIC) OOS BACKTEST ===")
        print(f"Zaman: {split_date.date()} -> Bugün")
        print(f"Toplam İşlem: {len(trades_df)}")
        print(f"Kazanma Oranı (Win Rate): %{win_rate:.2f}")
        print(f"Max Drawdown: %{max_dd:.2f}")
        print(f"Başlangıç: ${START_BALANCE:.2f}")
        print(f"Bitiş: ${balance:.2f} (Net Kâr: ${total_pnl:.2f})")
        print(f"Net Getiri: %{((balance - START_BALANCE)/START_BALANCE)*100:.2f}")
        
        # Breakdown by symbol
        print("\nKoin Bazlı Kâr/Zarar:")
        print(trades_df.groupby('symbol')['pnl_usd'].sum().sort_values(ascending=False))
        
        trades_df.to_csv("bot/engine/v26_trades.csv", index=False)
    else:
        print("Hiç işlem bulunamadı!")

if __name__ == "__main__":
    run_realistic_backtest()
