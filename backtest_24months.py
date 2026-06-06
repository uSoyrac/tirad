import ccxt
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import logging
import ta
import warnings

# Suppress pandas warnings
warnings.filterwarnings('ignore')

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("backtest_24m")

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
        except Exception as e:
            print(f"Fetch error for {symbol}: {e}")
            break
            
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def run_24m_backtest():
    print("=" * 60)
    print("🚀 24 AYLIK TOP-20 KÜMÜLATİF HİBRİT BACKTEST (META-REJİM) - OPTİMİZE")
    print("=" * 60)
    
    symbols = get_top_20_coins()
    print(f"Top 20 Coinler: {', '.join(symbols)}")
    
    total_trades = 0
    total_hybrid_pnl = 0
    ignition_trades = 0
    static_trades = 0
    
    for symbol in symbols:
        df = fetch_24m_ohlcv(symbol)
        if df.empty or len(df) < 200:
            print(f"[-] {symbol} için yeterli veri yok.")
            continue
            
        print(f"[+] {symbol}: {len(df)} mum (4s) vektörel analiz ediliyor...")
        
        # --- VECTORIZED PRE-CALCULATION ---
        # 1. Kinetik Enerji & Ignition
        df['velocity'] = df['close'].diff()
        df['kinetic_energy'] = df['volume'] * (df['velocity']**2)
        df['ke_mean_10'] = df['kinetic_energy'].rolling(10).mean()
        df['ke_std_10'] = df['kinetic_energy'].rolling(10).std()
        df['is_ignition'] = (df['kinetic_energy'] > (df['ke_mean_10'] + 3 * df['ke_std_10'])) & (df['kinetic_energy'] > 0)
        df['ignition_dir'] = np.where(df['velocity'] > 0, "LONG", "SHORT")
        
        # 2. Termodinamik Faz
        df['temperature'] = df['close'].rolling(20).std()
        df['flow'] = abs(df['close'] - df['close'].shift(20))
        df['wick_size'] = (df['high'] - np.maximum(df['close'], df['open'])) + (np.minimum(df['close'], df['open']) - df['low'])
        df['body_size'] = abs(df['close'] - df['open']) + 1e-8
        df['toxicity'] = (df['wick_size'] / df['body_size']).rolling(10).mean()
        
        temp_mean = df['temperature'].mean()
        flow_mean = df['flow'].mean()
        df['is_gas'] = ((df['temperature'] > temp_mean * 1.5) & (df['flow'] < flow_mean)) | (df['toxicity'] > 3.0)
        
        # 3. Trend & SL (Basitleştirilmiş ATR + EMA)
        df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)
        df['ema250'] = ta.trend.ema_indicator(df['close'], window=250)
        df['trend_dir'] = np.where(df['close'] > df['ema250'], "LONG", "SHORT")
        df['sl_price'] = np.where(df['trend_dir'] == "LONG", df['close'] - df['atr']*2, df['close'] + df['atr']*2)
        
        # --- ITERATIVE SIMULATION ---
        i = 250
        while i < len(df) - 5:
            # Sinyal Kontrolü
            if df['is_gas'].iloc[i]:
                i += 1
                continue
                
            is_ignition = df['is_ignition'].iloc[i]
            if is_ignition:
                entry_dir = df['ignition_dir'].iloc[i]
            else:
                entry_dir = df['trend_dir'].iloc[i]
                
            entry_price = df['close'].iloc[i]
            initial_sl = df['sl_price'].iloc[i]
            risk = abs(entry_price - initial_sl)
            
            if risk < 1e-8:
                i += 1
                continue
                
            total_trades += 1
            
            if is_ignition:
                ignition_trades += 1
                current_sl = initial_sl
                pnl = 0
                
                for j in range(i+1, len(df)):
                    curr_candle = df.iloc[j]
                    if entry_dir == "LONG" and curr_candle['low'] <= current_sl:
                        pnl = (current_sl - entry_price) / risk
                        break
                    elif entry_dir == "SHORT" and curr_candle['high'] >= current_sl:
                        pnl = (entry_price - current_sl) / risk
                        break
                        
                    # Basit Maximizer Mantığı (Vectorized)
                    # Yerçekimi ivmesi azalırsa sık
                    accel = df['velocity'].iloc[j] - df['velocity'].iloc[j-1]
                    accel_dir = accel if entry_dir == "LONG" else -accel
                    gravity = abs(curr_candle['close'] - df['ema250'].iloc[j]) / df['atr'].iloc[j]
                    
                    base_dist = df['atr'].iloc[j] * 2.0
                    if accel_dir < 0 and gravity > 3.0:
                        multiplier = max(0.1, 1.0 - (abs(accel_dir) * 0.1))
                        base_dist *= multiplier
                        
                    proposed_sl = curr_candle['close'] - base_dist if entry_dir == "LONG" else curr_candle['close'] + base_dist
                    if entry_dir == "LONG": current_sl = max(current_sl, proposed_sl)
                    else: current_sl = min(current_sl, proposed_sl)
                else:
                    last_p = df['close'].iloc[-1]
                    pnl = (last_p - entry_price) / risk if entry_dir == "LONG" else (entry_price - last_p) / risk
                    
                total_hybrid_pnl += pnl
                i = j + 1
            else:
                static_trades += 1
                tp3 = entry_price + (risk * 3.0) if entry_dir == "LONG" else entry_price - (risk * 3.0)
                pnl = 0
                
                for j in range(i+1, len(df)):
                    curr_candle = df.iloc[j]
                    if entry_dir == "LONG":
                        if curr_candle['low'] <= initial_sl:
                            pnl = -1.0
                            break
                        elif curr_candle['high'] >= tp3:
                            pnl = 3.0
                            break
                    else:
                        if curr_candle['high'] >= initial_sl:
                            pnl = -1.0
                            break
                        elif curr_candle['low'] <= tp3:
                            pnl = 3.0
                            break
                else:
                    last_p = df['close'].iloc[-1]
                    pnl = (last_p - entry_price) / risk if entry_dir == "LONG" else (entry_price - last_p) / risk
                    
                total_hybrid_pnl += pnl
                i = j + 1
                
    print("\n" + "=" * 60)
    print("📊 24 AYLIK TOP-20 HİBRİT META-SİSTEM SONUÇLARI (R Çarpanı)")
    print("=" * 60)
    print(f"Toplam İşlem Sayısı: {total_trades}")
    print(f"Statik İşlemler (Testere/Normal) : {static_trades} işlem")
    print(f"Dinamik İşlemler (Momentum Ateşleme) : {ignition_trades} işlem")
    print(f"🏆 Toplam Net PnL (Hibrit Sistem)  : {total_hybrid_pnl:.2f} R")
    print("=" * 60)
    
    if total_trades > 0:
        print(f"Aylık Ortalama Getiri : {(total_hybrid_pnl / 24):.2f} R")
        print("Not: Risk R=Yüzde 1 Bakiye ise, aylık getiri % cinsinden yaklaşık bu değere eşittir.")

if __name__ == "__main__":
    run_24m_backtest()
