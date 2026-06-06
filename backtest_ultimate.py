import ccxt
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import logging
import ta
import warnings

warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.WARNING)

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

def run_ultimate_backtest():
    print("=" * 60)
    print("💎 ULTIMATE SENTEZ: 4H META-GİRİŞ + BALİSTİK ÇIKIŞ")
    print("=" * 60)
    
    symbols = get_top_20_coins()
    
    total_trades = 0
    total_pnl_R = 0
    
    for symbol in symbols:
        df = fetch_24m_ohlcv(symbol)
        if df.empty or len(df) < 250:
            continue
            
        print(f"[*] {symbol}: {len(df)} mum (4s) sentezleniyor...")
        
        # --- 4H Meta-Regime (Giriş İçin) ---
        df['temperature'] = df['close'].rolling(20).std()
        df['flow'] = abs(df['close'] - df['close'].shift(20))
        df['wick_size'] = (df['high'] - np.maximum(df['close'], df['open'])) + (np.minimum(df['close'], df['open']) - df['low'])
        df['body_size'] = abs(df['close'] - df['open']) + 1e-8
        df['toxicity'] = (df['wick_size'] / df['body_size']).rolling(10).mean()
        
        temp_mean = df['temperature'].mean()
        flow_mean = df['flow'].mean()
        # "Gas" fazı iptal filtresi (Toksik piyasa)
        df['is_gas'] = ((df['temperature'] > temp_mean * 1.5) & (df['flow'] < flow_mean)) | (df['toxicity'] > 3.0)
        
        # Trend Filter
        df['ema250'] = ta.trend.ema_indicator(df['close'], window=250)
        df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)
        df['trend_dir'] = np.where(df['close'] > df['ema250'], "LONG", "SHORT")
        
        df['sl_price'] = np.where(df['trend_dir'] == "LONG", df['close'] - df['atr']*2.0, df['close'] + df['atr']*2.0)
        
        # --- Balistik Parametreler (Çıkış İçin) ---
        df['velocity'] = df['close'].diff()
        df['accel'] = df['velocity'].diff()  # İvme: Fiyat hızı artıyor mu düşüyor mu?
        df['kinetic_energy'] = df['volume'] * (df['velocity']**2)
        df['avg_vol'] = df['volume'].rolling(50).mean()
        
        i = 250
        while i < len(df) - 5:
            # Gas fazında işlem yasak (Sadece sağlam trendlerde giriyoruz)
            if df['is_gas'].iloc[i]:
                i += 1
                continue
                
            entry_dir = df['trend_dir'].iloc[i]
            entry_price = df['close'].iloc[i]
            initial_sl = df['sl_price'].iloc[i]
            risk = abs(entry_price - initial_sl)
            
            if risk < 1e-8:
                i += 1
                continue
                
            total_trades += 1
            current_sl = initial_sl
            pnl = 0
            
            # --- RIDING THE TREND (Ballistic Exit) ---
            for j in range(i+1, len(df)):
                curr = df.iloc[j]
                
                # SL Vuruldu mu?
                if entry_dir == "LONG" and curr['low'] <= current_sl:
                    pnl = (current_sl - entry_price) / risk
                    break
                elif entry_dir == "SHORT" and curr['high'] >= current_sl:
                    pnl = (entry_price - current_sl) / risk
                    break
                    
                # BALİSTİK ÇIKIŞ (İvme Azalması + Kinetik Tükeniş)
                atr_j = df['atr'].iloc[j]
                accel_j = df['accel'].iloc[j]
                
                if entry_dir == "LONG":
                    # Kârda isek ve İvme (Acceleration) aniden terse döndüyse (Mermi tepeye ulaştı)
                    if (curr['close'] > entry_price) and accel_j < 0:
                        # Kementi son 1 ATR'ye daralt (Tepede kilitle)
                        proposed_sl = curr['close'] - (atr_j * 1.0)
                        current_sl = max(current_sl, proposed_sl)
                else:
                    if (curr['close'] < entry_price) and accel_j > 0:
                        proposed_sl = curr['close'] + (atr_j * 1.0)
                        current_sl = min(current_sl, proposed_sl)
                        
            else:
                last_p = df['close'].iloc[-1]
                pnl = (last_p - entry_price) / risk if entry_dir == "LONG" else (entry_price - last_p) / risk
                
            total_pnl_R += pnl
            i = j + 1
            
    print("\n" + "=" * 60)
    print("📊 ULTIMATE SENTEZ KÜMÜLATİF SONUÇLARI (R Çarpanı)")
    print("=" * 60)
    print(f"Toplam İşlem: {total_trades}")
    print(f"🏆 Toplam Net PnL : {total_pnl_R:.2f} R")
    print(f"Aylık Ortalama   : {(total_pnl_R / 24):.2f} R")
    print("=" * 60)

if __name__ == "__main__":
    run_ultimate_backtest()
