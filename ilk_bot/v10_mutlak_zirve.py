#!/usr/bin/env python3
import sys, os
import pandas as pd
import numpy as np
import warnings
import ta
import time
from itertools import product

warnings.filterwarnings("ignore")

COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]
TIMEFRAME = "4h"

# Grid Uzayı
ST_PERIODS = [10, 11, 12, 14]
ST_MULTIPLIERS = [3.0, 3.2, 3.5, 3.8, 4.0]
EMA_PERIODS = [100, 150, 200, 250]
TP_MULTIPLIERS = [2.0, 2.5, 3.0, 3.5, 4.0]
SL_MULTIPLIERS = [1.5, 2.0, 2.5]

def calculate_supertrend_fast(df, period, multiplier):
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    n = len(df)
    
    tr1 = high - low
    tr2 = np.zeros(n)
    tr3 = np.zeros(n)
    tr2[1:] = np.abs(high[1:] - close[:-1])
    tr3[1:] = np.abs(low[1:] - close[:-1])
    
    tr = np.maximum(tr1, np.maximum(tr2, tr3))
    
    atr = np.zeros(n)
    atr[0] = tr[0]
    alpha = 1.0 / period
    for i in range(1, n):
        atr[i] = alpha * tr[i] + (1 - alpha) * atr[i-1]
        
    hl2 = (high + low) / 2.0
    basic_ub = hl2 + (multiplier * atr)
    basic_lb = hl2 - (multiplier * atr)
    
    ub = basic_ub.copy()
    lb = basic_lb.copy()
    
    st = np.zeros(n)
    t = np.ones(n)
    
    for i in range(1, n):
        if ub[i] > ub[i-1] and close[i-1] <= ub[i-1]:
            ub[i] = ub[i-1]
        if lb[i] < lb[i-1] and close[i-1] >= lb[i-1]:
            lb[i] = lb[i-1]
            
        if close[i] > ub[i-1]:
            t[i] = 1
        elif close[i] < lb[i-1]:
            t[i] = -1
        else:
            t[i] = t[i-1]
            
        if t[i] == 1:
            st[i] = lb[i]
        else:
            st[i] = ub[i]
            
    return atr, st, t

def get_trade_result_fast(high_arr, low_arr, start_idx, trend, entry, atr, tp_mult, sl_mult):
    n = len(high_arr)
    end_idx = min(start_idx + 100, n)
    
    initial_sl = entry - (atr * sl_mult) if trend == 1 else entry + (atr * sl_mult)
    tp = entry + (atr * tp_mult) if trend == 1 else entry - (atr * tp_mult)
    
    risk_dist = abs(entry - initial_sl)
    rr = tp_mult / sl_mult
    
    be_dist = risk_dist * 1.25
    be_trigger = entry + be_dist if trend == 1 else entry - be_dist
    
    current_sl = initial_sl
    is_breakeven = False
    filled = False
    
    for i in range(start_idx, end_idx):
        h = high_arr[i]
        l = low_arr[i]
        
        if trend == 1:
            if not filled and l <= entry: filled = True
            if filled:
                if h >= tp: return rr, risk_dist/entry*100
                if h >= be_trigger and not is_breakeven:
                    current_sl = entry
                    is_breakeven = True
                if l <= current_sl:
                    if is_breakeven: return 0.0, risk_dist/entry*100
                    return -1.0, risk_dist/entry*100
        else:
            if not filled and h >= entry: filled = True
            if filled:
                if l <= tp: return rr, risk_dist/entry*100
                if l <= be_trigger and not is_breakeven:
                    current_sl = entry
                    is_breakeven = True
                if h >= current_sl:
                    if is_breakeven: return 0.0, risk_dist/entry*100
                    return -1.0, risk_dist/entry*100
    return 0.0, 0.0

def simulate_orp_fast(trades):
    equity = 100.0
    target_eq = 100.0
    step = 0
    cycle = 0.15
    max_lev = 15.0
    cons_losses = 0
    
    for t in trades:
        # t = (date_ts, r_mult, sl_pct)
        r_mult = t[1]
        sl_pct = t[2]
        
        if cons_losses >= 3:
            a_b = 0.01; a_m = 0.05; a_r = 1.0
        else:
            a_b = 0.05; a_m = 0.20; a_r = 1.5
            
        while equity >= target_eq:
            step += 1
            target_eq = 100.0 * ((1.0 + cycle) ** step)
            
        delta = target_eq - equity
        base_amt = equity * a_b
        req_risk = max(base_amt, delta / a_r)
        
        sl_f = sl_pct / 100.0 if sl_pct > 0 else 0.015
        pos = req_risk / sl_f
        req_lev = pos / equity if equity > 0 else 999
        act_lev = min(req_lev, max_lev)
        act_risk = (act_lev * equity) * sl_f
        
        if act_risk > equity * a_m:
            act_risk = equity * a_m
            
        pnl = act_risk * r_mult
        equity += pnl
        if equity <= 0: return 0.0
        
        if r_mult > 0: cons_losses = 0
        elif r_mult < 0: cons_losses += 1
            
    return equity

def run_deepmind_optimizer():
    print("="*80)
    print(" 🧠 V10 DEEPMIND: EXHAUSTIVE GRID SEARCH OPTIMIZATION 🧠")
    print("="*80)
    
    print("📥 Veriler Belleğe Yükleniyor ve Ön Hesaplamalar Yapılıyor...")
    start_time = time.time()
    
    coins_data = {}
    
    for coin in COINS:
        csv_path = os.path.join(os.path.dirname(__file__), "..", "uyg", "src", "data", f"{coin}_USDT_{TIMEFRAME}.csv")
        if not os.path.exists(csv_path): continue
            
        df = pd.read_csv(csv_path)
        df["ts"] = pd.to_datetime(df["ts"])
        
        # Ön hesaplamalar
        emas = {}
        for ep in EMA_PERIODS:
            emas[ep] = ta.trend.EMAIndicator(df["close"], window=ep).ema_indicator().values
            
        supertrends = {}
        for sp in ST_PERIODS:
            for sm in ST_MULTIPLIERS:
                atr, st, t = calculate_supertrend_fast(df, sp, sm)
                supertrends[f"{sp}_{sm}"] = (atr, st, t)
                
        coins_data[coin] = {
            "dates": df["ts"].values,
            "close": df["close"].values,
            "low": df["low"].values,
            "high": df["high"].values,
            "emas": emas,
            "supertrends": supertrends,
            "n": len(df)
        }
        
    print(f"✅ Hazırlık Tamamlandı. İşlem Süresi: {time.time() - start_time:.2f} saniye")
    
    total_combinations = len(ST_PERIODS) * len(ST_MULTIPLIERS) * len(EMA_PERIODS) * len(TP_MULTIPLIERS) * len(SL_MULTIPLIERS)
    print(f"🚀 Taranacak Toplam Kombinasyon (Evren) Sayısı: {total_combinations}")
    
    best_equity = 0
    best_params = None
    best_trades_list = []
    
    comb_tested = 0
    start_search = time.time()
    
    # Dış Döngü: ST Period, ST Mult, EMA Period
    for sp in ST_PERIODS:
        for sm in ST_MULTIPLIERS:
            for ep in EMA_PERIODS:
                
                # Bu konfigürasyon için tüm geçerli sinyalleri topla
                valid_signals = []
                for coin, data in coins_data.items():
                    close_arr = data["close"]
                    low_arr = data["low"]
                    high_arr = data["high"]
                    ema_arr = data["emas"][ep]
                    atr_arr, st_arr, t_arr = data["supertrends"][f"{sp}_{sm}"]
                    dates_arr = data["dates"]
                    
                    for i in range(250, data["n"] - 100):
                        trend = t_arr[i-1]
                        prev_trend = t_arr[i-2]
                        close = close_arr[i-1]
                        low = low_arr[i-1]
                        high = high_arr[i-1]
                        st = st_arr[i-1]
                        atr = atr_arr[i-1]
                        ema200 = ema_arr[i-1]
                        
                        is_signal = False
                        if trend == 1:
                            if prev_trend == -1: is_signal = True
                            elif low <= st + (atr * 0.5): is_signal = True
                        else:
                            if prev_trend == 1: is_signal = True
                            elif high >= st - (atr * 0.5): is_signal = True
                            
                        if not is_signal: continue
                        
                        if trend == 1 and close < ema200: continue
                        if trend == -1 and close > ema200: continue
                            
                        valid_signals.append({
                            "coin": coin,
                            "start_idx": i,
                            "trend": trend,
                            "entry": close,
                            "atr": atr,
                            "date": pd.Timestamp(dates_arr[i]),
                            "high_arr": high_arr,
                            "low_arr": low_arr
                        })
                        
                # İç Döngü: Sadece bu sinyaller üzerinde TP ve SL taraması
                for tp_m in TP_MULTIPLIERS:
                    for sl_m in SL_MULTIPLIERS:
                        comb_tested += 1
                        
                        current_trades = []
                        for sig in valid_signals:
                            r_mult, sl_pct = get_trade_result_fast(
                                sig["high_arr"], sig["low_arr"], sig["start_idx"], 
                                sig["trend"], sig["entry"], sig["atr"], tp_m, sl_m
                            )
                            if r_mult != 0.0 or (r_mult == 0.0 and sl_pct > 0.0):
                                current_trades.append((sig["date"], r_mult, sl_pct))
                                
                        if not current_trades: continue
                        
                        current_trades.sort(key=lambda x: x[0])
                        eq = simulate_orp_fast(current_trades)
                        
                        if eq > best_equity:
                            best_equity = eq
                            best_params = (sp, sm, ep, tp_m, sl_m)
                            best_trades_list = current_trades
                            
                        if comb_tested % 300 == 0:
                            print(f"⏳ Taranan: {comb_tested}/{total_combinations} | Şu anki Zirve: ${best_equity:,.0f} | Geçen Süre: {time.time()-start_search:.1f}s")
                            
    print("="*80)
    print("🎯 DEEPMIND OPTİMİZASYONU BİTTİ!")
    print(f"🏆 MUTLAK MATEMATİKSEL ZİRVE BULUNDU:")
    print(f"   Supertrend Period : {best_params[0]}")
    print(f"   Supertrend Çarpan : {best_params[1]}")
    print(f"   Makro EMA Period  : {best_params[2]}")
    print(f"   Kâr Alma (TP)     : {best_params[3]} ATR")
    print(f"   Zarar Kes (SL)    : {best_params[4]} ATR")
    print(f"\n💰 NİHAİ 1 YIL SONU KASASI: ${best_equity:,.2f} (100 Dolardan)")
    
    wins = sum(1 for t in best_trades_list if t[1] > 0)
    losses = sum(1 for t in best_trades_list if t[1] < 0)
    be = sum(1 for t in best_trades_list if t[1] == 0)
    wr = (wins/(wins+losses)*100) if (wins+losses) > 0 else 0
    print(f"📊 İŞLEM ÖZETİ -> Toplam: {len(best_trades_list)} | Başarılı: {wins} | Başarısız: {losses} | Win Rate: %{wr:.1f}")

    # Aylık Rapor Çıktısı
    equity = 100.0
    target_eq = 100.0
    step = 0
    cycle = 0.15
    max_lev = 15.0
    cons_losses = 0
    monthly_data = {}
    
    for t in best_trades_list:
        month_key = t[0].strftime("%Y-%m")
        if month_key not in monthly_data:
            monthly_data[month_key] = {"start_eq": equity, "end_eq": equity, "trades": 0, "wins": 0, "losses": 0}
            
        monthly_data[month_key]["trades"] += 1
        
        if cons_losses >= 3:
            a_b = 0.01; a_m = 0.05; a_r = 1.0
        else:
            a_b = 0.05; a_m = 0.20; a_r = 1.5
            
        while equity >= target_eq:
            step += 1
            target_eq = 100.0 * ((1.0 + cycle) ** step)
            
        delta = target_eq - equity
        base_amt = equity * a_b
        req_risk = max(base_amt, delta / a_r)
        
        sl_f = t[2] / 100.0 if t[2] > 0 else 0.015
        pos = req_risk / sl_f
        req_lev = pos / equity if equity > 0 else 999
        act_lev = min(req_lev, max_lev)
        act_risk = (act_lev * equity) * sl_f
        
        if act_risk > equity * a_m:
            act_risk = equity * a_m
            
        pnl = act_risk * t[1]
        equity += pnl
        if equity < 0: equity = 0
        
        if t[1] > 0:
            cons_losses = 0
            monthly_data[month_key]["wins"] += 1
        elif t[1] < 0:
            cons_losses += 1
            monthly_data[month_key]["losses"] += 1
            
        monthly_data[month_key]["end_eq"] = equity
        
    with open("deepmind_v10_report.md", "w") as f:
        md = "# V10 DeepMind Optimizer: Mutlak Matematiksel Zirve\n\n"
        md += f"**Bulunan En İyisi:** ST {best_params[0]}-{best_params[1]} | EMA {best_params[2]} | TP {best_params[3]} | SL {best_params[4]}\n\n"
        md += "| Ay (Yıl-Ay) | Başlangıç Kasası | Ay Sonu Kasası | İşlem Sayısı | Win Rate | Aylık Büyüme |\n"
        md += "| :--- | :---: | :---: | :---: | :---: | :---: |\n"
        
        for m_key, d in monthly_data.items():
            start_eq = d["start_eq"]
            end_eq = d["end_eq"]
            trades = d["trades"]
            wins = d["wins"]
            losses = d["losses"]
            wrate = (wins/(wins+losses)*100) if (wins+losses) > 0 else 0
            growth = ((end_eq - start_eq) / start_eq * 100) if start_eq > 0 else 0
            
            md += f"| **{m_key}** | ${start_eq:,.2f} | **${end_eq:,.2f}** | {trades} | %{wrate:.1f} | **%{growth:.1f}** |\n"
            
        f.write(md)

if __name__ == "__main__":
    run_deepmind_optimizer()
