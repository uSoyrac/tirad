import pandas as pd
import numpy as np
import xgboost as xgb
import os
import ta
import json
from datetime import datetime, timedelta

COMMISSION = 0.0004
SLIPPAGE = 0.0005
RISK_PER_TRADE = 0.02
START_BALANCE = 10000.0

def run_v28():
    features_dir = 'bot/engine/features_v27' # V27 modelini ve verilerini kullanıyoruz, sadece filtre ekleyeceğiz
    files = [f for f in os.listdir(features_dir) if f.endswith('.csv')]
    
    all_data = []
    for f in files:
        df = pd.read_csv(os.path.join(features_dir, f), parse_dates=['ts'])
        df['symbol'] = f.replace('.csv', '')
        
        # Piyasa Rejimi Filtresi İçin ADX Hesabı
        adx_ind = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
        df['adx_14'] = adx_ind.adx()
        
        all_data.append(df)
        
    combined_df = pd.concat(all_data)
    combined_df.sort_values(by='ts', inplace=True)
    combined_df.reset_index(drop=True, inplace=True)
    
    split_date = combined_df['ts'].max() - timedelta(days=90)
    test_df = combined_df[combined_df['ts'] >= split_date].copy()
    
    print(f"V28 1H Test Set (OOS): {len(test_df)} samples")
    
    # Önceden eğitilmiş V27 Modelini Yükle
    model = xgb.XGBClassifier()
    model.load_model("bot/engine/v27_xgb_model.json")
    with open("bot/engine/v27_xgb_meta.json", "r") as f:
        meta = json.load(f)
    features = meta["features"]
    
    print("V28 Rejim Filtreli Simülasyon Başlıyor...")
    
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
            
            # V28: PİYASA REJİMİ FİLTRESİ
            # Yapay zeka sinyal verse bile, trend yoksa (ADX < 25) GİRME!
            # Ayrıca aşırı hantal piyasaları (Daralma) atla.
            is_trending = row['adx_14'] > 25
            
            if prob > 0.55 and is_trending:
                sym = row['symbol']
                
                if any(p['symbol'] == sym for p in open_positions):
                    continue
                    
                entry_price = row['close']
                atr = (row['atr_14_pct'] / 100) * entry_price
                
                tp_price = entry_price + (atr * 3.5)
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
            
        print("\n=== V28 REJİM FİLTRELİ OOS BACKTEST ===")
        print(f"Toplam İşlem: {len(trades_df)} (ADX Filtresi ile sayılar düştü)")
        print(f"Kazanma Oranı (Sadece WIN): %{win_rate:.2f}")
        print(f"Pozitif İşlem Oranı (Kârlı Çıkış): %{len(trades_df[trades_df['pnl_usd'] > 0]) / len(trades_df) * 100:.2f}")
        print(f"Max Drawdown: %{max_dd:.2f}")
        print(f"Bitiş Bakiyesi: ${balance:.2f} (Net Kâr: ${total_pnl:.2f})")
        print(f"Net Getiri: %{((balance - START_BALANCE)/START_BALANCE)*100:.2f}")
        
        print("\nKoin Bazlı Kâr/Zarar:")
        print(trades_df.groupby('symbol')['pnl_usd'].sum().sort_values(ascending=False))

if __name__ == "__main__":
    run_v28()
