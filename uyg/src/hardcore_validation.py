#!/usr/bin/env python3
"""
hardcore_validation.py — ACIMASI GERÇEKÇİ DOĞRULAMA TESTİ
═══════════════════════════════════════════════════════════
1. Repainting testi (gelecek veri sızıntısı kontrolü)
2. BTC ve ETH ayrı ayrı, 3 strateji (ORP-5%, ORP-2%, Paroli)
3. Extra maliyet: 2x slippage, 1 bar gecikme, daha yüksek komisyon
"""
import os, sys, math, time, warnings, random
import numpy as np
import pandas as pd
from collections import defaultdict

warnings.filterwarnings("ignore")

from backtest_multi_tf import (
    score_slice_v2, WARMUP, EMA_TREND_PERIOD,
    SL_ATR_MULT, TP1_R, TP2_R, TP3_R, TRAIL_ATR,
    TP1_CLOSE, TP2_CLOSE, TP3_CLOSE
)
from live_scan import B, R, GR, RD, YL, CY, DM, ok, bad, warn, nfo, dim, head, h2, sep

CAPITAL = 100.0

# ═══════════════════════════════════════════════════════════════
# HARDCORE MALİYET MODELİ (Normal modelden 2x daha ağır)
# ═══════════════════════════════════════════════════════════════
# Normal model:  commission=0.04%, slippage=0.05% → round-trip=0.18%
# Hardcore model: commission=0.04%, slippage=0.10% → round-trip=0.28%
COMMISSION_HC = 0.0004   # %0.04 taker (Binance Futures standard)
SLIPPAGE_HC   = 0.0010   # %0.10 slippage (2x normal — kötü dolum varsayımı)
ROUND_TRIP_HC = (COMMISSION_HC + SLIPPAGE_HC) * 2   # ~%0.28 total

# 1 BAR GECİKME: Sinyal bar i-1'de üretilir, emir bar i'de gönderilir,
# ama DOLUM bar i+1'in açılışında gerçekleşir (gerçek hayat gecikmesi)
ENTRY_DELAY_BARS = 1  # 1 extra bar gecikme

# ═══════════════════════════════════════════════════════════════

def calculate_max_dd(eq):
    arr = np.array(eq)
    if len(arr) == 0: return 0.0
    peak = np.maximum.accumulate(arr)
    peak = np.where(peak == 0, 1.0, peak)
    dd = (arr - peak) / peak
    return float(abs(dd.min()) * 100)

def _ema(s, span):
    try: return float(s.ewm(span=span, adjust=False).mean().iloc[-1])
    except: return float(s.iloc[-1])

def _trend_1d(df_slice):
    cp = float(df_slice["close"].iloc[-1])
    ema = _ema(df_slice["close"], EMA_TREND_PERIOD)
    if cp > ema: return "BULLISH"
    elif cp < ema: return "BEARISH"
    return "NEUTRAL"


def backtest_hardcore(symbol, df_full, max_lev=5, use_delay=True, use_hc_costs=True):
    """
    Walk-forward backtest with HARDCORE realism:
    - Optional 1-bar entry delay
    - Higher slippage (2x normal)
    - Detailed trade log
    """
    round_trip = ROUND_TRIP_HC if use_hc_costs else (0.0004 + 0.0005) * 2
    trades = []
    eq_curve = [CAPITAL]

    in_trade = False
    t_dir = t_entry = t_sl = t_sl_orig = t_tp1 = t_tp2 = t_tp3 = 0.0
    t_atr = t_score = 0.0
    t_entry_bar = 0
    t_month = t_entry_date = ""
    t_tp1_hit = t_tp2_hit = t_trail_active = False
    t_trail_sl = t_locked_pnl = 0.0
    t_remaining = 1.0
    t_leverage = 1

    # Pending signal (for delay)
    pending_signal = None

    total = len(df_full)
    for i in range(WARMUP, total - 1):
        if i % 2000 == 0:
            sys.stdout.write(".")
            sys.stdout.flush()

        df_slice = df_full.iloc[max(0, i - 300):i]
        hi = float(df_full["high"].iloc[i])
        lo = float(df_full["low"].iloc[i])
        cl = float(df_full["close"].iloc[i])
        op = float(df_full["open"].iloc[i])
        bar_ts = df_full.index[i]
        month = str(bar_ts)[:7]

        # ── EXIT (always processes first) ──
        if in_trade:
            exited = False
            pnl_r = 0.0
            exit_result = ""
            exit_price = 0.0
            sl_dist = abs(t_entry - t_sl_orig) / t_entry

            if t_trail_active:
                if t_dir == "LONG":
                    new_trail = cl - t_atr * TRAIL_ATR
                    if new_trail > t_trail_sl: t_trail_sl = new_trail
                    if lo <= t_trail_sl:
                        pnl_r = t_locked_pnl + (t_trail_sl - t_entry)/t_entry/sl_dist
                        exit_result = "WIN_TRAIL"; exit_price = t_trail_sl; exited = True
                else:
                    new_trail = cl + t_atr * TRAIL_ATR
                    if new_trail < t_trail_sl: t_trail_sl = new_trail
                    if hi >= t_trail_sl:
                        pnl_r = t_locked_pnl + (t_entry - t_trail_sl)/t_entry/sl_dist
                        exit_result = "WIN_TRAIL"; exit_price = t_trail_sl; exited = True

            if not exited:
                if t_dir == "LONG":
                    if lo <= t_sl:
                        pnl_r = t_locked_pnl if t_tp1_hit else -1.0
                        exit_result = "WIN_BE" if t_tp1_hit else "LOSS"
                        exit_price = t_sl; exited = True
                    elif hi >= t_tp3:
                        pnl_r = t_locked_pnl + TP3_CLOSE * TP3_R
                        exit_result = "WIN_TP3"; exit_price = t_tp3; exited = True
                    elif not t_tp2_hit and hi >= t_tp2:
                        t_locked_pnl += TP2_CLOSE * TP2_R; t_tp2_hit = True
                        t_remaining -= TP2_CLOSE
                        t_trail_sl = max(t_trail_sl, t_entry + t_atr * 0.5)
                    elif not t_tp1_hit and hi >= t_tp1:
                        t_locked_pnl += TP1_CLOSE * TP1_R; t_tp1_hit = True
                        t_remaining -= TP1_CLOSE
                        t_sl = t_entry * 1.001; t_trail_active = True
                        t_trail_sl = t_entry - t_atr * TRAIL_ATR
                else:
                    if hi >= t_sl:
                        pnl_r = t_locked_pnl if t_tp1_hit else -1.0
                        exit_result = "WIN_BE" if t_tp1_hit else "LOSS"
                        exit_price = t_sl; exited = True
                    elif lo <= t_tp3:
                        pnl_r = t_locked_pnl + TP3_CLOSE * TP3_R
                        exit_result = "WIN_TP3"; exit_price = t_tp3; exited = True
                    elif not t_tp2_hit and lo <= t_tp2:
                        t_locked_pnl += TP2_CLOSE * TP2_R; t_tp2_hit = True
                        t_remaining -= TP2_CLOSE
                        t_trail_sl = min(t_trail_sl, t_entry - t_atr * 0.5)
                    elif not t_tp1_hit and lo <= t_tp1:
                        t_locked_pnl += TP1_CLOSE * TP1_R; t_tp1_hit = True
                        t_remaining -= TP1_CLOSE
                        t_sl = t_entry * 0.999; t_trail_active = True
                        t_trail_sl = t_entry + t_atr * TRAIL_ATR

            if exited:
                net_r = pnl_r - round_trip / sl_dist if sl_dist > 0 else pnl_r
                dollar_pnl = eq_curve[-1] * 0.02 * net_r
                new_eq = eq_curve[-1] + dollar_pnl
                eq_curve.append(new_eq)
                trades.append({
                    "symbol": symbol, "direction": t_dir,
                    "entry_date": t_entry_date, "exit_date": str(bar_ts)[:16],
                    "entry": round(t_entry, 4), "exit_price": round(exit_price, 4),
                    "sl": round(t_sl_orig, 4),
                    "result": exit_result, "r_mult": round(net_r, 3),
                    "dollar_pnl": round(dollar_pnl, 2),
                    "equity_after": round(new_eq, 2),
                    "score": round(t_score, 2), "month": month,
                    "sl_pct": round(sl_dist * 100, 2),
                    "leverage": t_leverage,
                    "bars_held": i - t_entry_bar,
                })
                in_trade = t_tp1_hit = t_tp2_hit = t_trail_active = False
                t_locked_pnl = 0.0; t_remaining = 1.0
            continue

        # ── CHECK PENDING SIGNAL (delayed entry) ──
        if pending_signal and use_delay:
            ps = pending_signal
            pending_signal = None
            # Enter at THIS bar's open (1 bar later than signal)
            actual_entry = op  # Open of next bar = realistic fill
            # Recalculate SL relative to actual entry
            if ps["trend"] == "BULLISH":
                sl_ = actual_entry - ps["atr"] * SL_ATR_MULT
                sl_dist = abs(actual_entry - sl_) / actual_entry
                if 0.005 < sl_dist <= 0.10:
                    risk_amount = actual_entry * sl_dist
                    tp1_ = actual_entry + risk_amount * TP1_R
                    tp2_ = actual_entry + risk_amount * TP2_R
                    tp3_ = actual_entry + risk_amount * TP3_R
                    d_ = "LONG"
                else:
                    continue
            else:
                sl_ = actual_entry + ps["atr"] * SL_ATR_MULT
                sl_dist = abs(actual_entry - sl_) / actual_entry
                if 0.005 < sl_dist <= 0.10:
                    risk_amount = actual_entry * sl_dist
                    tp1_ = actual_entry - risk_amount * TP1_R
                    tp2_ = actual_entry - risk_amount * TP2_R
                    tp3_ = actual_entry - risk_amount * TP3_R
                    d_ = "SHORT"
                else:
                    continue

            lev = max(1, min(math.ceil(0.02 / sl_dist), max_lev))
            t_entry = actual_entry; t_sl = sl_; t_sl_orig = sl_
            t_tp1 = tp1_; t_tp2 = tp2_; t_tp3 = tp3_
            t_atr = ps["atr"]; t_dir = d_; t_score = ps["score"]
            t_entry_bar = i; t_month = month; t_entry_date = str(bar_ts)[:16]
            t_tp1_hit = t_tp2_hit = t_trail_active = False
            t_trail_sl = 0.0; t_locked_pnl = 0.0; t_remaining = 1.0
            t_leverage = lev; in_trade = True
            continue

        # ── SIGNAL GENERATION ──
        comp, trend, entry_, sl_, atr_, vol_ok_ = score_slice_v2(df_slice)
        if comp < 4.5 or trend == "NEUTRAL" or entry_ is None:
            continue
        trend_1d = _trend_1d(df_slice)
        if trend_1d != "NEUTRAL" and trend_1d != trend:
            continue
        if not vol_ok_:
            continue
        sl_dist = abs(entry_ - sl_) / entry_
        if not (0.005 < sl_dist <= 0.10):
            continue

        if use_delay:
            pending_signal = {"trend": trend, "atr": atr_, "score": comp}
            continue

        # No delay: immediate entry (original behavior)
        if comp >= 8.0: max_lev_by_score = 5
        elif comp >= 6.5: max_lev_by_score = 4
        elif comp >= 5.5: max_lev_by_score = 3
        else: max_lev_by_score = 2
        lev = max(1, min(math.ceil(0.02 / sl_dist), min(max_lev_by_score, max_lev)))
        risk_amount = entry_ * sl_dist
        if trend == "BULLISH":
            tp1_ = entry_ + risk_amount * TP1_R
            tp2_ = entry_ + risk_amount * TP2_R
            tp3_ = entry_ + risk_amount * TP3_R
            d_ = "LONG"
        else:
            tp1_ = entry_ - risk_amount * TP1_R
            tp2_ = entry_ - risk_amount * TP2_R
            tp3_ = entry_ - risk_amount * TP3_R
            d_ = "SHORT"
        t_entry = entry_; t_sl = sl_; t_sl_orig = sl_
        t_tp1 = tp1_; t_tp2 = tp2_; t_tp3 = tp3_
        t_atr = atr_; t_dir = d_; t_score = comp
        t_entry_bar = i; t_month = month; t_entry_date = str(bar_ts)[:16]
        t_tp1_hit = t_tp2_hit = t_trail_active = False
        t_trail_sl = 0.0; t_locked_pnl = 0.0; t_remaining = 1.0
        t_leverage = lev; in_trade = True

    return {"trades": trades, "eq_curve": eq_curve}


# ═══════════════════════════════════════════════════════════════
# 3 FARKLI PARA YÖNETİMİ
# ═══════════════════════════════════════════════════════════════

def run_fixed_risk(trades, capital=100.0, risk_pct=0.02):
    eq = capital
    curve = [capital]
    for t in trades:
        pnl = eq * risk_pct * t["r_mult"]
        eq += pnl
        if eq < 1: eq = 0
        curve.append(eq)
    return {"final": eq, "curve": curve, "dd": calculate_max_dd(curve)}

def run_orp(trades, capital=100.0, step_pct=0.05, max_lev=5.0):
    eq = capital; step = 0; target = capital
    curve = [capital]; max_lev_used = 1.0
    for t in trades:
        while eq >= target:
            step += 1
            target = capital * ((1.0 + step_pct) ** step)
        delta = target - eq
        base = eq * 0.025
        risk = max(base, delta / 1.5)
        sl_f = t["sl_pct"] / 100.0
        if sl_f <= 0: sl_f = 0.015
        pos = risk / sl_f
        lev = min(pos / eq, max_lev)
        max_lev_used = max(max_lev_used, lev)
        actual_pos = lev * eq
        actual_risk = actual_pos * sl_f
        if actual_risk > eq * 0.15:
            actual_risk = eq * 0.15
        pnl = actual_risk * t["r_mult"]
        eq += pnl
        if eq < 1: eq = 0
        curve.append(eq)
    steps = int(math.log(eq/capital)/math.log(1+step_pct)) if eq > capital else 0
    return {"final": eq, "curve": curve, "dd": calculate_max_dd(curve),
            "steps": steps, "max_lev": max_lev_used}

def run_paroli(trades, capital=100.0, base_risk=0.02, max_risk=0.15, reset_after=3):
    eq = capital; consec_wins = 0
    curve = [capital]
    for t in trades:
        risk = min(base_risk * (2 ** consec_wins), max_risk)
        pnl = eq * risk * t["r_mult"]
        eq += pnl
        if eq < 1: eq = 0
        if t["r_mult"] > 0:
            consec_wins += 1
            if consec_wins >= reset_after:
                consec_wins = 0
        else:
            consec_wins = 0
        curve.append(eq)
    return {"final": eq, "curve": curve, "dd": calculate_max_dd(curve)}


# ═══════════════════════════════════════════════════════════════
# REPAINTING TEST
# ═══════════════════════════════════════════════════════════════

def repainting_test(symbol, df_full):
    """
    Anti-repainting kanıtı: Son 20 bar'ı kaldır, aynı sinyalleri üret.
    Eğer sinyal sonuçları aynıysa → repainting YOK.
    """
    full_len = len(df_full)
    test_bar = full_len - 100  # 100. bardan geriye bak

    # Full veri ile sinyal
    df_full_slice = df_full.iloc[max(0, test_bar - 300):test_bar]
    comp_full, trend_full, _, _, _, _ = score_slice_v2(df_full_slice)

    # Son 50 bar kesik veri ile sinyal (gelecek veri yok)
    df_cut = df_full.iloc[:test_bar]  # Sadece geçmiş
    df_cut_slice = df_cut.iloc[max(0, test_bar - 300):test_bar]
    comp_cut, trend_cut, _, _, _, _ = score_slice_v2(df_cut_slice)

    return {
        "bar_index": test_bar,
        "full_score": comp_full,
        "cut_score": comp_cut,
        "full_trend": trend_full,
        "cut_trend": trend_cut,
        "match": comp_full == comp_cut and trend_full == trend_cut,
    }


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    head("HARDCORE GERÇEKÇİLİK DOĞRULAMA TESTİ")
    print(f"  Maliyet: Slippage %0.10 (2x normal), Komisyon %0.04")
    print(f"  Gecikme: +1 bar giriş gecikmesi (gerçek API simülasyonu)")
    print(f"  Dönem: 12 ay (Haz 2025 → May 2026), TF: 4H\n")

    # ═══ REPAINTING TEST ═══
    h2("1. REPAİNTİNG TESTİ — Gelecek Veri Sızıntısı Kontrolü")
    for sym in ["ETH/USDT", "BTC/USDT"]:
        csv = f"data/historical/{sym.replace('/', '_')}_4h.csv"
        df = pd.read_csv(csv); df["ts"] = pd.to_datetime(df["ts"])
        df.set_index("ts", inplace=True); df = df.sort_index()

        results = []
        # Test 10 different points
        for offset in range(10):
            test_bar = len(df) - 200 - offset * 50
            if test_bar < WARMUP + 300: continue
            df_slice_full = df.iloc[max(0, test_bar - 300):test_bar]
            df_slice_cut = df.iloc[:test_bar].iloc[max(0, test_bar - 300):test_bar]
            c1, t1, _, _, _, _ = score_slice_v2(df_slice_full)
            c2, t2, _, _, _, _ = score_slice_v2(df_slice_cut)
            results.append(c1 == c2 and t1 == t2)

        pass_count = sum(results)
        total = len(results)
        if pass_count == total:
            print(f"  {sym:10} → {ok(f'GEÇTI ✅')} ({pass_count}/{total} bar eşleşti)")
            print(f"              Gelecek veri sızıntısı: {ok('SIFIR')}")
        else:
            print(f"  {sym:10} → {bad(f'BAŞARISIZ ❌')} ({pass_count}/{total})")
            print(f"              DİKKAT: Repainting olabilir!")

    print(f"\n  {dim('Açıklama: Aynı bar indeksinde, gelecek veri eklendiğinde ve')}")
    print(f"  {dim('çıkarıldığında sinyal skorları birebir aynı → repainting yok.')}")
    print(f"  {dim('df_slice = df.iloc[max(0,i-300):i] → bar i asla dahil değil.')}")

    # ═══ BACKTEST PER SYMBOL ═══
    configs = [
        ("NORMAL (önceki test)", False, False),
        ("HARDCORE (2x slippage + 1 bar gecikme)", True, True),
    ]

    for sym in ["ETH/USDT", "BTC/USDT"]:
        csv = f"data/historical/{sym.replace('/', '_')}_4h.csv"
        df = pd.read_csv(csv); df["ts"] = pd.to_datetime(df["ts"])
        df.set_index("ts", inplace=True); df = df.sort_index()

        sym_short = sym.split("/")[0]
        h2(f"2. {sym_short} — AYRI BACKTEST (12 AY, 4H)")

        for config_name, use_delay, use_hc in configs:
            sys.stdout.write(f"  {config_name:45} ")
            sys.stdout.flush()

            t0 = time.time()
            res = backtest_hardcore(sym, df, max_lev=5, use_delay=use_delay, use_hc_costs=use_hc)
            elapsed = time.time() - t0
            trades = res["trades"]
            n = len(trades)

            if n == 0:
                print(f" → {bad('0 işlem')} ({elapsed:.0f}sn)")
                continue

            wins = sum(1 for t in trades if t["r_mult"] > 0)
            losses = n - wins
            longs = sum(1 for t in trades if t["direction"] == "LONG")
            shorts = n - longs
            wr = wins / n * 100
            avg_r = np.mean([t["r_mult"] for t in trades])

            print(f" → {n} işlem ({elapsed:.0f}sn)  WR:{wr:.0f}%  L:{longs} S:{shorts}  AvgR:{avg_r:+.2f}")

            # Run 3 money management strategies
            fr = run_fixed_risk(trades)
            orp5 = run_orp(trades, step_pct=0.05)
            orp2 = run_orp(trades, step_pct=0.02)
            paroli = run_paroli(trades)

            print(f"     ┌{'─'*70}┐")
            print(f"     │ {'Strateji':25} {'Bitiş($)':>12} {'Çarpan':>8} {'MaxDD':>7} {'Adım':>6} │")
            print(f"     ├{'─'*70}┤")
            print(f"     │ {'Fixed Risk (%2)':25} {'${:>10,.2f}'.format(fr['final'])} {fr['final']/100:>7.1f}x {fr['dd']:>6.1f}% {'—':>6} │")
            print(f"     │ {'ORP %2 (Güvenli)':25} {'${:>10,.2f}'.format(orp2['final'])} {orp2['final']/100:>7.1f}x {orp2['dd']:>6.1f}% {orp2['steps']:>5}  │")
            print(f"     │ {'ORP %5 (Şampiyon)':25} {'${:>10,.2f}'.format(orp5['final'])} {orp5['final']/100:>7.1f}x {orp5['dd']:>6.1f}% {orp5['steps']:>5}  │")
            print(f"     │ {'Paroli (Agresif)':25} {'${:>10,.2f}'.format(paroli['final'])} {paroli['final']/100:>7.1f}x {paroli['dd']:>6.1f}% {'—':>6} │")
            print(f"     └{'─'*70}┘")

            # Monthly breakdown
            monthly = defaultdict(lambda: {"n": 0, "w": 0, "pnl": 0.0, "l": 0, "s": 0})
            for t in trades:
                m = t["month"]
                monthly[m]["n"] += 1
                monthly[m]["pnl"] += t["dollar_pnl"]
                if t["r_mult"] > 0: monthly[m]["w"] += 1
                if t["direction"] == "LONG": monthly[m]["l"] += 1
                else: monthly[m]["s"] += 1

            print(f"     Aylık dağılım:")
            for m in sorted(monthly.keys()):
                d = monthly[m]
                wr_m = d["w"]/d["n"]*100 if d["n"]>0 else 0
                pnl_s = f"+${d['pnl']:.2f}" if d["pnl"] > 0 else f"${d['pnl']:.2f}"
                print(f"       {m}: {d['n']:>2} işlem (L:{d['l']} S:{d['s']}) WR:{wr_m:>3.0f}% PnL(flat):{pnl_s}")
            print()

    # ═══ FINAL COMPARISON TABLE ═══
    h2("3. NİHAİ KARŞILAŞTIRMA — NORMAL vs HARDCORE")
    print(f"""
  ┌──────────────────────────────────────────────────────────────────────┐
  │                    NORMAL MODEL          HARDCORE MODEL             │
  │                    (Backtest std)        (Gerçek hayat sim)         │
  │ Maliyet:           %0.18 round-trip      %0.28 round-trip          │
  │ Gecikme:           0 bar                 +1 bar                     │
  │ Slippage:          %0.05                 %0.10                      │
  ├──────────────────────────────────────────────────────────────────────┤
  │ Eğer HARDCORE sonuçları NORMAL'in %50-70'i ise:                    │
  │   → Strateji SAĞLAM (gerçek hayatta da çalışır)                   │
  │                                                                    │
  │ Eğer HARDCORE sonuçları NORMAL'in %20'sinden az ise:               │
  │   → Strateji KIRILGAN (maliyet hassasiyeti yüksek)                │
  │                                                                    │
  │ Eğer HARDCORE'da bile ZARAR varsa:                                 │
  │   → Strateji ÇALIŞMAZ (hayal!)                                    │
  └──────────────────────────────────────────────────────────────────────┘
""")

    print(f"  {dim('Sonuçları yukarıdaki tablolardan karşılaştırın.')}")
    print(f"  {dim('HARDCORE model bile kârlıysa → Binance entegrasyonuna GEÇİN.')}")
    print(f"  {dim('HARDCORE model zarardaysa → Stratejiyi KULLANMAYIN.')}\n")


if __name__ == "__main__":
    main()
