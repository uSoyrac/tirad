#!/usr/bin/env python3
import sys, os
import pandas as pd
import numpy as np
import ccxt
import warnings
import ta

warnings.filterwarnings("ignore")
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "uyg", "src"))
from dynamic_optimizer import run_orp_dynamic

COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]

def get_binance_history_fast(exchange, symbol, timeframe, limit=1000):
    try:
        recent_ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        if not recent_ohlcv: return None
        df = pd.DataFrame(recent_ohlcv, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
        df['ts'] = pd.to_datetime(df['ts'], unit='ms')
        return df
    except Exception as e:
        print(f"[{symbol}] Hata: {e}")
        return None

def calculate_supertrend(df, period=10, multiplier=3):
    high = df['high']
    low = df['low']
    close = df['close']
    
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.DataFrame({'tr1': tr1, 'tr2': tr2, 'tr3': tr3}).max(axis=1)
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    
    hl2 = (high + low) / 2
    basic_ub = hl2 + (multiplier * atr)
    basic_lb = hl2 - (multiplier * atr)
    
    ub = basic_ub.copy().values
    lb = basic_lb.copy().values
    c = close.values
    
    st = np.zeros(len(df))
    t = np.ones(len(df))
    
    for i in range(1, len(df)):
        if ub[i] > ub[i-1] and c[i-1] <= ub[i-1]: ub[i] = ub[i-1]
        if lb[i] < lb[i-1] and c[i-1] >= lb[i-1]: lb[i] = lb[i-1]
            
        if c[i] > ub[i-1]: t[i] = 1
        elif c[i] < lb[i-1]: t[i] = -1
        else: t[i] = t[i-1]
            
        if t[i] == 1: st[i] = lb[i]
        else: st[i] = ub[i]
            
    df['atr'] = atr
    df['st'] = st
    df['st_trend'] = t
    return df

def get_trade_result(df, start_idx, trend, entry, atr):
    end_idx = min(start_idx + 60, len(df))
    slice_ahead = df.iloc[start_idx:end_idx]
    
    # EN ÇOK PARA KAZANDIRAN ORAN: 2.0 ATR STOP / 4.0 ATR KÂR
    sl = entry - (atr * 2.0) if trend == 1 else entry + (atr * 2.0)
    tp = entry + (atr * 4.0) if trend == 1 else entry - (atr * 4.0)
    risk_dist = abs(entry - sl)
    
    filled = False
    for _, row in slice_ahead.iterrows():
        high, low = row["high"], row["low"]
        if trend == 1:
            if not filled and low <= entry: filled = True
            if filled:
                if low <= sl: return -1.0, risk_dist/entry*100
                if high >= tp: return 2.0, risk_dist/entry*100
        else:
            if not filled and high >= entry: filled = True
            if filled:
                if high >= sl: return -1.0, risk_dist/entry*100
                if low <= tp: return 2.0, risk_dist/entry*100
    return 0.0, 0.0

def run_real_binance_test():
    print("="*70)
    print(" 🚀 MAKSİMUM KÂR (PARA BASMA) TESTİ: TOP 5 COİN - SON 3 AY 🚀")
    print("="*70)
    exchange = ccxt.binance({'enableRateLimit': True})
    
    test_bars = 540 # 3 months in 4H
    all_trades = []
    
    stats = {"total_signals": 0, "rej_adx": 0}
    
    for coin in COINS:
        symbol = f"{coin}/USDT"
        print(f"🔄 Taranıyor: {symbol}...", flush=True)
        df = get_binance_history_fast(exchange, symbol, "4h", limit=1000)
        if df is None or len(df) < 850: continue
            
        df = calculate_supertrend(df, 10, 3)
        
        adx_ind = ta.trend.ADXIndicator(df["high"], df["low"], df["close"], window=14)
        df["adx"] = adx_ind.adx()
            
        for i in range(len(df) - test_bars, len(df) - 60):
            trend = df["st_trend"].iloc[i-1]
            prev_trend = df["st_trend"].iloc[i-2]
            close = df["close"].iloc[i-1]
            low = df["low"].iloc[i-1]
            high = df["high"].iloc[i-1]
            st = df["st"].iloc[i-1]
            atr = df["atr"].iloc[i-1]
            
            adx = df["adx"].iloc[i-1]
            
            is_signal = False
            if trend == 1:
                if prev_trend == -1: is_signal = True
                elif low <= st + (atr * 0.5): is_signal = True
            else:
                if prev_trend == 1: is_signal = True
                elif high >= st - (atr * 0.5): is_signal = True
                
            if not is_signal: continue
            stats["total_signals"] += 1
            
            # TEK FİLTRE: ADX > 25 (Gecikmeli tüm filtreler kaldırıldı)
            if adx < 25:
                stats["rej_adx"] += 1
                continue
                
            result_r, sl_pct = get_trade_result(df, i, trend, close, atr)
            if result_r != 0.0:
                all_trades.append({"coin": coin, "date": df.iloc[i]['ts'], "r_mult": result_r, "sl_pct": sl_pct})
                
    all_trades = sorted(all_trades, key=lambda x: x["date"])
    print("\n✅ BINANCE TARAMASI TAMAMLANDI!")
    print(f"Toplam Fırsat     : {stats['total_signals']}")
    print(f"Zayıf Trend Çöpe  : {stats['rej_adx']} (ADX < 25)")
    print(f"Kusursuz İşlem    : {len(all_trades)}")
    
    if not all_trades: return
    
    wins = sum(1 for t in all_trades if t["r_mult"] > 0)
    win_rate = (wins / len(all_trades)) * 100 if all_trades else 0
    print(f"Başarılı İşlem: {wins} | Başarısız: {len(all_trades)-wins}")
    print(f"📊 GERÇEK PİYASA WIN RATE: %{win_rate:.1f} (R/R 2.0)\n")
    
    # BİLEŞİK FAİZİ ŞAHLANDIRAN AGRESİF ORP AYARLARI
    params = {
        "cycle_target_pct": 0.15,
        "recovery_factor": 1.5,
        "max_risk_cap": 0.20,
        "base_risk_pct": 0.05,
        "max_leverage": 15.0,
        "dynamic_recovery": True,
        "dd_scaling": True,
        "start_capital": 100.0
    }
    
    res = run_orp_dynamic(all_trades, params)
    
    print("="*70)
    print(" 💵 MAKSİMUM KÂR SONUCU: $100 KASA BÜYÜMESİ (ORP) 💵")
    print("="*70)
    print(f"Başlangıç Kasası : $100.00")
    print(f"3 Ay Sonraki Kasa: ${res['final_eq']:,.2f}  (~{res['final_eq']*33:,.0f} TL)")
    print(f"Net Büyüme Oranı : %{((res['final_eq']/100)-1)*100:.1f}")
    print(f"Büyüme Çarpanı   : {res['total_growth']:.2f}x")
    print(f"Maksimum Drawdown: %{res['max_drawdown']:.1f}")
    print(f"Tamamlanan Döngü : {res['steps_achieved']}")
    print("="*70)

if __name__ == "__main__":
    run_real_binance_test()
