import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split
import os

COMMISSION = 0.0004
SLIPPAGE = 0.0005
START_BALANCE = 100.0
LEVERAGE = 10
BET_FRACTION = 0.10 # Kasanın %10'u ile işleme girilir (100 doların 10 doları)
TP_PCT = 0.005 # %0.5 Fiyat Hareketi = 10x Kaldıraçta %5 ROE
SL_PCT = 0.005 # %0.5 Fiyat Hareketi = 10x Kaldıraçta -%5 ROE

def load_and_merge_mtf_data():
    features_15m_dir = 'bot/engine/features_v60'
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

def run_v60_betting():
    print("V60 Kuantum Konseyi: Smart Money AI ve Betting (Kasa) Yönetimi Başlıyor...")
    
    combined_df = load_and_merge_mtf_data()
    bull_df = combined_df[(combined_df['ts'] >= '2024-01-01') & (combined_df['ts'] < '2025-01-01')].copy()
    
    # Sadece yeni Smart Money verilerini AI'a veriyoruz
    features = [
        'vol_derivative', 'smart_money_spike', 'body_ratio', 
        'upper_wick_ratio', 'lower_wick_ratio', 'dist_ema50', 
        'dist_ema200', 'macd_diff'
    ]
    
    valid_df = combined_df.dropna(subset=features + ['target'])
    X_train, _, y_train, _ = train_test_split(valid_df[features], valid_df['target'], test_size=0.2, random_state=42)
    
    print("Ajan 4 (Yapay Zeka Dedektifi) Eğitiliyor...")
    model_ai = xgb.XGBClassifier(
        n_estimators=200, max_depth=5, learning_rate=0.05, 
        subsample=0.8, colsample_bytree=0.8, random_state=42, 
        eval_metric='logloss', tree_method='hist',
        scale_pos_weight=1.5
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
                pnl_usd = pos['margin_usd'] * LEVERAGE * net_pnl_pct
                balance += pnl_usd
                pos['exit_time'] = ts
                pos['pnl_usd'] = pnl_usd
                pos['roe_pct'] = (pnl_usd / pos['margin_usd']) * 100
                trade_history.append(pos)
            else:
                if (ts - pos['entry_time']).total_seconds() / 60 >= (15 * 20): # 20 bar horizon
                    exit_price = row['close']
                    pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price']
                    net_pnl_pct = pnl_pct - (COMMISSION * 2) - SLIPPAGE
                    pnl_usd = pos['margin_usd'] * LEVERAGE * net_pnl_pct
                    balance += pnl_usd
                    pos['exit_time'] = ts
                    pos['pnl_usd'] = pnl_usd
                    pos['roe_pct'] = (pnl_usd / pos['margin_usd']) * 100
                    trade_history.append(pos)
                else:
                    still_open.append(pos)
                    
        open_positions = still_open
        
        # Eğer açık işlem yoksa, Ajan Konseyi devreye girer
        if len(group) > 0 and len(open_positions) < 1:
            X_test = group[features]
            probs_ai = model_ai.predict_proba(X_test)[:, 1]
            
            candidates = []
            
            for i, row in group.reset_index(drop=True).iterrows():
                # Ajan 1: Supertrend + Keltner Channel (Trend Yönü ve İvmesi)
                supertrend_bullish = row['supertrend_dir'] == 1
                kc_breakout = row['close'] > row['kc_upper']
                macd_bullish = row['macd_diff'] > 0
                
                # Ajan 3: Multi-Timeframe Makro Onay (Balinaların yönü)
                mtf_1h_bullish = row['close_1h'] > row['ema_50_1h']
                mtf_4h_bullish = row['close_4h'] > row['ema_50_4h']
                
                # Ajan 5: Kronos (Temporal & Volatility)
                is_weekday = row['ts'].weekday() < 5
                is_active_session = row['ts'].hour in [13, 14, 15, 16, 17, 18, 19, 20]
                
                # Ajan 4: AI Fakeout Dedektifi
                prob = probs_ai[i]
                ai_approved = prob > 0.40 # AI'nin bu smart verilere göre onay vermesi
                
                if supertrend_bullish and kc_breakout and macd_bullish and mtf_1h_bullish and mtf_4h_bullish and is_weekday and is_active_session and ai_approved:
                    candidates.append((row['symbol'], row, prob))
                    
            if candidates:
                candidates.sort(key=lambda x: x[2], reverse=True)
                best_candidate = candidates[0]
                row = best_candidate[1]
                
                entry_price = row['close']
                # BETTING AJANI: Kasamın sadece %10'unu (veya belirlenen oranı) riske at
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
        net_pnl_pct = pnl_pct - (COMMISSION * 2) - SLIPPAGE
        pnl_usd = pos['margin_usd'] * LEVERAGE * net_pnl_pct
        balance += pnl_usd
        pos['exit_time'] = last_row['ts']
        pos['pnl_usd'] = pnl_usd
        pos['roe_pct'] = (pnl_usd / pos['margin_usd']) * 100
        trade_history.append(pos)
        
    trades_df = pd.DataFrame(trade_history)
    
    print("\nSimülasyon Tamamlandı! V60 Betting Ajanı Sonuçları:\n")
    if len(trades_df) == 0:
         print("Sistem hiç işlem açmadı!")
         return
         
    trades_df['week_start'] = trades_df['exit_time'].dt.to_period('W').dt.start_time
    weekly_stats = trades_df.groupby('week_start').agg(
        trades_count=('symbol', 'count'),
        weekly_pnl=('pnl_usd', 'sum')
    ).reset_index()
    
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
    
    print(f"\n--- V60 KUANTUM BETTING & SMART AI ÖZETİ ---")
    print(f"Kasa Kullanımı (Bet): %{BET_FRACTION*100:.0f} (Her işlemde kasanın %10'u riske edilir)")
    print(f"Hedeflenen Kaldıraç: {LEVERAGE}x")
    print(f"Başlangıç Bakiyesi: $100.00")
    print(f"Bitiş Bakiyesi: ${balance:.2f} (x{balance/100:.2f} KATLAMA)")
    print(f"Net Kâr: +%{(balance - 100.0):.1f}")
    print(f"Toplam İşlem: {len(trades_df)}")
    print(f"Kazanma Oranı (Win Rate): %{win_rate:.1f}")
    print(f"İşlem Başı Ortalama ROE: %{avg_roe:.2f}")

if __name__ == "__main__":
    run_v60_betting()
