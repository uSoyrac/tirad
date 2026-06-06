#!/usr/bin/env python3
import sys, os
import pandas as pd
import numpy as np
import warnings
import ta
from sklearn.cluster import KMeans

warnings.filterwarnings("ignore")

COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]
TIMEFRAME = "4h"

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
    current_sl = initial_sl
    is_breakeven = False
    filled = False
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

def build_ml_regime_filter():
    btc_1d_path = "/Users/uygar/.gemini/antigravity/scratch/tirad/uyg/src/data/BTC_USDT_1d.csv"
    df = pd.read_csv(btc_1d_path)
    df["ts"] = pd.to_datetime(df["ts"])
    df.set_index("ts", inplace=True)
    df['adx'] = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14).adx()
    tr = pd.DataFrame({'tr1': df['high'] - df['low'], 'tr2': abs(df['high'] - df['close'].shift(1)), 'tr3': abs(df['low'] - df['close'].shift(1))}).max(axis=1)
    df['atr_pct'] = (tr.ewm(alpha=1/14, adjust=False).mean() / df['close']) * 100
    df.dropna(inplace=True)
    regime_map = {}
    for i in range(90, len(df)):
        window = df.iloc[i-90:i]
        kmeans = KMeans(n_clusters=2, random_state=42, n_init=10).fit(window[['adx', 'atr_pct']].values)
        chop_cluster = 0 if kmeans.cluster_centers_[0][0] < kmeans.cluster_centers_[1][0] else 1
        current_features = df.iloc[i][['adx', 'atr_pct']].values.reshape(1, -1)
        pred = kmeans.predict(current_features)[0] if len(current_features[0]) == 2 else chop_cluster
        regime_map[df.index[i].strftime("%Y-%m-%d")] = "CHOP" if pred == chop_cluster else "TREND"
    return regime_map

def run_simulation():
    print("="*80)
    print(" 🤖 V16 YAPAY ZEKA (GERÇEKÇİ SÜRTÜNME/KOMİSYON TESTİ) 🤖")
    print("="*80)
    
    regime_map = build_ml_regime_filter()
    all_trades = []
    
    for coin in COINS:
        csv_path = f"/Users/uygar/.gemini/antigravity/scratch/tirad/uyg/src/data/{coin}_USDT_{TIMEFRAME}.csv"
        df = pd.read_csv(csv_path)
        df["ts"] = pd.to_datetime(df["ts"])
        df = calculate_supertrend(df, 14, 3.5)
        df["ema_250"] = ta.trend.EMAIndicator(df["close"], window=250).ema_indicator()
        df['adx'] = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14).adx()
        df['vol_sma'] = df['volume'].rolling(20).mean()
        df['vol_ratio'] = df['volume'] / df['vol_sma']
        
        for i in range(250, len(df) - 100):
            trend = df["st_trend"].iloc[i-1]
            prev_trend = df["st_trend"].iloc[i-2]
            close = df["close"].iloc[i-1]
            low = df["low"].iloc[i-1]
            high = df["high"].iloc[i-1]
            st = df["st"].iloc[i-1]
            atr = df["atr"].iloc[i-1]
            ema250 = df["ema_250"].iloc[i-1]
            adx = df["adx"].iloc[i-1]
            vol_ratio = df["vol_ratio"].iloc[i-1]
            
            is_signal = False
            if trend == 1:
                if prev_trend == -1 or low <= st + (atr * 0.5): is_signal = True
            else:
                if prev_trend == 1 or high >= st - (atr * 0.5): is_signal = True
                
            if not is_signal: continue
            
            # Filters
            if trend == 1 and close < ema250: continue
            if trend == -1 and close > ema250: continue
            if regime_map.get(df.iloc[i]['ts'].strftime("%Y-%m-%d"), "TREND") == "CHOP": continue
            if vol_ratio > 2.5 or adx > 40: continue
            
            res_r, sl_pct = get_trade_result(df, i, trend, close, atr)
            if res_r != 0.0 or sl_pct > 0.0:
                all_trades.append({"date": df.iloc[i]['ts'], "r_mult": res_r, "sl_pct": sl_pct})
                
    all_trades = sorted(all_trades, key=lambda x: x["date"])
    
    wins = sum(1 for t in all_trades if t["r_mult"] > 0)
    losses = sum(1 for t in all_trades if t["r_mult"] < 0)
    win_rate = (wins / len(all_trades) * 100) if all_trades else 0
    print(f"Toplam İşlem: {len(all_trades)} | Başarılı: {wins} | Başarısız: {losses} | WR: %{win_rate:.1f}")
    
    equity, min_eq, target_eq, step, cycle, max_lev, cons_loss, total_fees = 100.0, 100.0, 100.0, 0, 0.15, 15.0, 0, 0.0
    FRICTION_RATE = 0.0018
    monthly_data = {}
    
    for t in all_trades:
        month_key = t["date"].strftime("%Y-%m")
        if month_key not in monthly_data:
            monthly_data[month_key] = {"start_eq": equity, "end_eq": equity, "trades": 0, "wins": 0, "losses": 0}
            
        monthly_data[month_key]["trades"] += 1
        
        if cons_loss >= 3: a_b, a_m, a_r = 0.01, 0.05, 1.0
        else: a_b, a_m, a_r = 0.05, 0.20, 1.5
            
        while equity >= target_eq:
            step += 1
            target_eq = 100.0 * ((1.0 + cycle) ** step)
            
        delta = max(0, target_eq - equity)
        req_risk = max(equity * a_b, delta / a_r)
        sl_f = max(t["sl_pct"] / 100.0, 0.015)
        pos = req_risk / sl_f
        req_lev = pos / equity if equity > 0 else 999
        act_lev = min(req_lev, max_lev)
        act_risk = min(act_lev * equity * sl_f, equity * a_m)
        
        friction = (act_lev * equity) * FRICTION_RATE
        total_fees += friction
        pnl = (act_risk * t["r_mult"]) - friction
        equity += pnl
        
        if equity < min_eq: min_eq = equity
        if equity <= 0: break
            
        if t["r_mult"] > 0:
            cons_loss = 0
            monthly_data[month_key]["wins"] += 1
        elif t["r_mult"] < 0:
            cons_loss += 1
            monthly_data[month_key]["losses"] += 1
            
        monthly_data[month_key]["end_eq"] = equity
        
    print("\n" + "="*80)
    print(" 📅 V16 YAPAY ZEKA (GERÇEKÇİ SÜRTÜNME): 1 YILLIK KASA BÜYÜME TABLOSU 📅")
    print("="*80)
    
    with open("v16_reality_monthly_report.md", "w") as f:
        md = "# V16 Yapay Zeka (Gerçekçi Komisyonlu): Aylık Rapor\n\n"
        md += f"**Ödenen Toplam Komisyon ve Kayma Masrafı:** ${total_fees:,.2f}\n"
        md += f"**Max Çöküş (Kasanın Dibi):** ${min_eq:,.2f}\n\n"
        md += "| Ay (Yıl-Ay) | Başlangıç Kasası | Ay Sonu Kasası | İşlem Sayısı | Win Rate | Aylık Büyüme |\n"
        md += "| :--- | :---: | :---: | :---: | :---: | :---: |\n"
        
        for m_key, d in monthly_data.items():
            start_eq = d["start_eq"]
            end_eq = d["end_eq"]
            trades = d["trades"]
            wins, losses = d["wins"], d["losses"]
            wr = (wins/(wins+losses)*100) if (wins+losses) > 0 else 0
            growth = ((end_eq - start_eq) / start_eq * 100) if start_eq > 0 else 0
            
            print(f"{m_key} | Başlangıç: ${start_eq:>10,.2f} | Bitiş: ${end_eq:>10,.2f} | WR: %{wr:>4.1f} | Büyüme: %{growth:>7.1f}")
            md += f"| **{m_key}** | ${start_eq:,.2f} | **${end_eq:,.2f}** | {trades} | %{wr:.1f} | **%{growth:.1f}** |\n"
            
        f.write(md)
        
    print(f"\n💸 ÖDENEN TOPLAM KOMİSYON VE KAYMA MASRAFI: ${total_fees:,.2f}")
    print(f"📊 GERÇEK DÜNYADA KASANIN GÖRDÜĞÜ EN DİP SEVİYE: ${min_eq:,.2f}")
    print(f"\n💰 NİHAİ 1 YIL SONU GERÇEK KASASI: ${equity:,.2f} (100 Dolardan)")

if __name__ == "__main__":
    run_simulation()
