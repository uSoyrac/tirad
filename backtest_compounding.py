import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import ta
import warnings
import json

warnings.filterwarnings('ignore')

def get_top_20_coins():
    exchange = ccxt.binance({'options': {'defaultType': 'future'}})
    tickers = exchange.fetch_tickers()
    usdt_tickers = [t for sym, t in tickers.items() if '/USDT' in sym]
    usdt_tickers.sort(key=lambda x: float(x.get('quoteVolume', 0)), reverse=True)
    return [t['symbol'] for t in usdt_tickers[:20]]

def fetch_24m_ohlcv(symbol: str):
    exchange = ccxt.binance({'options': {'defaultType': 'future'}})
    two_years_ago = int((datetime.now() - timedelta(days=730)).timestamp() * 1000)
    all_ohlcv = []
    current_since = two_years_ago
    
    while True:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, '4h', since=current_since, limit=1000)
            if not ohlcv:
                break
            all_ohlcv.extend(ohlcv)
            current_since = ohlcv[-1][0] + 1
            if len(ohlcv) < 1000:
                break
        except Exception:
            break
            
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def run_compounding_backtest():
    symbols = get_top_20_coins()
    trades = []
    
    for symbol in symbols:
        print(f"[*] {symbol} simüle ediliyor...")
        df = fetch_24m_ohlcv(symbol)
        if df.empty or len(df) < 250:
            continue
            
        df['temperature'] = df['close'].rolling(20).std()
        df['flow'] = abs(df['close'] - df['close'].shift(20))
        df['wick_size'] = (df['high'] - np.maximum(df['close'], df['open'])) + (np.minimum(df['close'], df['open']) - df['low'])
        df['body_size'] = abs(df['close'] - df['open']) + 1e-8
        df['toxicity'] = (df['wick_size'] / df['body_size']).rolling(10).mean()
        
        temp_mean = df['temperature'].mean()
        flow_mean = df['flow'].mean()
        df['is_gas'] = ((df['temperature'] > temp_mean * 1.5) & (df['flow'] < flow_mean)) | (df['toxicity'] > 3.0)
        
        df['ema250'] = ta.trend.ema_indicator(df['close'], window=250)
        df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)
        df['trend_dir'] = np.where(df['close'] > df['ema250'], "LONG", "SHORT")
        df['sl_price'] = np.where(df['trend_dir'] == "LONG", df['close'] - df['atr']*2.0, df['close'] + df['atr']*2.0)
        
        df['velocity'] = df['close'].diff()
        df['accel'] = df['velocity'].diff()
        
        i = 250
        while i < len(df) - 5:
            if df['is_gas'].iloc[i]:
                i += 1
                continue
                
            entry_dir = df['trend_dir'].iloc[i]
            entry_price = df['close'].iloc[i]
            initial_sl = df['sl_price'].iloc[i]
            entry_time = df['timestamp'].iloc[i]
            risk = abs(entry_price - initial_sl)
            
            if risk < 1e-8:
                i += 1
                continue
                
            current_sl = initial_sl
            pnl = 0
            exit_time = None
            
            for j in range(i+1, len(df)):
                curr = df.iloc[j]
                
                if entry_dir == "LONG" and curr['low'] <= current_sl:
                    pnl = (current_sl - entry_price) / risk
                    exit_time = curr['timestamp']
                    break
                elif entry_dir == "SHORT" and curr['high'] >= current_sl:
                    pnl = (entry_price - current_sl) / risk
                    exit_time = curr['timestamp']
                    break
                    
                atr_j = df['atr'].iloc[j]
                accel_j = df['accel'].iloc[j]
                
                if entry_dir == "LONG":
                    if (curr['close'] > entry_price) and accel_j < 0:
                        proposed_sl = curr['close'] - (atr_j * 1.0)
                        current_sl = max(current_sl, proposed_sl)
                else:
                    if (curr['close'] < entry_price) and accel_j > 0:
                        proposed_sl = curr['close'] + (atr_j * 1.0)
                        current_sl = min(current_sl, proposed_sl)
            else:
                last_p = df['close'].iloc[-1]
                pnl = (last_p - entry_price) / risk if entry_dir == "LONG" else (entry_price - last_p) / risk
                exit_time = df['timestamp'].iloc[-1]
                
            trades.append({
                'symbol': symbol,
                'entry_time': entry_time,
                'exit_time': exit_time,
                'direction': entry_dir,
                'pnl_R': pnl
            })
            i = j + 1

    # --- PORTFÖY SİMÜLASYONU ---
    # İşlemleri kapanış zamanına göre sırala
    trades.sort(key=lambda x: x['exit_time'])
    
    balance = 100.0  # Başlangıç $100
    RISK_PER_TRADE = 0.02  # Her işlemde kasanın %2'si risk edilir (1R = %2 Kasa)
    
    weekly_stats = {}
    
    for t in trades:
        # PnL Hesabı
        trade_profit_usd = (balance * RISK_PER_TRADE) * t['pnl_R']
        balance += trade_profit_usd
        
        # Hafta gruplaması (Yıl-Hafta)
        year, week, _ = t['exit_time'].isocalendar()
        week_key = f"{year}-W{week:02d}"
        
        if week_key not in weekly_stats:
            weekly_stats[week_key] = {
                'start_balance': balance - trade_profit_usd,
                'end_balance': balance,
                'trades': 0,
                'wins': 0,
                'losses': 0,
                'total_R': 0.0
            }
        
        ws = weekly_stats[week_key]
        ws['end_balance'] = balance
        ws['trades'] += 1
        ws['total_R'] += t['pnl_R']
        if t['pnl_R'] > 0:
            ws['wins'] += 1
        else:
            ws['losses'] += 1
            
    # Markdown Çıktısı Hazırla
    md_out = "# BİLEŞİK GETİRİ (COMPOUNDING) HAFTALIK RAPORU\n\n"
    md_out += f"**Başlangıç Bakiyesi:** $100.00\n"
    md_out += f"**Toplam İşlem:** {len(trades)}\n"
    md_out += f"**Bitiş Bakiyesi:** ${balance:,.2f}\n"
    md_out += f"**Risk Yönetimi:** İşlem başı %2 risk (1R = Kasanın %2'si)\n\n"
    
    md_out += "| Hafta | İşlem Sayısı | Win/Loss | O Hafta Kazanılan R | Dönem Sonu Bakiye |\n"
    md_out += "|---|---|---|---|---|\n"
    
    for wk in sorted(weekly_stats.keys()):
        ws = weekly_stats[wk]
        md_out += f"| {wk} | {ws['trades']} | {ws['wins']}W / {ws['losses']}L | {ws['total_R']:+.2f} R | **${ws['end_balance']:,.2f}** |\n"
        
    with open('/Users/uygar/.gemini/antigravity/brain/27157ebd-165c-4285-a7e7-c36f31bcf8c4/compounding_report.md', 'w') as f:
        f.write(md_out)
        
    print(f"Toplam İşlem: {len(trades)}")
    print(f"Final Bakiye: ${balance:,.2f}")
    print("Rapor compounding_report.md dosyasına yazıldı.")

if __name__ == "__main__":
    run_compounding_backtest()
