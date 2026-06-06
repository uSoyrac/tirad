#!/usr/bin/env python3
"""
V19 WIN RATE HUNTER: Kazanma Oranını Artırma Odaklı
====================================================
V18 Problemi: %44.2 Win Rate, 406 işlemden 206 kayıp → $146K komisyon
V19 Hedefi: Kalitesiz işlemleri eleye eleye WR'ı yükseltmek,
            aynı zamanda yeterli işlem sayısını korumak.

STRATEJİ: Birden fazla WR arttırıcı filtre test et, en optimal kombinasyonu bul.

FİLTRELER:
  A) Sadece Crossover (Trend değişiminde gir, bounce'ları atla)
  B) RSI Filtresi (Aşırı alım/satım bölgelerinde işlem açma)
  C) MACD Momentum (Histogram yönü trend yönüyle uyumlu olmalı)
  D) Günlük Trend Onayı (1D EMA200 ile 4H sinyal uyumu)
  E) Sıkı Hacim Filtresi (vol_ratio < 2.0 yerine 1.8)
  F) ATR Bandı (Çok düşük ve çok yüksek volatilitede işlem açma)
  G) ADX Bandı (15-35 arası - ne çok zayıf ne çok güçlü trend)
"""
import sys, os
import pandas as pd
import numpy as np
import warnings
import ta
from itertools import combinations

warnings.filterwarnings("ignore")

COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]
TIMEFRAME = "4h"
FRICTION_RATE = 0.0006  # Limit maker

def calculate_supertrend(df, period=14, multiplier=3.5):
    high, low, close = df['high'], df['low'], df['close']
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
    tp_mult, sl_mult = 4.0, 2.5
    end_idx = min(start_idx + 100, len(df))
    slice_ahead = df.iloc[start_idx:end_idx]
    initial_sl = entry - (atr * sl_mult) if trend == 1 else entry + (atr * sl_mult)
    tp = entry + (atr * tp_mult) if trend == 1 else entry - (atr * tp_mult)
    risk_dist = abs(entry - initial_sl)
    rr = tp_mult / sl_mult
    be_dist = risk_dist * 1.25
    be_trigger = entry + be_dist if trend == 1 else entry - be_dist
    current_sl, is_breakeven, filled = initial_sl, False, False
    for _, row in slice_ahead.iterrows():
        high, low = row["high"], row["low"]
        if trend == 1:
            if not filled and low <= entry: filled = True
            if filled:
                if high >= tp: return rr, risk_dist/entry*100
                if high >= be_trigger and not is_breakeven: current_sl, is_breakeven = entry, True
                if low <= current_sl: return (0.0 if is_breakeven else -1.0), risk_dist/entry*100
        else:
            if not filled and high >= entry: filled = True
            if filled:
                if low <= tp: return rr, risk_dist/entry*100
                if low <= be_trigger and not is_breakeven: current_sl, is_breakeven = entry, True
                if high >= current_sl: return (0.0 if is_breakeven else -1.0), risk_dist/entry*100
    return 0.0, 0.0

def simulate_equity(trades, start_capital=100.0):
    equity = start_capital
    target_eq = start_capital
    step, cons_loss, total_fees = 0, 0, 0.0
    min_eq, peak_eq = start_capital, start_capital
    monthly_data = {}
    
    for t in trades:
        month_key = t["date"].strftime("%Y-%m")
        if month_key not in monthly_data:
            monthly_data[month_key] = {"start_eq": equity, "end_eq": equity, "trades": 0, "wins": 0, "losses": 0}
        monthly_data[month_key]["trades"] += 1
        
        drawdown_pct = (peak_eq - equity) / peak_eq if peak_eq > 0 else 0
        if drawdown_pct > 0.5: current_max_lev = 3.0
        elif drawdown_pct > 0.3: current_max_lev = 6.0
        elif drawdown_pct > 0.15: current_max_lev = 9.0
        else: current_max_lev = 15.0
        
        if cons_loss >= 3: a_b, a_m, a_r = 0.0125, 0.05, 1.5
        else: a_b, a_m, a_r = 0.05, 0.20, 1.5
        
        while equity >= target_eq:
            step += 1
            target_eq = start_capital * (1.15 ** step)
        
        delta = max(0, target_eq - equity)
        req_risk = max(equity * a_b, delta / a_r)
        sl_f = max(t["sl_pct"] / 100.0, 0.015)
        act_lev = min(req_risk / sl_f / equity if equity > 0 else 999, current_max_lev)
        act_risk = min(act_lev * equity * sl_f, equity * a_m)
        
        # 🚨 BİNANCE LİKİDİTE DUVARI (REALITY CHECK) 🚨
        MAX_POS_USD = 50000.0
        act_pos = act_lev * equity
        if act_pos > MAX_POS_USD:
            act_pos = MAX_POS_USD
            act_lev = act_pos / equity
            act_risk = act_pos * sl_f
            
        friction = act_pos * FRICTION_RATE
        total_fees += friction
        equity += (act_risk * t["r_mult"]) - friction
        
        if equity > peak_eq: peak_eq = equity
        if equity < min_eq: min_eq = equity
        if equity <= 0: break
        
        if t["r_mult"] > 0:
            cons_loss = 0
            monthly_data[month_key]["wins"] += 1
        elif t["r_mult"] < 0:
            cons_loss += 1
            monthly_data[month_key]["losses"] += 1
        monthly_data[month_key]["end_eq"] = equity
    
    return equity, min_eq, total_fees, monthly_data

def main():
    print("="*80)
    print(" 🎯 V19 WIN RATE HUNTER: KAZANMA ORANINI ARTIRMA OPTİMİZASYONU 🎯")
    print("="*80)
    
    # Load 1D data for daily trend confirmation
    daily_ema = {}
    for coin in COINS:
        d1_path = f"/Users/uygar/.gemini/antigravity/scratch/tirad/uyg/src/data/{coin}_USDT_1d.csv"
        if os.path.exists(d1_path):
            df_d = pd.read_csv(d1_path)
            df_d["ts"] = pd.to_datetime(df_d["ts"])
            df_d["ema_200"] = ta.trend.EMAIndicator(df_d["close"], window=200).ema_indicator()
            daily_ema[coin] = df_d.set_index("ts")[["close", "ema_200"]]
    
    # Load 4H data
    all_dfs = {}
    for coin in COINS:
        csv_path = f"/Users/uygar/.gemini/antigravity/scratch/tirad/uyg/src/data/{coin}_USDT_{TIMEFRAME}.csv"
        if not os.path.exists(csv_path): continue
        df = pd.read_csv(csv_path)
        df["ts"] = pd.to_datetime(df["ts"])
        df = calculate_supertrend(df, 14, 3.5)
        df["ema_250"] = ta.trend.EMAIndicator(df["close"], window=250).ema_indicator()
        df['adx'] = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14).adx()
        df['vol_sma'] = df['volume'].rolling(20).mean()
        df['vol_ratio'] = df['volume'] / df['vol_sma']
        df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
        macd = ta.trend.MACD(df['close'], window_slow=26, window_fast=12, window_sign=9)
        df['macd_hist'] = macd.macd_diff()
        df['atr_pct'] = (df['atr'] / df['close']) * 100
        df['atr_pct_sma'] = df['atr_pct'].rolling(50).mean()
        all_dfs[coin] = df
    
    # Define filter combinations to test
    filter_names = {
        "A": "Sadece Crossover",
        "B": "RSI Filtresi",
        "C": "MACD Momentum",
        "D": "Günlük Trend",
        "E": "Sıkı Hacim(<2.0)",
        "F": "ATR Bandı",
        "G": "ADX Bandı(15-35)",
    }
    
    # Generate all trade signals with all filter flags
    print("\n🔬 Sinyal taranıyor ve filtre bayrakları hesaplanıyor...\n")
    
    all_signals = []
    for coin, df in all_dfs.items():
        for i in range(250, len(df) - 100):
            trend = df["st_trend"].iloc[i-1]
            prev_trend = df["st_trend"].iloc[i-2]
            close = df["close"].iloc[i-1]
            low_p, high_p = df["low"].iloc[i-1], df["high"].iloc[i-1]
            st, atr = df["st"].iloc[i-1], df["atr"].iloc[i-1]
            ema250 = df["ema_250"].iloc[i-1]
            adx = df["adx"].iloc[i-1]
            vol_ratio = df["vol_ratio"].iloc[i-1]
            rsi = df["rsi"].iloc[i-1]
            macd_hist = df["macd_hist"].iloc[i-1]
            atr_pct = df["atr_pct"].iloc[i-1]
            atr_pct_sma = df["atr_pct_sma"].iloc[i-1]
            
            # Base signal
            is_crossover = (trend == 1 and prev_trend == -1) or (trend == -1 and prev_trend == 1)
            is_bounce = False
            if trend == 1 and low_p <= st + (atr * 0.5): is_bounce = True
            if trend == -1 and high_p >= st - (atr * 0.5): is_bounce = True
            
            if not is_crossover and not is_bounce: continue
            
            # EMA 250 base filter (always on)
            if trend == 1 and close < ema250: continue
            if trend == -1 and close > ema250: continue
            
            # V14 base filter (always on)
            if vol_ratio > 2.5 or adx > 40: continue
            
            # Get trade result
            res_r, sl_pct = get_trade_result(df, i, trend, close, atr)
            if res_r == 0.0 and sl_pct == 0.0: continue
            
            # Calculate filter flags
            flags = {}
            flags["A"] = is_crossover  # Only crossover, no bounces
            flags["B"] = (trend == 1 and rsi < 65) or (trend == -1 and rsi > 35)  # RSI not extreme
            flags["C"] = (trend == 1 and macd_hist > 0) or (trend == -1 and macd_hist < 0)  # MACD aligned
            
            # Daily trend confirmation
            daily_ok = True
            if coin in daily_ema:
                date_key = df.iloc[i]['ts'].normalize()
                nearby = daily_ema[coin].index.searchsorted(date_key) - 1
                if 0 <= nearby < len(daily_ema[coin]):
                    d_close = daily_ema[coin].iloc[nearby]["close"]
                    d_ema = daily_ema[coin].iloc[nearby]["ema_200"]
                    if pd.notna(d_ema):
                        if trend == 1 and d_close < d_ema: daily_ok = False
                        if trend == -1 and d_close > d_ema: daily_ok = False
            flags["D"] = daily_ok
            
            flags["E"] = vol_ratio < 2.0  # Tighter volume
            flags["F"] = atr_pct_sma > 0 and 0.5 < (atr_pct / atr_pct_sma) < 2.0  # ATR in normal band
            flags["G"] = 15 < adx < 35  # ADX sweet spot
            
            all_signals.append({
                "coin": coin, "date": df.iloc[i]['ts'], "r_mult": res_r, "sl_pct": sl_pct,
                "flags": flags
            })
    
    all_signals = sorted(all_signals, key=lambda x: x["date"])
    
    # V18 baseline (no extra filters beyond V14)
    base_trades = [{"date": s["date"], "r_mult": s["r_mult"], "sl_pct": s["sl_pct"]} for s in all_signals]
    base_wins = sum(1 for s in all_signals if s["r_mult"] > 0)
    base_losses = sum(1 for s in all_signals if s["r_mult"] < 0)
    base_wr = base_wins / (base_wins + base_losses) * 100 if (base_wins + base_losses) > 0 else 0
    
    print(f"V18 Baseline: {len(all_signals)} işlem | WR: %{base_wr:.1f} ({base_wins}W/{base_losses}L)")
    
    # Test all single filters and combinations
    results = []
    
    # Test each single filter
    filter_keys = list(filter_names.keys())
    all_combos = []
    for r in range(1, len(filter_keys) + 1):
        for combo in combinations(filter_keys, r):
            all_combos.append(combo)
    
    print(f"\n🚀 {len(all_combos)} filtre kombinasyonu test ediliyor...\n")
    
    for combo in all_combos:
        filtered = [s for s in all_signals if all(s["flags"][f] for f in combo)]
        if len(filtered) < 30: continue  # Min 30 işlem
        
        trades = [{"date": s["date"], "r_mult": s["r_mult"], "sl_pct": s["sl_pct"]} for s in filtered]
        wins = sum(1 for s in filtered if s["r_mult"] > 0)
        losses = sum(1 for s in filtered if s["r_mult"] < 0)
        wr = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
        
        equity, min_eq, fees, monthly = simulate_equity(trades)
        
        combo_name = "+".join(combo)
        results.append({
            "combo": combo_name,
            "combo_desc": " + ".join(filter_names[f] for f in combo),
            "trades": len(filtered),
            "wins": wins,
            "losses": losses,
            "wr": wr,
            "equity": equity,
            "min_eq": min_eq,
            "fees": fees,
            "monthly": monthly,
        })
    
    # Sort by equity (best overall performance)
    results.sort(key=lambda x: x["equity"], reverse=True)
    
    # Also find best WR with decent profit
    wr_sorted = sorted([r for r in results if r["equity"] > 100000], key=lambda x: x["wr"], reverse=True)
    
    print("="*80)
    print(" 📊 EN YÜKSEK KÂRLI KOMBİNASYONLAR (Top 15)")
    print("="*80)
    
    with open("v19_winrate_report.md", "w") as f:
        f.write("# 🎯 V19 Win Rate Hunter: Kazanma Oranı Optimizasyonu\n\n")
        f.write(f"**V18 Baseline:** {len(all_signals)} işlem | WR: %{base_wr:.1f}\n\n")
        
        f.write("## 💰 En Yüksek Kârlı Kombinasyonlar (Top 15)\n\n")
        f.write("| # | Filtreler | İşlem | Wins | Losses | WR | Min Kasa | Komisyon | NET KÂR |\n")
        f.write("| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |\n")
        for i, r in enumerate(results[:15], 1):
            safe = "🛡️" if r["min_eq"] >= 5 else "⚠️"
            print(f"  #{i} {r['combo']:20s} | {r['trades']:>3} işlem | WR: %{r['wr']:>4.1f} | Min: ${r['min_eq']:>6.2f} | Fee: ${r['fees']:>9,.0f} | KÂR: ${r['equity']:>12,.0f}")
            f.write(f"| {safe}{i} | {r['combo_desc']} | {r['trades']} | {r['wins']} | {r['losses']} | **%{r['wr']:.1f}** | ${r['min_eq']:,.2f} | ${r['fees']:,.0f} | **${r['equity']:,.0f}** |\n")
        
        if wr_sorted:
            f.write(f"\n## 🎯 En Yüksek Win Rate ($100K+ Kâr, Top 10)\n\n")
            f.write("| # | Filtreler | İşlem | WR | Min Kasa | Komisyon | NET KÂR |\n")
            f.write("| :---: | :--- | :---: | :---: | :---: | :---: | :---: |\n")
            print(f"\n{'='*80}")
            print(f" 🎯 EN YÜKSEK WIN RATE KOMBİNASYONLAR ($100K+ Kâr)")
            print(f"{'='*80}")
            for i, r in enumerate(wr_sorted[:10], 1):
                print(f"  #{i} {r['combo']:20s} | {r['trades']:>3} işlem | WR: %{r['wr']:>4.1f} | KÂR: ${r['equity']:>12,.0f}")
                f.write(f"| {i} | {r['combo_desc']} | {r['trades']} | **%{r['wr']:.1f}** | ${r['min_eq']:,.2f} | ${r['fees']:,.0f} | **${r['equity']:,.0f}** |\n")
        
        # Best overall (highest profit with WR > 50%)
        high_wr_profitable = [r for r in results if r["wr"] >= 50 and r["min_eq"] >= 5]
        if high_wr_profitable:
            best = high_wr_profitable[0]
        else:
            best = wr_sorted[0] if wr_sorted else results[0]
        
        f.write(f"\n## 🏆 V19 ŞAMPİYON: Aylık Dağılım\n\n")
        f.write(f"**Konfigürasyon:** {best['combo_desc']}\n")
        f.write(f"**İşlem:** {best['trades']} | **WR:** %{best['wr']:.1f} | **Min Kasa:** ${best['min_eq']:,.2f}\n\n")
        f.write("| Ay | Başlangıç | Bitiş | İşlem | Win Rate | Büyüme |\n")
        f.write("| :--- | :---: | :---: | :---: | :---: | :---: |\n")
        print(f"\n{'='*80}")
        print(f" 🏆 V19 ŞAMPİYON: {best['combo_desc']}")
        print(f" İşlem: {best['trades']} | WR: %{best['wr']:.1f} | KÂR: ${best['equity']:,.0f}")
        print(f"{'='*80}")
        for m_key, d in best["monthly"].items():
            wr = (d["wins"]/(d["wins"]+d["losses"])*100) if (d["wins"]+d["losses"]) > 0 else 0
            growth = ((d["end_eq"] - d["start_eq"]) / d["start_eq"] * 100) if d["start_eq"] > 0 else 0
            print(f"  {m_key}: ${d['start_eq']:>12,.2f} → ${d['end_eq']:>12,.2f} | WR: %{wr:>4.1f} | Büyüme: %{growth:>9.1f}")
            f.write(f"| **{m_key}** | ${d['start_eq']:,.2f} | **${d['end_eq']:,.2f}** | {d['trades']} | %{wr:.1f} | **%{growth:.1f}** |\n")
        
        f.write(f"\n**💰 NİHAİ KÂR: ${best['equity']:,.2f}** | **💸 Komisyon: ${best['fees']:,.2f}** | **🛡️ Min Kasa: ${best['min_eq']:,.2f}**\n")
    
    print(f"\n✅ Rapor v19_winrate_report.md dosyasına kaydedildi!")

if __name__ == "__main__":
    main()
