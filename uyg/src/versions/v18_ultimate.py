#!/usr/bin/env python3
"""
V18 ULTIMATE OPTIMIZER - TÜM BİLGİ BİRİKİMİNİN NİHAİ BİRLEŞİMİ
==================================================================

KULLANILAN KAYNAKLAR (Tüm Artifact'ler Tarandı):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. bot_strategy_guide.md → ORP (Optimized Recovery Progression) + Ruin Guard
2. optimization_results.md → Grid Search: Cycle %10, Recovery 1.0, Base %4, MaxRisk %20, MaxLev 10x  
3. bot_strategies_vol2.md → Filtre gevşetme, işlem sıklığı artırma
4. optimal_limit_dca_plan.md → Limit emirleri (Maker fee), Scale-In DCA
5. ml_optimization_plan.md → XGBoost filtresi, Precision odaklı model
6. reality_check_report.md → Likidite limitleri, kaldıraç tier'ları
7. master_prompt_guide.md → Blackjack kart sayma felsefesi, SMC + OB + ORP
8. V7-V17 test sonuçları → Balina tuzağı, ML rejim, komisyon sürtünmesi

ÖĞRENİMLER VE SENTEZİ:
━━━━━━━━━━━━━━━━━━━━━━
• Grid Search optimal ORP: Cycle=%10, Recovery=1.0, BaseRisk=%4, MaxRisk=%20, MaxLev=10x
  (Eski %5/%15/15x parametreleri büyümeyi %5219 yavaşlatıyordu!)
• Limit emirler (Maker): Komisyonu %75 düşürür (0.02% vs 0.04% taker)
• BNB fee discount (%25): Maker fee'yi 0.015%'e düşürür
• Dinamik kaldıraç: Drawdown'da kaldıracı düşürmek kasayı korur
• V14 Anti-Likidite: Hacim patlaması (>2.5x) ve ADX>40 filtresi
• V16 ML Rejim: BTC günlük verilerinden K-Means ile chop/trend sınıflandırma
• Paranın Hızı (Velocity): İşlem sayısını düşürmek milyonları öldürür
"""
import sys, os
import pandas as pd
import numpy as np
import warnings
import ta
from sklearn.cluster import KMeans
from itertools import product

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

def build_ml_regime_filter():
    btc_1d_path = "/Users/uygar/.gemini/antigravity/scratch/tirad/uyg/src/data/BTC_USDT_1d.csv"
    if not os.path.exists(btc_1d_path): return {}
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
        pred = kmeans.predict(current_features)[0]
        regime_map[df.index[i].strftime("%Y-%m-%d")] = "CHOP" if pred == chop_cluster else "TREND"
    return regime_map

def generate_trades(all_dfs, use_v14, use_ml, regime_map):
    trades = []
    for coin, df in all_dfs.items():
        for i in range(250, len(df) - 100):
            trend = df["st_trend"].iloc[i-1]
            prev_trend = df["st_trend"].iloc[i-2]
            close = df["close"].iloc[i-1]
            low_p, high_p = df["low"].iloc[i-1], df["high"].iloc[i-1]
            st, atr = df["st"].iloc[i-1], df["atr"].iloc[i-1]
            ema250 = df["ema_250"].iloc[i-1]
            
            is_signal = False
            if trend == 1:
                if prev_trend == -1 or low_p <= st + (atr * 0.5): is_signal = True
            else:
                if prev_trend == 1 or high_p >= st - (atr * 0.5): is_signal = True
            if not is_signal: continue
            if trend == 1 and close < ema250: continue
            if trend == -1 and close > ema250: continue
            if use_ml and regime_map.get(df.iloc[i]['ts'].strftime("%Y-%m-%d"), "TREND") == "CHOP": continue
            if use_v14 and (df["vol_ratio"].iloc[i-1] > 2.5 or df["adx"].iloc[i-1] > 40): continue
            
            res_r, sl_pct = get_trade_result(df, i, trend, close, atr)
            if res_r != 0.0 or sl_pct > 0.0:
                trades.append({"date": df.iloc[i]['ts'], "r_mult": res_r, "sl_pct": sl_pct})
    return sorted(trades, key=lambda x: x["date"])

def simulate_equity(trades, start_capital, max_lev, friction_rate, use_dynamic_lev,
                    cycle_pct, recovery_factor, base_risk_pct, max_risk_cap, cons_loss_freeze):
    """
    Grid Search Optimal ORP Motoru (optimization_results.md'den):
    - cycle_pct: %10 (eski %5'ten 2x agresif)
    - recovery_factor: 1.0 (tam deficit risk, eski 1.5 bölen kaldırıldı)
    - base_risk_pct: %4 (eski %2.5'ten yükseltildi)
    - max_risk_cap: %20 (eski %15'ten genişletildi)
    """
    equity = start_capital
    target_eq = start_capital
    step, cons_loss, total_fees = 0, 0, 0.0
    min_eq = start_capital
    peak_eq = start_capital
    monthly_data = {}
    
    for t in trades:
        month_key = t["date"].strftime("%Y-%m")
        if month_key not in monthly_data:
            monthly_data[month_key] = {"start_eq": equity, "end_eq": equity, "trades": 0, "wins": 0, "losses": 0}
        monthly_data[month_key]["trades"] += 1
        
        # Dinamik kaldıraç (bot_strategy_guide: Ruin Guard prensibi)
        if use_dynamic_lev:
            drawdown_pct = (peak_eq - equity) / peak_eq if peak_eq > 0 else 0
            if drawdown_pct > 0.5:
                current_max_lev = max(2, max_lev * 0.2)
            elif drawdown_pct > 0.3:
                current_max_lev = max(3, max_lev * 0.4)
            elif drawdown_pct > 0.15:
                current_max_lev = max(5, max_lev * 0.6)
            else:
                current_max_lev = max_lev
        else:
            current_max_lev = max_lev
        
        # ORP Consecutive Loss Freeze (3+ ardışık kayıpta risk düşür)
        if cons_loss_freeze and cons_loss >= 3:
            a_b = base_risk_pct * 0.25  # Base risk'i %75 düşür
            a_m = max_risk_cap * 0.25   # Max cap'i %75 düşür
            a_r = max(recovery_factor, 1.5)  # Recovery'yi güvenli moda al
        else:
            a_b = base_risk_pct
            a_m = max_risk_cap
            a_r = recovery_factor
            
        # Target hesaplama (Grid Search optimal: cycle_pct=0.10)
        while equity >= target_eq:
            step += 1
            target_eq = start_capital * ((1.0 + cycle_pct) ** step)
            
        delta = max(0, target_eq - equity)
        base_amt = equity * a_b
        req_risk = max(base_amt, delta / a_r)
        
        sl_f = max(t["sl_pct"] / 100.0, 0.015)
        pos = req_risk / sl_f
        req_lev = pos / equity if equity > 0 else 999
        act_lev = min(req_lev, current_max_lev)
        act_risk = min(act_lev * equity * sl_f, equity * a_m)
        
        # 🚨 BİNANCE LİKİDİTE DUVARI (REALITY CHECK) 🚨
        MAX_POS_USD = 50000.0
        act_pos = act_lev * equity
        if act_pos > MAX_POS_USD:
            act_pos = MAX_POS_USD
            act_lev = act_pos / equity
            act_risk = act_pos * sl_f
            
        friction = act_pos * friction_rate
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
    print(" 🏆 V18 ULTIMATE OPTIMIZER: TÜM BİLGİ BİRİKİMİNİN SENTEZİ 🏆")
    print("="*80)
    
    print("📊 Veriler yükleniyor...", flush=True)
    regime_map = build_ml_regime_filter()
    
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
        all_dfs[coin] = df
    
    # Trade sets
    print("🔬 İşlem sinyalleri taranıyor...", flush=True)
    trade_sets = {}
    for use_v14 in [True, False]:
        for use_ml in [True, False]:
            key = f"v14={use_v14}_ml={use_ml}"
            trade_sets[key] = generate_trades(all_dfs, use_v14, use_ml, regime_map)
            print(f"  {key}: {len(trade_sets[key])} işlem")
    
    # ━━━━ KONFİGÜRASYON MATRİSİ ━━━━
    friction_options = [
        ("Market(Taker)", 0.0018),
        ("Limit(Maker)", 0.0006),
        ("Limit+BNB", 0.0005),
    ]
    
    filter_options = [
        ("V10(Filtersiz)", "v14=False_ml=False"),
        ("V14(AntiLiq)", "v14=True_ml=False"),
        ("V14+ML(Hibrit)", "v14=True_ml=True"),
    ]
    
    # Grid Search Optimal ORP params (optimization_results.md)
    orp_options = [
        ("ORP_Eski(%5/1.5/15)", 0.15, 1.5, 0.05, 0.20, 15, True),    # Eski V14 parametreleri
        ("ORP_GridOpt(%10/1.0/10)", 0.10, 1.0, 0.04, 0.20, 10, True), # Grid Search OPTIMAL
        ("ORP_Agresif(%15/1.0/12)", 0.15, 1.0, 0.05, 0.25, 12, True), # Agresif hibrit
        ("ORP_Güvenli(%10/1.0/8)", 0.10, 1.0, 0.03, 0.15, 8, True),   # Güvenli
    ]
    
    dyn_lev_options = [
        ("Sabit", False),
        ("Dinamik", True),
    ]
    
    capital_options = [100, 500, 1000, 3000]
    
    print(f"\n🚀 {len(friction_options)*len(filter_options)*len(orp_options)*len(dyn_lev_options)*len(capital_options)} konfigürasyon test ediliyor...", flush=True)
    
    results = []
    for (fric_name, fric_rate), (filt_name, filt_key), (orp_name, cycle, recov, base_r, max_r, max_l, freeze), (dyn_name, dyn_lev), capital in product(
        friction_options, filter_options, orp_options, dyn_lev_options, capital_options
    ):
        trades = trade_sets[filt_key]
        if not trades: continue
        
        equity, min_eq, fees, monthly = simulate_equity(
            trades, capital, max_l, fric_rate, dyn_lev,
            cycle, recov, base_r, max_r, freeze
        )
        
        results.append({
            "Filtre": filt_name,
            "Emir": fric_name,
            "ORP": orp_name,
            "DynLev": dyn_name,
            "Sermaye": capital,
            "Min Kasa": min_eq,
            "Komisyon": fees,
            "NET KÂR": equity,
            "Kat": equity / capital if capital > 0 else 0,
            "monthly": monthly,
        })
    
    results.sort(key=lambda x: x["NET KÂR"], reverse=True)
    
    safe_million = [r for r in results if r["NET KÂR"] >= 1_000_000 and r["Min Kasa"] >= 5.0]
    risky_million = [r for r in results if r["NET KÂR"] >= 1_000_000 and r["Min Kasa"] < 5.0]
    safe_100k = [r for r in results if r["NET KÂR"] >= 100_000 and r["Min Kasa"] >= 5.0]
    safe_best_100 = sorted([r for r in results if r["Sermaye"] == 100 and r["Min Kasa"] >= 5.0], key=lambda x: x["NET KÂR"], reverse=True)
    
    print(f"\n{'='*80}")
    print(f" 💰 TOPLAM {len(results)} KONFİGÜRASYON TEST EDİLDİ")
    print(f" 🛡️ GÜVENLİ $1M+ SENARYOLAR: {len(safe_million)}")
    print(f" ⚠️ RİSKLİ $1M+ SENARYOLAR: {len(risky_million)}")
    print(f" 🏦 GÜVENLİ $100K+ SENARYOLAR: {len(safe_100k)}")
    print(f"{'='*80}")
    
    with open("v18_ultimate_report.md", "w") as f:
        f.write("# 🏆 V18 Ultimate: Tüm Bilgi Birikiminin Sentezi\n\n")
        f.write("Bu rapor, V7'den V17'ye kadar yapılan tüm testlerin, Grid Search optimizasyonlarının,\n")
        f.write("Makine Öğrenmesi rejim filtrelerinin, limit emir komisyon azaltmasının ve dinamik kaldıraç\n")
        f.write("stratejisinin birleşimidir. Toplam **{}** farklı konfigürasyon test edilmiştir.\n\n".format(len(results)))
        
        # ━━━ SAFE MILLIONS ━━━
        if safe_million:
            f.write("## 🛡️ GÜVENLİ MİLYONLUK SENARYOLAR (İflas Etmeden $1M+)\n\n")
            f.write("| # | Filtre | Emir | ORP | Kaldıraç | Sermaye | Min Kasa | Komisyon | NET KÂR | Kat |\n")
            f.write("| :---: | :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |\n")
            for i, r in enumerate(safe_million[:20], 1):
                f.write(f"| {i} | {r['Filtre']} | {r['Emir']} | {r['ORP']} | {r['DynLev']} | ${r['Sermaye']:,} | ${r['Min Kasa']:,.2f} | ${r['Komisyon']:,.0f} | **${r['NET KÂR']:,.0f}** | **{r['Kat']:,.0f}x** |\n")
                print(f"🛡️#{i} {r['Filtre']} | {r['Emir']} | {r['ORP']} | {r['DynLev']} | ${r['Sermaye']:,} → ${r['NET KÂR']:,.0f} (Min:${r['Min Kasa']:,.2f})")
        
        # ━━━ SAFE 100K ━━━
        if safe_100k:
            f.write(f"\n## 🏦 GÜVENLİ $100K+ SENARYOLAR (Top 20)\n\n")
            f.write("| # | Filtre | Emir | ORP | Kaldıraç | Sermaye | Min Kasa | NET KÂR | Kat |\n")
            f.write("| :---: | :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: |\n")
            for i, r in enumerate(safe_100k[:20], 1):
                f.write(f"| {i} | {r['Filtre']} | {r['Emir']} | {r['ORP']} | {r['DynLev']} | ${r['Sermaye']:,} | ${r['Min Kasa']:,.2f} | **${r['NET KÂR']:,.0f}** | **{r['Kat']:,.0f}x** |\n")
        
        # ━━━ BEST $100 START ━━━
        if safe_best_100:
            f.write(f"\n## 💡 EN İYİ $100 BAŞLANGIÇLI GÜVENLİ SENARYOLAR (Top 10)\n\n")
            f.write("| # | Filtre | Emir | ORP | Kaldıraç | Min Kasa | NET KÂR | Kat |\n")
            f.write("| :---: | :--- | :--- | :--- | :--- | :---: | :---: | :---: |\n")
            for i, r in enumerate(safe_best_100[:10], 1):
                f.write(f"| {i} | {r['Filtre']} | {r['Emir']} | {r['ORP']} | {r['DynLev']} | ${r['Min Kasa']:,.2f} | **${r['NET KÂR']:,.0f}** | **{r['Kat']:,.0f}x** |\n")
        
        # ━━━ BEST OVERALL MONTHLY ━━━
        overall_best = safe_million[0] if safe_million else (safe_100k[0] if safe_100k else results[0])
        f.write(f"\n## 🏆 EN OPTİMAL SENARYO: Aylık Dağılım\n\n")
        f.write(f"**Konfigürasyon:** {overall_best['Filtre']} + {overall_best['Emir']} + {overall_best['ORP']} + {overall_best['DynLev']} + ${overall_best['Sermaye']:,} Sermaye\n\n")
        f.write("| Ay | Başlangıç | Bitiş | İşlem | Win Rate | Büyüme |\n")
        f.write("| :--- | :---: | :---: | :---: | :---: | :---: |\n")
        for m_key, d in overall_best["monthly"].items():
            wr = (d["wins"]/(d["wins"]+d["losses"])*100) if (d["wins"]+d["losses"]) > 0 else 0
            growth = ((d["end_eq"] - d["start_eq"]) / d["start_eq"] * 100) if d["start_eq"] > 0 else 0
            f.write(f"| **{m_key}** | ${d['start_eq']:,.2f} | **${d['end_eq']:,.2f}** | {d['trades']} | %{wr:.1f} | **%{growth:.1f}** |\n")
            print(f"  {m_key}: ${d['start_eq']:,.2f} → ${d['end_eq']:,.2f} | WR: %{wr:.1f} | Büyüme: %{growth:.1f}")
    
    print(f"\n✅ Rapor v18_ultimate_report.md dosyasına kaydedildi!")

if __name__ == "__main__":
    main()
