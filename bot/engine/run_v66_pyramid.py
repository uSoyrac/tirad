import pandas as pd
import numpy as np
import xgboost as xgb
import os

ENTRY_FEE = 0.0009
TP_FEE = 0.0001
SL_FEE = 0.0009

START_BALANCE = 100.0
LEVERAGE = 10

BASE_BET_FRACTION = 0.15      # İlk giriş kasası
PYRAMID_BET_FRACTION = 0.15   # Her adımda eklenecek kasa oranı
INITIAL_SL_PCT = 0.010        # İlk Stop Loss %1
PYRAMID_TRIGGER_PCT = 0.015   # Fiyat %1.5 kâra geçerse piramit at

OPTIMAL_THRESHOLD = 0.70      # OOS test için makul eşik
RECOVERY_THRESHOLD = 0.75

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

def run_v66_pyramiding():
    print("🌟 V66 PYRAMIDING (Trend Sörfü & Trailing Stop) SİMÜLASYONU BAŞLIYOR...")
    
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
    
    # 2025 Öncesi Eğitim
    train_df = valid_df[valid_df['ts'] < '2025-01-01']
    # 2025 ve Sonrası (1.5 Yıllık OOS Test)
    test_df = valid_df[valid_df['ts'] >= '2025-01-01']
    
    target_count = train_df['target'].sum()
    total_count = len(train_df)
    scale_pos = (total_count - target_count) / target_count
    
    X_train = train_df[features]
    y_train = train_df['target']
    
    print("Yapay Zeka (AI) Eğitiliyor...")
    model_ai = xgb.XGBClassifier(
        n_estimators=400, max_depth=7, learning_rate=0.02, 
        subsample=0.8, colsample_bytree=0.8, random_state=42, 
        eval_metric='logloss', tree_method='hist',
        scale_pos_weight=scale_pos
    )
    model_ai.fit(X_train, y_train)
    
    print("OOS Kör Test (1.5 Yıllık Pyramiding) Hesaplanıyor...")
    test_features = test_df[features].fillna(0)
    ai_probs = model_ai.predict_proba(test_features)[:, 1]
    
    test_df = test_df.copy()
    test_df['ai_prob'] = ai_probs
    
    # Makro Trend Filtresi
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
            close = row['close']
            
            # 1. Stop-Loss Kontrolü
            if low <= pos['sl_price']:
                # İşlem Zararla veya Trailing Stop ile kapandı
                exit_price = pos['sl_price']
                pnl_pct = (exit_price - pos['avg_entry_price']) / pos['avg_entry_price']
                net_pnl_pct = pnl_pct - (ENTRY_FEE + SL_FEE)
                pnl_usd = pos['margin_usd'] * LEVERAGE * net_pnl_pct
                
                balance += pnl_usd
                pos['exit_time'] = ts
                pos['exit_price'] = exit_price
                pos['pnl_usd'] = pnl_usd
                pos['status'] = "STOP_LOSS / TRAILING_STOP"
                pos['balance_after'] = balance
                
                # Sadece gerçek zararda recovery moduna geç, kâr kilitliyken patlarsa geçme
                in_recovery_mode = (pnl_usd < 0)
                trade_history.append(pos)
                continue
                
            # 2. Dinamik Trend Exit Kontrolü (Supertrend SAT veya MACD negatif)
            # Fakat piramitlendiyse hemen çıkmasın diye ufak tolerans verebiliriz.
            if row['supertrend_dir'] == -1:
                exit_price = close
                pnl_pct = (exit_price - pos['avg_entry_price']) / pos['avg_entry_price']
                net_pnl_pct = pnl_pct - (ENTRY_FEE + TP_FEE)
                pnl_usd = pos['margin_usd'] * LEVERAGE * net_pnl_pct
                
                balance += pnl_usd
                pos['exit_time'] = ts
                pos['exit_price'] = exit_price
                pos['pnl_usd'] = pnl_usd
                pos['status'] = "DYNAMIC_TREND_EXIT"
                pos['balance_after'] = balance
                
                in_recovery_mode = (pnl_usd < 0)
                trade_history.append(pos)
                continue

            # 3. Time-out Kontrolü (Limitsiz kâr için süreyi uzatıyoruz - 48 saat)
            if (ts - pos['entry_time']).total_seconds() / 3600 >= 48:
                exit_price = close
                pnl_pct = (exit_price - pos['avg_entry_price']) / pos['avg_entry_price']
                net_pnl_pct = pnl_pct - (ENTRY_FEE + TP_FEE)
                pnl_usd = pos['margin_usd'] * LEVERAGE * net_pnl_pct
                
                balance += pnl_usd
                pos['exit_time'] = ts
                pos['exit_price'] = exit_price
                pos['pnl_usd'] = pnl_usd
                pos['status'] = "TIME_OUT"
                pos['balance_after'] = balance
                
                in_recovery_mode = (pnl_usd < 0)
                trade_history.append(pos)
                continue
                
            # 4. PYRAMIDING KONTROLÜ
            # Level 1 Ekleme
            if pos['pyramid_level'] == 0 and high >= pos['base_entry_price'] * (1 + PYRAMID_TRIGGER_PCT):
                add_margin = balance * PYRAMID_BET_FRACTION
                add_price = pos['base_entry_price'] * (1 + PYRAMID_TRIGGER_PCT)
                
                # Yeni ortalama maliyet hesaplama
                total_qty = (pos['margin_usd'] * LEVERAGE / pos['avg_entry_price']) + (add_margin * LEVERAGE / add_price)
                new_margin = pos['margin_usd'] + add_margin
                new_avg_price = (new_margin * LEVERAGE) / total_qty
                
                pos['margin_usd'] = new_margin
                pos['avg_entry_price'] = new_avg_price
                pos['pyramid_level'] = 1
                
                # Güvenlik Kilidi: Stop'u Base Entry'ye çek (Başa Baş)
                pos['sl_price'] = pos['base_entry_price']
                
            # Level 2 Ekleme
            elif pos['pyramid_level'] == 1 and high >= pos['base_entry_price'] * (1 + PYRAMID_TRIGGER_PCT * 2):
                add_margin = balance * PYRAMID_BET_FRACTION
                add_price = pos['base_entry_price'] * (1 + PYRAMID_TRIGGER_PCT * 2)
                
                total_qty = (pos['margin_usd'] * LEVERAGE / pos['avg_entry_price']) + (add_margin * LEVERAGE / add_price)
                new_margin = pos['margin_usd'] + add_margin
                new_avg_price = (new_margin * LEVERAGE) / total_qty
                
                pos['margin_usd'] = new_margin
                pos['avg_entry_price'] = new_avg_price
                pos['pyramid_level'] = 2
                
                # Güvenlik Kilidi: Stop'u Level 1 Entry'ye çek (Kârı Kilitle)
                pos['sl_price'] = pos['base_entry_price'] * (1 + PYRAMID_TRIGGER_PCT)
            
            still_open.append(pos)
            
        open_positions = still_open
        
        # Sadece 1 işlem açık kalsın (kasa yönetimini bozmamak için)
        if len(group) > 0 and len(open_positions) < 1:
            req_thresh = RECOVERY_THRESHOLD if in_recovery_mode else OPTIMAL_THRESHOLD
            valid_candidates = group[(group['macro_ok'] == True) & (group['ai_prob'] > req_thresh)]
            
            if len(valid_candidates) > 0:
                best_candidate = valid_candidates.sort_values(by='ai_prob', ascending=False).iloc[0]
                
                entry_price = best_candidate['close']
                bet_pct = BASE_BET_FRACTION * 2 if in_recovery_mode else BASE_BET_FRACTION
                margin_usd = balance * bet_pct 
                
                open_positions.append({
                    'symbol': best_candidate['symbol'],
                    'entry_time': ts,
                    'base_entry_price': entry_price,
                    'avg_entry_price': entry_price,
                    'sl_price': entry_price * (1 - INITIAL_SL_PCT),
                    'margin_usd': margin_usd,
                    'pyramid_level': 0,
                    'bet_mode': "RECOVERY" if in_recovery_mode else "NORMAL"
                })

    for pos in open_positions:
        sym = pos['symbol']
        last_row = test_df[test_df['symbol'] == sym].iloc[-1]
        exit_price = last_row['close']
        pnl_pct = (exit_price - pos['avg_entry_price']) / pos['avg_entry_price']
        net_pnl_pct = pnl_pct - (ENTRY_FEE + TP_FEE)
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
    pyramided_trades = len(trades_df[trades_df['pyramid_level'] > 0])
    level2_trades = len(trades_df[trades_df['pyramid_level'] > 1])
    
    print("\nSon 10 İşlem (Pyramiding Detaylı):")
    print(trades_df[['entry_time', 'symbol', 'status', 'pyramid_level', 'pnl_usd', 'balance_after']].tail(10))
    
    print(f"\n🏆 V66 PYRAMIDING (TREND SÖRFÜ) ÖZETİ 🏆")
    print(f"Test Periyodu: 2025-2026 (1.5 Yıl) | Pariteler: Top 5")
    print(f"İlk Giriş: %{BASE_BET_FRACTION*100} | Piramit Ekleme: +%{PYRAMID_BET_FRACTION*100}")
    print(f"Başlangıç Bakiyesi: ${START_BALANCE:.2f}")
    print(f"Bitiş Bakiyesi: ${balance:.2f} (x{balance/START_BALANCE:.2f} KATLAMA)")
    print(f"Toplam İşlem: {len(trades_df)}")
    print(f"Piramitlenen (Eklenen) İşlem: {pyramided_trades} (Level 2'ye Çıkan: {level2_trades})")
    print(f"Kazanma Oranı (Win Rate): %{win_rate:.1f}")
    print(f"Ortalama İşlem Kârı (Beklenen Değer): ${trades_df['pnl_usd'].mean():.2f}")

if __name__ == "__main__":
    run_v66_pyramiding()
