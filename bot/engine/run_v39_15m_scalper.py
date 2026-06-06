import pandas as pd
import numpy as np
import xgboost as xgb
import os

COMMISSION = 0.0004
SLIPPAGE = 0.0005
START_BALANCE = 100.0

def run_v39_15m_scalper():
    features_dir = 'bot/engine/features_v39'
    files = [f for f in os.listdir(features_dir) if f.endswith('.csv')]
    
    all_data = []
    print("V39 15m Yüksek Frekans Scalper Başlatılıyor...")
    print("Veriler yükleniyor (70.000+ 15m Mum)...")
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
        'target', 'target_is_trend'
    ]]
    
    train_df.dropna(subset=features + ['target', 'target_is_trend'], inplace=True)
    
    X_train = train_df[features]
    y_train_trend = train_df['target_is_trend']
    y_train_sniper = train_df['target']
    
    print("Ajan 1 Eğitiliyor: Pusula (Trend & Hacim Onayı)...")
    model_watcher = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric='logloss',
        tree_method='hist'
    )
    model_watcher.fit(X_train, y_train_trend)
    
    print("Ajan 2 Eğitiliyor: Sıkışma (Bollinger Kırılımı ve 10x Vur-Kaç)...")
    model_sniper = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric='logloss',
        tree_method='hist'
    )
    model_sniper.fit(X_train, y_train_sniper)
    print("Scalper Yapay Zekası Eğitildi. 10x Kaldıraçlı OOS Test Başlıyor!")
    
    balance = START_BALANCE
    open_positions = []
    trade_history = []
    
    grouped = test_df.groupby('ts')
    
    # 15m hedefleri
    tp_pct_target = 0.02   # %2 fiyat hareketi
    sl_pct_target = 0.005  # %0.5 zararkesen
    
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
                
                # 10x Kaldıraç Çarpanı
                pnl_usd = pos['margin_usd'] * 10 * net_pnl_pct
                
                balance += pnl_usd
                pos['exit_price'] = exit_price
                pos['exit_time'] = ts
                pos['pnl_usd'] = pnl_usd
                
                # ROE = Return on Equity (Yatırılan paraya göre getiri)
                pos['roe_pct'] = (pnl_usd / pos['margin_usd']) * 100
                pos['status'] = "TP_HIT (+%20 ROE)" if hit_tp else "SL_HIT (-%5 ROE)"
                pos['balance_after'] = balance
                trade_history.append(pos)
            else:
                # 15m scalp için max 16 mum (4 saat) bekleme
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
        
        if len(group) > 0 and len(open_positions) < 1: # Aynı anda sadece 1 işleme (Tüm kasa) izin ver
            X_test = group[features]
            probs_trend = model_watcher.predict_proba(X_test)[:, 1]
            probs_sniper = model_sniper.predict_proba(X_test)[:, 1]
            
            candidates = []
            for i, row in group.reset_index(drop=True).iterrows():
                # Hacim Zıplaması Onayı (Ajan 3) + Trend Onayı (Ajan 1) + Sıkışma Onayı (Ajan 2)
                vol_spike = row['vol_spike']
                adx = row['adx_14']
                
                prob_trend = probs_trend[i]
                prob_sniper = probs_sniper[i]
                
                # Sadece hacim olan, ADX>15 olan ve modellerin çok emin olduğu anlar
                if vol_spike == 1 and adx > 15 and prob_trend > 0.65 and prob_sniper > 0.65:
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
                
                # Tüm kasa margin olarak yatırılıyor. (Bileşik Getiri / Compound Interest)
                margin_usd = balance
                position_size = margin_usd * 10 # 10x Kaldıraç
                
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
        pos['exit_price'] = exit_price
        pos['exit_time'] = last_row['ts']
        pos['pnl_usd'] = pnl_usd
        pos['roe_pct'] = (pnl_usd / pos['margin_usd']) * 100
        pos['status'] = "FORCE_CLOSE"
        pos['balance_after'] = balance
        trade_history.append(pos)
        
    trades_df = pd.DataFrame(trade_history)
    
    print("\nSimülasyon Tamamlandı. V39 15m Scalper Raporu Oluşturuluyor...\n")
    
    if len(trades_df) == 0:
         print("Sistem hiç işlem açmadı!")
         return
         
    # Sadece ilk 20 ve son 10 işlemi gösterelim (Terminali boğmamak için)
    print("--- İLK 10 VUR-KAÇ İŞLEMİ ---")
    first_10 = trades_df.head(10)[['entry_time', 'symbol', 'status', 'roe_pct', 'pnl_usd', 'balance_after']]
    print(first_10.to_string(index=False))
    
    print("\n--- SON 10 VUR-KAÇ İŞLEMİ ---")
    last_10 = trades_df.tail(10)[['entry_time', 'symbol', 'status', 'roe_pct', 'pnl_usd', 'balance_after']]
    print(last_10.to_string(index=False))
    
    win_rate = len(trades_df[trades_df['pnl_usd'] > 0]) / len(trades_df) * 100
    
    print("\n--- V39 15M SCALPER (ÖZEL TİM) 1 YILLIK KÖR TEST ÖZETİ ---")
    print(f"Başlangıç Bakiyesi: $100.00")
    print(f"Bitiş Bakiyesi: ${balance:.2f}")
    print(f"Toplam İşlem: {len(trades_df)}")
    print(f"Kazanma Oranı (Win Rate): %{win_rate:.1f}")

if __name__ == "__main__":
    run_v39_15m_scalper()
