import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split
import os

COMMISSION = 0.0004
SLIPPAGE = 0.0005
START_BALANCE = 100.0
TP_PCT = 0.02
SL_PCT = 0.005

def load_and_merge_mtf_data():
    features_15m_dir = 'bot/engine/features_v39'
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

def run_simulation(bull_df, mode, model_sniper=None, model_watcher=None, features=None):
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
                pnl_usd = pos['margin_usd'] * 10 * net_pnl_pct
                balance += pnl_usd
                pos['exit_time'] = ts
                pos['pnl_usd'] = pnl_usd
                trade_history.append(pos)
            else:
                if (ts - pos['entry_time']).total_seconds() / 60 >= 240:
                    exit_price = row['close']
                    pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price']
                    net_pnl_pct = pnl_pct - (COMMISSION * 2) - SLIPPAGE
                    pnl_usd = pos['margin_usd'] * 10 * net_pnl_pct
                    balance += pnl_usd
                    pos['exit_time'] = ts
                    pos['pnl_usd'] = pnl_usd
                    trade_history.append(pos)
                else:
                    still_open.append(pos)
                    
        open_positions = still_open
        
        # Sadece açık işlem yokken yeni işlem ara (Bileşik getiri güvenliği)
        if len(group) > 0 and len(open_positions) < 1:
            if model_sniper is not None and model_watcher is not None:
                X_test = group[features]
                probs_sniper = model_sniper.predict_proba(X_test)[:, 1]
                probs_trend = model_watcher.predict_proba(X_test)[:, 1]
            else:
                probs_sniper = np.zeros(len(group))
                probs_trend = np.zeros(len(group))
                
            candidates = []
            
            for i, row in group.reset_index(drop=True).iterrows():
                # Ajan 1 & 2: Mikroskobik Trend ve Hacim (Benzin)
                trend_ok = row['adx_14'] > 20
                bb_breakout = row['close'] > row['bb_upper']
                vol_spike = row['vol_spike'] == 1
                
                # Ajan 3: İklim (Makro MTF Confluence)
                mtf_1h_bullish = row['close_1h'] > row['ema_50_1h']
                mtf_4h_bullish = row['close_4h'] > row['ema_50_4h']
                
                # Ajan 4: Dedektif (AI Probability)
                prob_s = probs_sniper[i]
                prob_t = probs_trend[i]
                ai_ok = (prob_s > 0.06 and prob_t > 0.08) # Makul ML threshold'ları
                
                # Ajan 5: Kronos (Temporal Agent)
                # Hafta içi mi? (0-4 Pzt-Cuma). Cts-Paz işlem yasak.
                # Saat 13-21 arası (Londra-New York kesişimi yüksek hacim)
                is_weekday = row['ts'].weekday() < 5
                is_active_session = row['ts'].hour in [13, 14, 15, 16, 17, 18, 19, 20]
                temporal_ok = is_weekday and is_active_session
                
                # Karar Ağacı Mantığı (Master Agent)
                execute = False
                
                if mode == "TEST_1_CLASSIC":
                    # Sadece Ajan 1 & 2 (Eski sistemin)
                    execute = trend_ok and bb_breakout and vol_spike
                
                elif mode == "TEST_2_MTF":
                    # Ajan 1, 2, 3 (MTF Filtreli)
                    execute = trend_ok and bb_breakout and vol_spike and mtf_1h_bullish and mtf_4h_bullish
                    
                elif mode == "TEST_3_AI_MTF":
                    # Ajan 1, 2, 3, 4 (Yapay Zeka Dedektif dahil)
                    execute = trend_ok and bb_breakout and vol_spike and mtf_1h_bullish and mtf_4h_bullish and ai_ok
                    
                elif mode == "TEST_4_FULL_COUNCIL":
                    # Ajan 1, 2, 3, 4, 5 (Tam Kuantum Konseyi - Kutsal Kâse)
                    execute = trend_ok and bb_breakout and vol_spike and mtf_1h_bullish and mtf_4h_bullish and ai_ok and temporal_ok
                    
                if execute:
                    # En yüksek AI puanına sahip olanı seçmek için (AI kapalıysa 0)
                    candidates.append((row['symbol'], row, prob_s))
                    
            if candidates:
                candidates.sort(key=lambda x: x[2], reverse=True)
                best_candidate = candidates[0]
                row = best_candidate[1]
                
                entry_price = row['close']
                margin_usd = balance
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
        pnl_usd = pos['margin_usd'] * 10 * net_pnl_pct
        balance += pnl_usd
        pos['exit_time'] = last_row['ts']
        pos['pnl_usd'] = pnl_usd
        trade_history.append(pos)
        
    trades_df = pd.DataFrame(trade_history)
    return trades_df, balance

def run_v50_ablation():
    print("V50 Multi-Agent Kuantum Konseyi: Ablation (Kombinasyon) Testi Başlıyor...")
    
    combined_df = load_and_merge_mtf_data()
    bull_df = combined_df[(combined_df['ts'] >= '2024-01-01') & (combined_df['ts'] < '2025-01-01')].copy()
    
    features = [c for c in combined_df.columns if c not in [
        'ts', 'open', 'high', 'low', 'close', 'volume', 'symbol',
        'target', 'target_is_trend', 'close_1h', 'ema_50_1h', 'close_4h', 'ema_50_4h'
    ]]
    
    valid_df = combined_df.dropna(subset=features + ['target', 'target_is_trend'])
    X_train, _, y_train_trend, _ = train_test_split(valid_df[features], valid_df['target_is_trend'], test_size=0.2, random_state=42)
    _, _, y_train_sniper, _ = train_test_split(valid_df[features], valid_df['target'], test_size=0.2, random_state=42)
    
    print("\nAjan 4 (Yapay Zeka Dedektifi) Eğitiliyor...")
    model_watcher = xgb.XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.05, random_state=42, eval_metric='logloss')
    model_watcher.fit(X_train, y_train_trend)
    
    model_sniper = xgb.XGBClassifier(n_estimators=150, max_depth=5, learning_rate=0.05, random_state=42, eval_metric='logloss')
    model_sniper.fit(X_train, y_train_sniper)
    
    modes = [
        ("TEST_1_CLASSIC", "Ajan 1+2 (İndikatör + Hacim)"),
        ("TEST_2_MTF", "Ajan 1+2+3 (Makro 4H Filtresi)"),
        ("TEST_3_AI_MTF", "Ajan 1+2+3+4 (Yapay Zeka Dedektifi)"),
        ("TEST_4_FULL_COUNCIL", "Ajan 1+2+3+4+5 (AI + Kronos Zaman Filtresi)")
    ]
    
    print("\n--- 2024 YILI MEGA BOĞA & CHOP SİMÜLASYONU ---")
    
    for mode_id, mode_name in modes:
        print(f"\n[+] Çalıştırılıyor: {mode_name}...")
        trades_df, final_balance = run_simulation(bull_df, mode_id, model_sniper, model_watcher, features)
        
        if len(trades_df) == 0:
            print(f"  Sonuç: 0 İşlem.")
            continue
            
        win_rate = len(trades_df[trades_df['pnl_usd'] > 0]) / len(trades_df) * 100
        print(f"  Toplam İşlem: {len(trades_df)}")
        print(f"  Kazanma Oranı: %{win_rate:.1f}")
        print(f"  Nihai Bakiye: ${final_balance:.2f} (x{final_balance/START_BALANCE:.1f} Katlama)")

if __name__ == "__main__":
    run_v50_ablation()
