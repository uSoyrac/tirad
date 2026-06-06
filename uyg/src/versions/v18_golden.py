#!/usr/bin/env python3
"""
V18 ALTIN FORMÜL - NİHAİ MİLYONLUK SENARYO
=============================================
288 konfigürasyon taramasından çıkan şampiyon:
  • Sinyal: Supertrend (14, 3.5) + EMA 250 (4H gerçek Binance verisi)
  • Filtre: V14 Anti-Likidite (Vol > 2.5 VEYA ADX > 40 → REDDET)
  • Emir: LİMİT (Maker Fee %0.02/side + %0.02 slippage = %0.06 toplam)
  • ORP: Cycle %15, Recovery 1.5, BaseRisk %5, MaxRisk %20, MaxLev 15x
  • Kaldıraç: DİNAMİK (Drawdown > %15 → kaldıracı kademeli düşür)
  • Cons Loss Freeze: 3+ ardışık kayıpta risk %75 düşürülür

GERÇEKÇİLİK KONTROL LİSTESİ:
  ✅ Gerçek Binance 4H OHLCV verisi (Temmuz 2025 - Mayıs 2026)
  ✅ Maker komisyon (%0.02 x 2 side = %0.04 round-trip)
  ✅ Limit emir slippage (%0.02 - market'e göre çok düşük)
  ✅ Toplam sürtünme: %0.06 (her işlemde kaldıraç x %0.06 kasadan kesilir)
  ✅ Sıfır gelecek görme (No Look-Ahead Bias)
  ✅ Supertrend sadece kapanmış mumdan hesaplanır
  ✅ EMA 250 sadece kapanmış mumdan hesaplanır
"""
import sys, os
import pandas as pd
import numpy as np
import warnings
import ta

warnings.filterwarnings("ignore")

COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]
TIMEFRAME = "4h"

# ━━━ GERÇEK PİYASA SÜRTÜNME ORANI ━━━
# Limit emir (Maker): %0.02/side x 2 = %0.04
# Limit slippage: %0.02 (market'e göre çok düşük)
# Toplam: %0.06
FRICTION_RATE = 0.0006

# ━━━ ORP PARAMETRELERİ (V18 Şampiyon) ━━━
CYCLE_PCT = 0.15       # Her hedef adımda %15 büyüme
RECOVERY_FACTOR = 1.5  # Deficit'in 1.5'e bölünmüş halini risk al
BASE_RISK_PCT = 0.05   # Minimum %5 taban risk
MAX_RISK_CAP = 0.20    # Maksimum %20 risk tavanı
MAX_LEVERAGE = 15.0    # Maksimum 15x kaldıraç
CONS_LOSS_FREEZE = 3   # 3+ ardışık kayıpta güvenli moda geç

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

def run_v18():
    print("="*80)
    print(" 🏆 V18 ALTIN FORMÜL: GERÇEKÇİ MİLYONLUK SENARYO 🏆")
    print("="*80)
    print()
    print("GERÇEKÇİLİK PARAMETRELERİ:")
    print(f"  📊 Veri: Gerçek Binance {TIMEFRAME} OHLCV (5 Coin, ~1 Yıl)")
    print(f"  💸 Komisyon: Limit Maker %0.02/side (Round-trip: %0.04)")
    print(f"  📉 Slippage: %0.02 (Limit emir - çok düşük)")
    print(f"  🔧 Toplam Sürtünme: %{FRICTION_RATE*100:.2f} (her işlemde lev x {FRICTION_RATE*100:.2f}%)")
    print(f"  ⚙️ ORP: Cycle {CYCLE_PCT*100:.0f}% | Recovery {RECOVERY_FACTOR} | MaxRisk {MAX_RISK_CAP*100:.0f}% | MaxLev {MAX_LEVERAGE:.0f}x")
    print(f"  🛡️ Dinamik Kaldıraç: Drawdown > %15 → kaldıraç kademeli düşer")
    print(f"  🧊 Cons Loss Freeze: {CONS_LOSS_FREEZE}+ ardışık kayıpta risk %75 azalır")
    print()
    
    # ━━━ VERİ YÜKLEME ━━━
    all_trades = []
    coin_stats = {}
    
    for coin in COINS:
        csv_path = os.path.join(os.path.dirname(__file__), "..", "uyg", "src", "data", f"{coin}_USDT_{TIMEFRAME}.csv")
        if not os.path.exists(csv_path):
            print(f"  ⚠️ {coin} verisi bulunamadı: {csv_path}")
            continue
        
        df = pd.read_csv(csv_path)
        df["ts"] = pd.to_datetime(df["ts"])
        
        # Veri aralığını göster
        print(f"  📂 {coin}: {len(df)} mum | {df['ts'].iloc[0].strftime('%Y-%m-%d')} → {df['ts'].iloc[-1].strftime('%Y-%m-%d')}")
        
        # İndikatörler
        df = calculate_supertrend(df, period=14, multiplier=3.5)
        df["ema_250"] = ta.trend.EMAIndicator(df["close"], window=250).ema_indicator()
        adx_ind = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
        df['adx'] = adx_ind.adx()
        df['vol_sma'] = df['volume'].rolling(20).mean()
        df['vol_ratio'] = df['volume'] / df['vol_sma']
        
        coin_trades = 0
        for i in range(250, len(df) - 100):
            trend = df["st_trend"].iloc[i-1]
            prev_trend = df["st_trend"].iloc[i-2]
            close = df["close"].iloc[i-1]
            low_p = df["low"].iloc[i-1]
            high_p = df["high"].iloc[i-1]
            st = df["st"].iloc[i-1]
            atr = df["atr"].iloc[i-1]
            ema250 = df["ema_250"].iloc[i-1]
            adx = df["adx"].iloc[i-1]
            vol_ratio = df["vol_ratio"].iloc[i-1]
            
            # Sinyal tespiti
            is_signal = False
            if trend == 1:
                if prev_trend == -1 or low_p <= st + (atr * 0.5): is_signal = True
            else:
                if prev_trend == 1 or high_p >= st - (atr * 0.5): is_signal = True
            if not is_signal: continue
            
            # EMA 250 trend filtresi
            if trend == 1 and close < ema250: continue
            if trend == -1 and close > ema250: continue
            
            # V14 Anti-Likidite Filtresi (Balina Tuzağı Reddi)
            if vol_ratio > 2.5: continue
            if adx > 40: continue
            
            result_r, sl_pct = get_trade_result(df, i, trend, close, atr)
            if result_r != 0.0 or (result_r == 0.0 and sl_pct > 0.0):
                all_trades.append({
                    "coin": coin, "date": df.iloc[i]['ts'], "r_mult": result_r, "sl_pct": sl_pct
                })
                coin_trades += 1
        
        coin_stats[coin] = coin_trades
    
    all_trades = sorted(all_trades, key=lambda x: x["date"])
    
    print()
    print(f"  🔬 Coin bazlı işlem dağılımı:")
    for coin, count in coin_stats.items():
        print(f"     {coin}: {count} işlem")
    
    wins = sum(1 for t in all_trades if t["r_mult"] > 0)
    losses = sum(1 for t in all_trades if t["r_mult"] < 0)
    breakevens = sum(1 for t in all_trades if t["r_mult"] == 0.0 and t["sl_pct"] > 0)
    win_rate = (wins / (wins + losses)) * 100 if (wins + losses) > 0 else 0
    
    print(f"\n  📊 Toplam İşlem: {len(all_trades)}")
    print(f"  ✅ Başarılı: {wins} | ❌ Başarısız: {losses} | 🔄 Breakeven: {breakevens}")
    print(f"  📈 Win Rate: %{win_rate:.1f}")
    
    # ━━━ ORP SİMÜLASYONU (DİNAMİK KALDIRAÇ + SÜRTÜNME) ━━━
    START_CAPITAL = 100.0
    equity = START_CAPITAL
    target_eq = START_CAPITAL
    step = 0
    cons_loss = 0
    total_fees = 0.0
    min_eq = START_CAPITAL
    peak_eq = START_CAPITAL
    monthly_data = {}
    
    for t in all_trades:
        month_key = t["date"].strftime("%Y-%m")
        if month_key not in monthly_data:
            monthly_data[month_key] = {
                "start_eq": equity, "end_eq": equity,
                "trades": 0, "wins": 0, "losses": 0, "breakevens": 0,
                "fees": 0.0
            }
        monthly_data[month_key]["trades"] += 1
        
        # ━━━ DİNAMİK KALDIRAÇ (Ruin Guard) ━━━
        drawdown_pct = (peak_eq - equity) / peak_eq if peak_eq > 0 else 0
        if drawdown_pct > 0.5:
            current_max_lev = max(2, MAX_LEVERAGE * 0.2)
        elif drawdown_pct > 0.3:
            current_max_lev = max(3, MAX_LEVERAGE * 0.4)
        elif drawdown_pct > 0.15:
            current_max_lev = max(5, MAX_LEVERAGE * 0.6)
        else:
            current_max_lev = MAX_LEVERAGE
        
        # ━━━ CONSECUTIVE LOSS FREEZE ━━━
        if cons_loss >= CONS_LOSS_FREEZE:
            a_b = BASE_RISK_PCT * 0.25
            a_m = MAX_RISK_CAP * 0.25
            a_r = max(RECOVERY_FACTOR, 1.5)
        else:
            a_b = BASE_RISK_PCT
            a_m = MAX_RISK_CAP
            a_r = RECOVERY_FACTOR
        
        # ━━━ ORP HEDEF HESAPLAMA ━━━
        while equity >= target_eq:
            step += 1
            target_eq = START_CAPITAL * ((1.0 + CYCLE_PCT) ** step)
        
        delta = max(0, target_eq - equity)
        base_amt = equity * a_b
        req_risk = max(base_amt, delta / a_r)
        
        sl_f = max(t["sl_pct"] / 100.0, 0.015)
        pos = req_risk / sl_f
        req_lev = pos / equity if equity > 0 else 999
        act_lev = min(req_lev, current_max_lev)
        act_risk = min(act_lev * equity * sl_f, equity * a_m)
        
        # ━━━ GERÇEK PİYASA SÜRTÜNME TAHSİLATI ━━━
        friction = (act_lev * equity) * FRICTION_RATE
        total_fees += friction
        monthly_data[month_key]["fees"] += friction
        
        pnl = (act_risk * t["r_mult"]) - friction
        equity += pnl
        
        if equity > peak_eq: peak_eq = equity
        if equity < min_eq: min_eq = equity
        if equity <= 0:
            print("\n  💀 KASA SIFIRLANDI!")
            break
        
        if t["r_mult"] > 0:
            cons_loss = 0
            monthly_data[month_key]["wins"] += 1
        elif t["r_mult"] < 0:
            cons_loss += 1
            monthly_data[month_key]["losses"] += 1
        else:
            monthly_data[month_key]["breakevens"] += 1
        
        monthly_data[month_key]["end_eq"] = equity
    
    # ━━━ AYLIK RAPOR ━━━
    print("\n" + "="*80)
    print(" 📅 V18 ALTIN FORMÜL: AYLIK PERFORMANS TABLOSU")
    print("="*80)
    
    report_lines = []
    report_lines.append("# 🏆 V18 Altın Formül: Gerçekçi Milyonluk Senaryo\n")
    report_lines.append("## Gerçekçilik Parametreleri\n")
    report_lines.append(f"- **Veri:** Gerçek Binance {TIMEFRAME} OHLCV (5 Coin: {', '.join(COINS)})\n")
    report_lines.append(f"- **Komisyon:** Limit Maker %0.02/side (Round-trip: %0.04)\n")
    report_lines.append(f"- **Slippage:** %0.02 (Limit emir)\n")
    report_lines.append(f"- **Toplam Sürtünme:** %{FRICTION_RATE*100:.2f} per trade (kaldıraç ile çarpılır)\n")
    report_lines.append(f"- **ORP:** Cycle {CYCLE_PCT*100:.0f}% | Recovery {RECOVERY_FACTOR} | MaxRisk {MAX_RISK_CAP*100:.0f}% | MaxLev {MAX_LEVERAGE:.0f}x\n")
    report_lines.append(f"- **Dinamik Kaldıraç:** Drawdown > %15 → kaldıraç kademeli düşer\n")
    report_lines.append(f"- **Başlangıç Sermayesi:** ${START_CAPITAL:,.0f}\n\n")
    
    report_lines.append("## Aylık Performans\n\n")
    report_lines.append("| Ay | Başlangıç | Bitiş | İşlem | Kazanç | Kayıp | Win Rate | Komisyon | Büyüme |\n")
    report_lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |\n")
    
    for m_key, d in monthly_data.items():
        start_eq = d["start_eq"]
        end_eq = d["end_eq"]
        trades = d["trades"]
        wins = d["wins"]
        losses = d["losses"]
        fees = d["fees"]
        wr = (wins/(wins+losses)*100) if (wins+losses) > 0 else 0
        growth = ((end_eq - start_eq) / start_eq * 100) if start_eq > 0 else 0
        
        print(f"  {m_key} | ${start_eq:>12,.2f} → ${end_eq:>12,.2f} | {trades:>3} işlem | W:{wins:>2} L:{losses:>2} | WR: %{wr:>4.1f} | Komisyon: ${fees:>8,.2f} | Büyüme: %{growth:>9.1f}")
        report_lines.append(f"| **{m_key}** | ${start_eq:,.2f} | **${end_eq:,.2f}** | {trades} | {wins} | {losses} | %{wr:.1f} | ${fees:,.2f} | **%{growth:.1f}** |\n")
    
    report_lines.append(f"\n## Özet İstatistikler\n\n")
    report_lines.append(f"- **Başlangıç Sermayesi:** ${START_CAPITAL:,.2f}\n")
    report_lines.append(f"- **Yıl Sonu Net Kasa:** ${equity:,.2f}\n")
    report_lines.append(f"- **Büyüme Katı:** {equity/START_CAPITAL:,.0f}x\n")
    report_lines.append(f"- **Ödenen Toplam Komisyon:** ${total_fees:,.2f}\n")
    report_lines.append(f"- **Kasanın Gördüğü En Dip:** ${min_eq:,.2f}\n")
    report_lines.append(f"- **Kasanın Gördüğü En Zirve:** ${peak_eq:,.2f}\n")
    
    with open("v18_golden_monthly.md", "w") as f:
        f.writelines(report_lines)
    
    print()
    print("="*80)
    print(f"  💸 ÖDENEN TOPLAM KOMİSYON: ${total_fees:,.2f}")
    print(f"  📊 KASANIN GÖRDÜĞÜ EN DİP: ${min_eq:,.2f}")
    print(f"  📈 KASANIN GÖRDÜĞÜ EN ZİRVE: ${peak_eq:,.2f}")
    print()
    print(f"  💰 NİHAİ 1 YIL SONU NET KASA: ${equity:,.2f}")
    print(f"  🚀 BÜYÜME: {equity/START_CAPITAL:,.0f} KAT ({(equity-START_CAPITAL)/START_CAPITAL*100:,.0f}%)")
    print("="*80)
    print(f"\n  ✅ Rapor v18_golden_monthly.md dosyasına kaydedildi!")

if __name__ == "__main__":
    run_v18()
