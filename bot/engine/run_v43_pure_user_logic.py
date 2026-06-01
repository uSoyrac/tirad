import pandas as pd
import numpy as np
import os

COMMISSION = 0.0004
SLIPPAGE = 0.0005
START_BALANCE = 100.0

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

def run_v43_pure_user_logic():
    print("V43 PURE MTF (Senin Manuel Sistemin) Otomatize Ediliyor...")
    print("Kaldıraç: 10x, Kâr Hedefi: +%20 ROE, Zarar Kes: -%5 ROE")
    
    combined_df = load_and_merge_mtf_data()
    
    # 2024 Yılı Boğa Piyasası
    bull_df = combined_df[(combined_df['ts'] >= '2024-01-01') & (combined_df['ts'] < '2025-01-01')].copy()
    
    balance = START_BALANCE
    open_positions = []
    trade_history = []
    
    grouped = bull_df.groupby('ts')
    tp_pct_target = 0.02  # 10x kaldıraçta %20 ROE
    sl_pct_target = 0.005 # 10x kaldıraçta -%5 ROE
    
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
                pos['exit_price'] = exit_price
                pos['exit_time'] = ts
                pos['pnl_usd'] = pnl_usd
                pos['roe_pct'] = (pnl_usd / pos['margin_usd']) * 100
                pos['status'] = "TP_HIT (+%20 ROE)" if hit_tp else "SL_HIT (-%5 ROE)"
                pos['balance_after'] = balance
                trade_history.append(pos)
            else:
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
        
        if len(group) > 0 and len(open_positions) < 1:
            for i, row in group.reset_index(drop=True).iterrows():
                # SENİN MANUEL SİSTEMİN KODLANMIŞ HALİ:
                # 1. Trend: ADX > 20 (Trend var)
                # 2. Bollinger Bandı: Fiyat üst banda yapışmış (Close > Upper Band)
                # 3. Hacim: Volume Spike (Anormal hacim patlaması)
                # 4. Ajan 4 (Büyük Resim): 1H ve 4H trend EMA 50'nin üstünde
                
                trend_ok = row['adx_14'] > 20
                bb_breakout = row['close'] > row['bb_upper']
                vol_spike = row['vol_spike'] == 1
                mtf_1h_bullish = row['close_1h'] > row['ema_50_1h']
                mtf_4h_bullish = row['close_4h'] > row['ema_50_4h']
                
                if trend_ok and bb_breakout and vol_spike and mtf_1h_bullish and mtf_4h_bullish:
                    entry_price = row['close']
                    tp_price = entry_price * (1 + tp_pct_target)
                    sl_price = entry_price * (1 - sl_pct_target)
                    
                    # Bileşik Getiri (Kasandaki tüm parayı %100 marjin ile basıyorsun, 10x)
                    margin_usd = balance
                    open_positions.append({
                        'symbol': row['symbol'],
                        'entry_time': ts,
                        'entry_price': entry_price,
                        'sl_price': sl_price,
                        'tp_price': tp_price,
                        'margin_usd': margin_usd
                    })
                    break # Aynı anda tek işleme gir

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
        pos['balance_after'] = balance
        trade_history.append(pos)
        
    trades_df = pd.DataFrame(trade_history)
    
    print("\nSimülasyon Tamamlandı! Senin Sisteminin 2024 Boğasındaki Performansı...\n")
    
    if len(trades_df) == 0:
         print("Sistem hiç işlem açmadı!")
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
    
    print("\n--- V43 PURE USER MTF 2024 BOĞA KÖR TEST ÖZETİ ---")
    print(f"Başlangıç Bakiyesi: $100.00")
    print(f"Bitiş Bakiyesi: ${balance:.2f} (x{balance/100:.2f} KATLAMA)")
    print(f"Net Kâr: +%{(balance - 100.0):.1f}")
    print(f"Toplam İşlem: {len(trades_df)}")
    print(f"Kazanma Oranı (Win Rate): %{win_rate:.1f}")

if __name__ == "__main__":
    run_v43_pure_user_logic()
