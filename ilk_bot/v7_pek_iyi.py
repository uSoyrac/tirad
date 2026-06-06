#!/usr/bin/env python3
import sys, os
import pandas as pd
import numpy as np
import warnings
import ta
import math
from itertools import product

warnings.filterwarnings("ignore")

COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]
TIMEFRAME = "4h"

def calculate_supertrend(df, period, multiplier, col_prefix):
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
            
    df[f'{col_prefix}_atr'] = atr
    df[f'{col_prefix}_st'] = st
    df[f'{col_prefix}_trend'] = t
    return df

def get_trade_result_v7(df, start_idx, trend, entry, atr, tp_mult, sl_mult):
    end_idx = min(start_idx + 100, len(df))
    slice_ahead = df.iloc[start_idx:end_idx]
    
    initial_sl = entry - (atr * sl_mult) if trend == 1 else entry + (atr * sl_mult)
    tp = entry + (atr * tp_mult) if trend == 1 else entry - (atr * tp_mult)
    
    risk_dist = abs(entry - initial_sl)
    rr = tp_mult / sl_mult
    
    # Break-Even her zaman SL'den biraz daha uzak bir noktada tetiklensin (Risk'in 1.25 katı)
    be_dist = risk_dist * 1.25
    be_trigger = entry + be_dist if trend == 1 else entry - be_dist
    
    current_sl = initial_sl
    is_breakeven = False
    
    filled = False
    for _, row in slice_ahead.iterrows():
        high, low = row["high"], row["low"]
        if trend == 1:
            if not filled and low <= entry: filled = True
            if filled:
                if high >= tp: return rr, risk_dist/entry*100
                if high >= be_trigger and not is_breakeven:
                    current_sl = entry
                    is_breakeven = True
                if low <= current_sl:
                    if is_breakeven: return 0.0, risk_dist/entry*100
                    return -1.0, risk_dist/entry*100
        else:
            if not filled and high >= entry: filled = True
            if filled:
                if low <= tp: return rr, risk_dist/entry*100
                if low <= be_trigger and not is_breakeven:
                    current_sl = entry
                    is_breakeven = True
                if high >= current_sl:
                    if is_breakeven: return 0.0, risk_dist/entry*100
                    return -1.0, risk_dist/entry*100
    return 0.0, 0.0

def simulate_v2_orp(trades):
    equity = 100.0
    target_eq = 100.0
    step = 0
    cycle = 0.15
    max_lev = 15.0
    cons_losses = 0
    
    for t in trades:
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
        
        sl_f = t["sl_pct"] / 100.0 if t["sl_pct"] > 0 else 0.015
        pos = req_risk / sl_f
        req_lev = pos / equity if equity > 0 else 999
        act_lev = min(req_lev, max_lev)
        act_risk = (act_lev * equity) * sl_f
        
        if act_risk > equity * a_m:
            act_risk = equity * a_m
            
        pnl = act_risk * t["r_mult"]
        equity += pnl
        if equity <= 0: return 0.0
        
        if t["r_mult"] > 0: cons_losses = 0
        elif t["r_mult"] < 0: cons_losses += 1
            
    return equity

def run_1_year_test():
    print("="*80)
    print(" 🤖 V7 AI OPTIMIZER: GRID SEARCH & HYPERPARAMETER TUNING 🤖")
    print("="*80)
    
    # Verileri bir kez yükle ve EMA/ST hesaplamalarını önceden yap
    coin_data = {}
    st_multipliers = [2.5, 3.0, 3.5]
    
    print("🔄 Veriler Yükleniyor ve Ön Hesaplamalar Yapılıyor...")
    for coin in COINS:
        csv_path = os.path.join(os.path.dirname(__file__), "..", "uyg", "src", "data", f"{coin}_USDT_{TIMEFRAME}.csv")
        if not os.path.exists(csv_path): continue
            
        df = pd.read_csv(csv_path)
        df["ts"] = pd.to_datetime(df["ts"])
        df["ema_200"] = ta.trend.EMAIndicator(df["close"], window=200).ema_indicator()
        
        for mult in st_multipliers:
            prefix = f"st_{str(mult).replace('.','_')}"
            df = calculate_supertrend(df, 10, mult, prefix)
            
        coin_data[coin] = df
        
    # Grid Search Parametreleri
    tp_multipliers = [3.0, 4.0, 5.0, 6.0]
    sl_multipliers = [1.5, 2.0, 2.5]
    
    combinations = list(product(st_multipliers, tp_multipliers, sl_multipliers))
    print(f"✅ Hazırlık Tamamlandı. Toplam taranacak paralel evren (kombinasyon) sayısı: {len(combinations)}")
    
    best_equity = 0
    best_params = None
    best_trades = []
    
    print("⏳ AI OPTİMİZASYON DÖNGÜSÜ BAŞLADI (Lütfen Bekleyin)...")
    for st_m, tp_m, sl_m in combinations:
        prefix = f"st_{str(st_m).replace('.','_')}"
        all_trades = []
        
        for coin, df in coin_data.items():
            for i in range(250, len(df) - 100):
                trend = df[f"{prefix}_trend"].iloc[i-1]
                prev_trend = df[f"{prefix}_trend"].iloc[i-2]
                
                close = df["close"].iloc[i-1]
                low = df["low"].iloc[i-1]
                high = df["high"].iloc[i-1]
                st = df[f"{prefix}_st"].iloc[i-1]
                atr = df[f"{prefix}_atr"].iloc[i-1]
                ema200 = df["ema_200"].iloc[i-1]
                
                is_signal = False
                if trend == 1:
                    if prev_trend == -1: is_signal = True
                    elif low <= st + (atr * 0.5): is_signal = True
                else:
                    if prev_trend == 1: is_signal = True
                    elif high >= st - (atr * 0.5): is_signal = True
                    
                if not is_signal: continue
                
                # EMA 200 MAKRO FİLTRE (Klasik V2 Mantığı)
                if trend == 1 and close < ema200: continue
                if trend == -1 and close > ema200: continue
                    
                result_r, sl_pct = get_trade_result_v7(df, i, trend, close, atr, tp_m, sl_m)
                
                if result_r != 0.0 or (result_r == 0.0 and sl_pct > 0.0):
                    all_trades.append({
                        "coin": coin, "date": df.iloc[i]['ts'], "r_mult": result_r, "sl_pct": sl_pct
                    })
                    
        all_trades = sorted(all_trades, key=lambda x: x["date"])
        equity = simulate_v2_orp(all_trades)
        
        if equity > best_equity:
            best_equity = equity
            best_params = (st_m, tp_m, sl_m)
            best_trades = all_trades
            
    print("🎯 YAPAY ZEKA OPTİMİZASYONU TAMAMLANDI!")
    print(f"🏆 EN İYİ GENETİK BULUNDU -> Supertrend: {best_params[0]} | Kâr (TP): {best_params[1]} ATR | Zarar Kes (SL): {best_params[2]} ATR")
    
    wins = sum(1 for t in best_trades if t["r_mult"] > 0)
    losses = sum(1 for t in best_trades if t["r_mult"] < 0)
    be = sum(1 for t in best_trades if t["r_mult"] == 0.0)
    wr = (wins/(wins+losses)*100) if (wins+losses) > 0 else 0
    print(f"📊 OPTİMAL İŞLEM İSTATİSTİKLERİ -> Toplam: {len(best_trades)} | Başarılı: {wins} | Başarısız: {losses} | Başa Baş: {be} | Win Rate: %{wr:.1f}")
    
    # AYLIK TABLO ÇIKTISI
    print("\n" + "="*80)
    print(" 📅 V7 AI OPTIMIZED V2: 1 YILLIK KASA BÜYÜME TABLOSU 📅")
    print("="*80)
    
    equity = 100.0
    target_eq = 100.0
    step = 0
    cycle = 0.15
    max_lev = 15.0
    cons_losses = 0
    monthly_data = {}
    
    for t in best_trades:
        month_key = t["date"].strftime("%Y-%m")
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
        
        sl_f = t["sl_pct"] / 100.0 if t["sl_pct"] > 0 else 0.015
        pos = req_risk / sl_f
        req_lev = pos / equity if equity > 0 else 999
        act_lev = min(req_lev, max_lev)
        act_risk = (act_lev * equity) * sl_f
        
        if act_risk > equity * a_m:
            act_risk = equity * a_m
            
        pnl = act_risk * t["r_mult"]
        equity += pnl
        if equity < 0: equity = 0
        
        if t["r_mult"] > 0:
            cons_losses = 0
            monthly_data[month_key]["wins"] += 1
        elif t["r_mult"] < 0:
            cons_losses += 1
            monthly_data[month_key]["losses"] += 1
            
        monthly_data[month_key]["end_eq"] = equity
        
    with open("ai_v7_report.md", "w") as f:
        md = "# V7 AI Optimized V2: 1 Yıllık Efsanevi Rapor\n\n"
        md += f"**Yapay Zekanın Bulduğu Optimal Parametreler:** Supertrend: {best_params[0]}x | TP: {best_params[1]} ATR | SL: {best_params[2]} ATR\n\n"
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
            
            print(f"{m_key} | Başlangıç: ${start_eq:>10,.2f} | Bitiş: ${end_eq:>10,.2f} | WR: %{wrate:>4.1f} | Büyüme: %{growth:>7.1f}")
            md += f"| **{m_key}** | ${start_eq:,.2f} | **${end_eq:,.2f}** | {trades} | %{wrate:.1f} | **%{growth:.1f}** |\n"
            
        f.write(md)
        
    print("\n✅ Rapor ai_v7_report.md dosyasına kaydedildi!")
    print(f"\n💰 NİHAİ 1 YIL SONU KASASI: ${equity:,.2f} (100 Dolardan)")
    print(f"📈 Yıllık Büyüme: {equity/100:,.0f} Kat ({(equity-100)/100*100:,.0f}%)")

if __name__ == "__main__":
    run_1_year_test()
