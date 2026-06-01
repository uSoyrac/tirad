import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split
import os

# GERÇEKÇİ MALİYETLER (Binance VIP 0 veya standart seviye varsayımıyla, slippage dahil)
ENTRY_FEE = 0.0009  # %0.04 Komisyon + %0.05 Slippage (Market Order)
TP_FEE = 0.0001     # %0.01 Maker Fee + 0 Slippage (Limit Order)
SL_FEE = 0.0009     # %0.04 Komisyon + %0.05 Slippage (Market Order)

START_BALANCE = 100.0
LEVERAGE = 10
BET_FRACTION = 0.20 # Kasanın %20'si riske ediliyor
TP_PCT = 0.020 # 10x kaldıraçta +%20 ROE hedefleniyor
SL_PCT = 0.010 # 10x kaldıraçta -%10 ROE riske ediliyor

def load_and_merge_mtf_data():
    features_15m_dir = 'bot/engine/features_v61'
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

def run_v61_expo_rocket():
    print("V61 Expo Rocket: Komisyon Düşmanı Eksponansiyel Model Başlıyor...")
    print("Hedef: %2 Fiyat Hareketi (10x Kaldıraç = %20 ROE) | Risk: %1 Fiyat Düşüşü (10x = -%10 ROE)")
    print(f"Betting (Kasa) Oranı: Her işlemde Kasanın %{BET_FRACTION*100:.0f}'si riske atılacak.")
    print("İşlem Maliyetleri: Market Giriş (%0.09) + Limit Çıkış (%0.01) veya Market Stop (%0.09)")
    
    combined_df = load_and_merge_mtf_data()
    bull_df = combined_df[(combined_df['ts'] >= '2024-01-01') & (combined_df['ts'] < '2025-01-01')].copy()
    
    features = [
        'vol_derivative', 'smart_money_spike', 'body_ratio', 
        'upper_wick_ratio', 'lower_wick_ratio', 'dist_ema50', 
        'dist_ema200', 'macd_diff'
    ]
    
    valid_df = combined_df.dropna(subset=features + ['target'])
    
    print("\n[AI] Sınıf Dengesizliği (Class Imbalance) Analizi Yapılıyor...")
    target_count = valid_df['target'].sum()
    total_count = len(valid_df)
    print(f"Gerçek Kırılımların (Target=1) Toplam İçindeki Oranı: %{(target_count/total_count)*100:.2f}")
    
    # Scale Pos Weight (Imbalanced veri için kritik, %2 hareket çok nadirdir)
    scale_pos = (total_count - target_count) / target_count
    
    X_train, _, y_train, _ = train_test_split(valid_df[features], valid_df['target'], test_size=0.2, random_state=42)
    
    print(f"Ajan 4 (Yapay Zeka Dedektifi) Dev Trendleri Öğreniyor (scale_pos_weight={scale_pos:.1f})...")
    model_ai = xgb.XGBClassifier(
        n_estimators=300, max_depth=6, learning_rate=0.03, 
        subsample=0.8, colsample_bytree=0.8, random_state=42, 
        eval_metric='logloss', tree_method='hist',
        scale_pos_weight=scale_pos # Kritik: Çünkü %2.0'lık hareket bulmak, %0.5'lik hareket bulmaktan 5 kat daha zordur!
    )
    model_ai.fit(X_train, y_train)
    
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
                    pnl_pct = TP_PCT
                    cost_pct = ENTRY_FEE + TP_FEE
                else: # SL Hit
                    pnl_pct = -SL_PCT
                    cost_pct = ENTRY_FEE + SL_FEE
                    
                net_pnl_pct = pnl_pct - cost_pct
                pnl_usd = pos['margin_usd'] * LEVERAGE * net_pnl_pct
                
                balance += pnl_usd
                pos['exit_time'] = ts
                pos['pnl_usd'] = pnl_usd
                pos['roe_pct'] = net_pnl_pct * LEVERAGE * 100
                pos['status'] = "TP" if (hit_tp and not hit_sl) else "SL"
                pos['balance_after'] = balance
                trade_history.append(pos)
            else:
                if (ts - pos['entry_time']).total_seconds() / 60 >= (15 * 32): # 32 bar (8 saat) zaman aşımı
                    exit_price = row['close']
                    pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price']
                    cost_pct = ENTRY_FEE + SL_FEE # Zaman aşımı exit'i piyasa emriyle olur
                    net_pnl_pct = pnl_pct - cost_pct
                    pnl_usd = pos['margin_usd'] * LEVERAGE * net_pnl_pct
                    
                    balance += pnl_usd
                    pos['exit_time'] = ts
                    pos['pnl_usd'] = pnl_usd
                    pos['roe_pct'] = net_pnl_pct * LEVERAGE * 100
                    pos['status'] = "TIME_EXIT"
                    pos['balance_after'] = balance
                    trade_history.append(pos)
                else:
                    still_open.append(pos)
                    
        open_positions = still_open
        
        # Eğer açık işlem yoksa (Bileşik getiri güvenliği), yeni işlem ara
        if len(group) > 0 and len(open_positions) < 1:
            X_test = group[features]
            probs_ai = model_ai.predict_proba(X_test)[:, 1]
            
            candidates = []
            
            for i, row in group.reset_index(drop=True).iterrows():
                # Ajan 1: Supertrend + Keltner Channel 
                supertrend_bullish = row['supertrend_dir'] == 1
                kc_breakout = row['close'] > row['kc_upper']
                macd_bullish = row['macd_diff'] > 0
                
                # Ajan 3: Multi-Timeframe Makro Onay 
                mtf_1h_bullish = row['close_1h'] > row['ema_50_1h']
                mtf_4h_bullish = row['close_4h'] > row['ema_50_4h']
                
                # Ajan 5: Kronos (Temporal)
                is_weekday = row['ts'].weekday() < 5
                is_active_session = row['ts'].hour in [13, 14, 15, 16, 17, 18, 19, 20]
                
                # Ajan 4: AI Fakeout Dedektifi
                prob = probs_ai[i]
                
                # Threshold'u 0.50'den yüksek tutarsak daha az ama daha güvenli işlem açar
                ai_approved = prob > 0.60 
                
                if supertrend_bullish and kc_breakout and macd_bullish and mtf_1h_bullish and mtf_4h_bullish and is_weekday and is_active_session and ai_approved:
                    candidates.append((row['symbol'], row, prob))
                    
            if candidates:
                candidates.sort(key=lambda x: x[2], reverse=True)
                best_candidate = candidates[0]
                row = best_candidate[1]
                
                entry_price = row['close']
                margin_usd = balance * BET_FRACTION 
                
                open_positions.append({
                    'symbol': row['symbol'],
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
        cost_pct = ENTRY_FEE + SL_FEE
        net_pnl_pct = pnl_pct - cost_pct
        pnl_usd = pos['margin_usd'] * LEVERAGE * net_pnl_pct
        balance += pnl_usd
        pos['exit_time'] = last_row['ts']
        pos['pnl_usd'] = pnl_usd
        pos['roe_pct'] = net_pnl_pct * LEVERAGE * 100
        pos['status'] = "FORCE_CLOSE"
        pos['balance_after'] = balance
        trade_history.append(pos)
        
    trades_df = pd.DataFrame(trade_history)
    
    print("\nSimülasyon Tamamlandı! V61 Expo Rocket Sonuçları:\n")
    if len(trades_df) == 0:
         print("Sistem hiç işlem açmadı! AI Threshold çok yüksek olabilir.")
         return
         
    trades_df['week_start'] = trades_df['exit_time'].dt.to_period('W').dt.start_time
    weekly_stats = trades_df.groupby('week_start').agg(
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
    
    win_rate = len(trades_df[trades_df['pnl_usd'] > 0]) / len(trades_df) * 100
    avg_roe = trades_df['roe_pct'].mean()
    
    print(f"\n--- V61 EXPO ROCKET ÖZETİ ---")
    print(f"Kasa Kullanımı (Bet): %{BET_FRACTION*100:.0f} (Her işlemde kasanın %20'si riske edilir)")
    print(f"Hedeflenen Kaldıraç: {LEVERAGE}x")
    print(f"Başlangıç Bakiyesi: $100.00")
    print(f"Bitiş Bakiyesi: ${balance:.2f} (x{balance/100:.2f} KATLAMA)")
    print(f"Net Kâr: +%{(balance - 100.0):.1f}")
    print(f"Toplam İşlem: {len(trades_df)}")
    print(f"Kazanma Oranı (Win Rate): %{win_rate:.1f}")
    print(f"İşlem Başı Ortalama ROE: %{avg_roe:.2f}")

if __name__ == "__main__":
    run_v61_expo_rocket()
