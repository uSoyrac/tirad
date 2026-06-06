import ccxt
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import logging
import warnings

warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("backtest_predator")

def get_top_20_coins():
    exchange = ccxt.binance({'options': {'defaultType': 'future'}})
    tickers = exchange.fetch_tickers()
    usdt_tickers = [t for sym, t in tickers.items() if '/USDT' in sym]
    usdt_tickers.sort(key=lambda x: float(x.get('quoteVolume', 0)), reverse=True)
    return [t['symbol'] for t in usdt_tickers[:20]]

def fetch_6m_15m_ohlcv(symbol: str):
    exchange = ccxt.binance({'options': {'defaultType': 'future'}})
    six_months_ago = int((datetime.now() - timedelta(days=180)).timestamp() * 1000)
    all_ohlcv = []
    current_since = six_months_ago
    
    while True:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, '15m', since=current_since, limit=1000)
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

def run_predator_backtest():
    print("=" * 60)
    print("🐺 PREDATÖR PUSUSU & BALİSTİK ÇIKIŞ: 15 DAKİKALIK BACKTEST")
    print("=" * 60)
    
    symbols = get_top_20_coins()
    
    total_trades = 0
    total_pnl_R = 0
    
    from bot.engine.microstructure import MicrostructureAnalyzer
    import ta
    
    for symbol in symbols:
        df = fetch_6m_15m_ohlcv(symbol)
        if df.empty or len(df) < 200:
            continue
            
        print(f"[*] {symbol}: {len(df)} mum (15m) taranıyor...")
        
        # --- Vectorized Calculations ---
        df['vol_mean_20'] = df['volume'].rolling(20).mean()
        df['is_vol_climax'] = df['volume'] > df['vol_mean_20'] * 2.5
        
        df['lowest_20'] = df['low'].rolling(20).min().shift(1)
        df['highest_20'] = df['high'].rolling(20).max().shift(1)
        
        df['is_sweep_low'] = df['low'] <= df['lowest_20']
        df['is_sweep_high'] = df['high'] >= df['highest_20']
        
        df['lower_wick'] = np.minimum(df['close'], df['open']) - df['low']
        df['upper_wick'] = df['high'] - np.maximum(df['close'], df['open'])
        df['total_range'] = df['high'] - df['low'] + 1e-8
        
        df['ambush_long'] = df['is_vol_climax'] & df['is_sweep_low'] & ((df['lower_wick'] / df['total_range']) > 0.5) & (df['close'] > df['open'])
        df['ambush_short'] = df['is_vol_climax'] & df['is_sweep_high'] & ((df['upper_wick'] / df['total_range']) > 0.5) & (df['close'] < df['open'])
        
        df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)
        df['accel'] = df['close'].diff().diff()
        
        # --- Trade Loop ---
        i = 50
        while i < len(df) - 5:
            if not (df['ambush_long'].iloc[i] or df['ambush_short'].iloc[i]):
                i += 1
                continue
                
            entry_dir = "LONG" if df['ambush_long'].iloc[i] else "SHORT"
            entry_price = df['close'].iloc[i]
            
            # SL is tightly set behind the swept wick
            initial_sl = df['low'].iloc[i] * 0.999 if entry_dir == "LONG" else df['high'].iloc[i] * 1.001
            risk = abs(entry_price - initial_sl)
            
            if risk < 1e-8:
                i += 1
                continue
                
            total_trades += 1
            current_sl = initial_sl
            pnl = 0
            
            # Ballistic Ride
            for j in range(i+1, len(df)):
                curr = df.iloc[j]
                
                # SL Hit?
                if entry_dir == "LONG" and curr['low'] <= current_sl:
                    pnl = (current_sl - entry_price) / risk
                    break
                elif entry_dir == "SHORT" and curr['high'] >= current_sl:
                    pnl = (entry_price - current_sl) / risk
                    break
                    
                # Break Even Snap
                if entry_dir == "LONG" and (curr['high'] - entry_price) / risk > 1.0 and current_sl < entry_price:
                    current_sl = entry_price
                elif entry_dir == "SHORT" and (entry_price - curr['low']) / risk > 1.0 and current_sl > entry_price:
                    current_sl = entry_price
                    
                # Ballistic Exit Logic
                atr_j = df['atr'].iloc[j]
                accel_j = df['accel'].iloc[j]
                
                if entry_dir == "LONG":
                    if accel_j < 0: # Momentum decreasing
                        proposed_sl = curr['close'] - (atr_j * 1.0)
                        current_sl = max(current_sl, proposed_sl)
                else:
                    if accel_j > 0:
                        proposed_sl = curr['close'] + (atr_j * 1.0)
                        current_sl = min(current_sl, proposed_sl)
            else:
                last_p = df['close'].iloc[-1]
                pnl = (last_p - entry_price) / risk if entry_dir == "LONG" else (entry_price - last_p) / risk
                
            total_pnl_R += pnl
            if pnl > 2.0:
                print(f"  🌊 [WIN] {symbol} {entry_dir} Dipten Yakalandı: {pnl:.1f} R Kazanç!")
                
            i = j + 1
            
    print("\n" + "=" * 60)
    print("📊 PREDATÖR PUSUSU (15M) KÜMÜLATİF SONUÇLARI (R Çarpanı)")
    print("=" * 60)
    print(f"Toplam Pusu İşlemi: {total_trades}")
    print(f"🏆 Toplam Net PnL : {total_pnl_R:.2f} R")
    print("=" * 60)

if __name__ == "__main__":
    run_predator_backtest()
