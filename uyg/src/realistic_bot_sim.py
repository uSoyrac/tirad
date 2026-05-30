#!/usr/bin/env python3
"""
realistic_bot_sim.py — Gerçekçi 12 Aylık Binance Bot Simülasyonu
═════════════════════════════════════════════════════════════════
$100 başlangıç, 4H, ETH/BTC/SOL/XRP üzerinde S3 + ORP-5% stratejisi.
Her trade detaylı loglanır: tarih, yön, giriş, çıkış, kaldıraç, PnL vb.
"""
import os, sys, math, time, warnings
import numpy as np
import pandas as pd
from collections import defaultdict
from datetime import datetime

warnings.filterwarnings("ignore")

# Import from existing codebase
from backtest_multi_tf import (
    score_slice_v2, WARMUP, EMA_TREND_PERIOD, VOL_MULT,
    SL_ATR_MULT, TP1_R, TP2_R, TP3_R, TRAIL_ATR,
    TP1_CLOSE, TP2_CLOSE, TP3_CLOSE, COMMISSION, SLIPPAGE, ROUND_TRIP
)
from live_scan import B, R, GR, RD, YL, CY, DM, ok, bad, warn, nfo, dim, head, h2, sep

CAPITAL = 100.0
SYMBOLS = ["ETH/USDT", "BTC/USDT", "SOL/USDT", "XRP/USDT"]
TIMEFRAME = "4h"

# ═══════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════

def calculate_max_dd(equity_curve):
    eq = np.array(equity_curve)
    if len(eq) == 0: return 0.0
    peak = np.maximum.accumulate(eq)
    peak = np.where(peak == 0, 1.0, peak)
    dd = (eq - peak) / peak
    return float(abs(dd.min()) * 100)

def _ema(series, span):
    try: return float(series.ewm(span=span, adjust=False).mean().iloc[-1])
    except: return float(series.iloc[-1])

def _trend_1d(df_slice):
    cp = float(df_slice["close"].iloc[-1])
    ema = _ema(df_slice["close"], EMA_TREND_PERIOD)
    if cp > ema: return "BULLISH"
    elif cp < ema: return "BEARISH"
    return "NEUTRAL"


# ═══════════════════════════════════════════════════════════════
#  SINGLE-SYMBOL BACKTEST WITH DETAILED TRADE LOG
# ═══════════════════════════════════════════════════════════════

def backtest_detailed(symbol, df_full, max_leverage_limit=5):
    """Walk-forward backtest returning detailed trade list."""
    trades = []
    equity_curve = [CAPITAL]

    in_trade = False
    t_dir = t_entry = t_sl = t_sl_original = t_tp1 = t_tp2 = t_tp3 = 0.0
    t_atr = t_score = t_entry_bar = 0
    t_month = t_entry_date = ""
    t_tp1_hit = t_tp2_hit = t_trail_active = False
    t_trail_sl = t_locked_pnl = 0.0
    t_remaining_qty = 1.0
    t_leverage = 1
    t_liq_dist = 1.0

    total = len(df_full)
    for i in range(WARMUP, total - 1):
        if i % 2000 == 0:
            sys.stdout.write(".")
            sys.stdout.flush()

        df_slice = df_full.iloc[max(0, i - 300):i]
        hi = float(df_full["high"].iloc[i])
        lo = float(df_full["low"].iloc[i])
        cl = float(df_full["close"].iloc[i])
        bar_ts = df_full.index[i]
        month = str(bar_ts)[:7]

        # ── EXIT ──
        if in_trade:
            exited = False
            pnl_r = 0.0
            exit_result = ""
            exit_price = 0.0
            sl_dist = abs(t_entry - t_sl_original) / t_entry

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
                        if t_tp1_hit: pnl_r = t_locked_pnl; exit_result = "WIN_BE"
                        else: pnl_r = -1.0; exit_result = "LOSS"
                        exit_price = t_sl; exited = True
                    elif hi >= t_tp3:
                        pnl_r = t_locked_pnl + TP3_CLOSE * TP3_R
                        exit_result = "WIN_TP3"; exit_price = t_tp3; exited = True
                    elif not t_tp2_hit and hi >= t_tp2:
                        t_locked_pnl += TP2_CLOSE * TP2_R; t_tp2_hit = True
                        t_remaining_qty -= TP2_CLOSE
                        t_trail_sl = max(t_trail_sl, t_entry + t_atr * 0.5)
                    elif not t_tp1_hit and hi >= t_tp1:
                        t_locked_pnl += TP1_CLOSE * TP1_R; t_tp1_hit = True
                        t_remaining_qty -= TP1_CLOSE
                        t_sl = t_entry * 1.001; t_trail_active = True
                        t_trail_sl = t_entry - t_atr * TRAIL_ATR
                else:  # SHORT
                    if hi >= t_sl:
                        if t_tp1_hit: pnl_r = t_locked_pnl; exit_result = "WIN_BE"
                        else: pnl_r = -1.0; exit_result = "LOSS"
                        exit_price = t_sl; exited = True
                    elif lo <= t_tp3:
                        pnl_r = t_locked_pnl + TP3_CLOSE * TP3_R
                        exit_result = "WIN_TP3"; exit_price = t_tp3; exited = True
                    elif not t_tp2_hit and lo <= t_tp2:
                        t_locked_pnl += TP2_CLOSE * TP2_R; t_tp2_hit = True
                        t_remaining_qty -= TP2_CLOSE
                        t_trail_sl = min(t_trail_sl, t_entry - t_atr * 0.5)
                    elif not t_tp1_hit and lo <= t_tp1:
                        t_locked_pnl += TP1_CLOSE * TP1_R; t_tp1_hit = True
                        t_remaining_qty -= TP1_CLOSE
                        t_sl = t_entry * 0.999; t_trail_active = True
                        t_trail_sl = t_entry + t_atr * TRAIL_ATR

            if exited:
                net_r = pnl_r - ROUND_TRIP / sl_dist if sl_dist > 0 else pnl_r
                dollar_pnl = equity_curve[-1] * 0.02 * net_r
                new_eq = equity_curve[-1] + dollar_pnl
                equity_curve.append(new_eq)

                trades.append({
                    "symbol": symbol,
                    "direction": t_dir,
                    "entry_date": t_entry_date,
                    "exit_date": str(bar_ts)[:16],
                    "entry": round(t_entry, 4),
                    "sl": round(t_sl_original, 4),
                    "exit_price": round(exit_price, 4),
                    "tp1": round(t_tp1, 4),
                    "tp2": round(t_tp2, 4),
                    "tp3": round(t_tp3, 4),
                    "result": exit_result,
                    "r_mult": round(net_r, 3),
                    "dollar_pnl": round(dollar_pnl, 2),
                    "equity_before": round(equity_curve[-2], 2),
                    "equity_after": round(new_eq, 2),
                    "score": round(t_score, 2),
                    "month": t_month,
                    "sl_pct": round(sl_dist * 100, 2),
                    "atr": round(t_atr, 4),
                    "tp1_hit": t_tp1_hit,
                    "tp2_hit": t_tp2_hit,
                    "leverage": t_leverage,
                    "liq_dist_pct": round(t_liq_dist * 100, 1),
                    "bars_held": i - t_entry_bar,
                })

                in_trade = t_tp1_hit = t_tp2_hit = t_trail_active = False
                t_locked_pnl = 0.0; t_remaining_qty = 1.0
            continue

        # ── ENTRY ──
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

        if comp >= 8.0: max_lev_by_score = 5
        elif comp >= 6.5: max_lev_by_score = 4
        elif comp >= 5.5: max_lev_by_score = 3
        else: max_lev_by_score = 2

        max_lev = min(max_lev_by_score, max_leverage_limit)
        req_lev = math.ceil(0.02 / sl_dist)
        lev = max(1, min(req_lev, max_lev))
        liq_dist = 1.0 / lev

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

        t_entry = entry_; t_sl = sl_; t_sl_original = sl_
        t_tp1 = tp1_; t_tp2 = tp2_; t_tp3 = tp3_
        t_atr = atr_; t_dir = d_; t_score = comp
        t_entry_bar = i; t_month = month
        t_entry_date = str(bar_ts)[:16]
        t_tp1_hit = t_tp2_hit = t_trail_active = False
        t_trail_sl = 0.0; t_locked_pnl = 0.0; t_remaining_qty = 1.0
        t_leverage = lev; t_liq_dist = liq_dist
        in_trade = True

    return {"trades": trades, "equity_curve": equity_curve}


# ═══════════════════════════════════════════════════════════════
#  ORP ENGINE (returns detailed trade-by-trade)
# ═══════════════════════════════════════════════════════════════

def run_orp_detailed(trades, start_capital=100.0, target_step_pct=0.05, max_lev_cap=5.0):
    """ORP with detailed per-trade output."""
    equity = start_capital
    target_step = 0
    target_equity = start_capital
    equity_curve = [start_capital]
    orp_trades = []
    max_lev_used = 1.0

    for t in trades:
        while equity >= target_equity:
            target_step += 1
            target_equity = start_capital * ((1.0 + target_step_pct) ** target_step)

        delta = target_equity - equity
        base_risk = equity * 0.025
        required_risk = max(base_risk, delta / 1.5)

        sl_fraction = t["sl_pct"] / 100.0
        if sl_fraction <= 0: sl_fraction = 0.015

        pos_size = required_risk / sl_fraction
        req_lev = pos_size / equity

        actual_lev = min(req_lev, max_lev_cap)
        max_lev_used = max(max_lev_used, actual_lev)

        actual_pos = actual_lev * equity
        actual_risk = actual_pos * sl_fraction

        if actual_risk > equity * 0.15:
            actual_risk = equity * 0.15
            actual_pos = actual_risk / sl_fraction
            actual_lev = actual_pos / equity

        dollar_pnl = actual_risk * t["r_mult"]
        old_eq = equity
        equity += dollar_pnl
        if equity <= 1.0: equity = 0.0

        equity_curve.append(equity)

        orp_trades.append({
            **t,
            "orp_equity_before": round(old_eq, 2),
            "orp_equity_after": round(equity, 2),
            "orp_dollar_pnl": round(dollar_pnl, 2),
            "orp_risk_usdt": round(actual_risk, 2),
            "orp_pos_size_usdt": round(actual_pos, 2),
            "orp_leverage": round(actual_lev, 2),
            "orp_target_step": target_step,
            "orp_target_eq": round(target_equity, 2),
        })

    steps = 0
    if equity > start_capital:
        steps = int(math.log(equity / start_capital) / math.log(1.0 + target_step_pct))

    return {
        "trades": orp_trades,
        "equity_curve": equity_curve,
        "final_eq": equity,
        "max_dd": calculate_max_dd(equity_curve),
        "max_lev_used": max_lev_used,
        "steps": steps,
    }


# ═══════════════════════════════════════════════════════════════
#  MAIN RUNNER
# ═══════════════════════════════════════════════════════════════

def main():
    head("GERÇEKÇİ BİNANCE BOT SİMÜLASYONU — 12 AY — 4H — ORP %5")
    print(f"  Başlangıç: {ok('$100.00')}  |  Strateji: S3-ORP-5%  |  Max Kaldıraç: 5x")
    print(f"  Coinler: ETH, BTC, SOL, XRP  |  Timeframe: 4H")
    print(f"  Dönem: Haziran 2025 → Mayıs 2026 (12 ay)\n")

    all_raw_trades = []
    sym_stats = {}

    # 1) Run backtests per symbol
    h2("SEMBOL BAZINDA BACKTEST")
    for sym in SYMBOLS:
        csv = f"data/historical/{sym.replace('/', '_')}_4h.csv"
        if not os.path.exists(csv):
            print(f"  {bad('HATA')}: {csv} bulunamadı"); continue

        df = pd.read_csv(csv)
        df["ts"] = pd.to_datetime(df["ts"])
        df.set_index("ts", inplace=True)
        df = df.sort_index()

        d0, d1 = str(df.index[WARMUP])[:10], str(df.index[-1])[:10]
        sys.stdout.write(f"  {sym:10} ({d0} → {d1})  {len(df)} bar ")
        sys.stdout.flush()

        t0 = time.time()
        result = backtest_detailed(sym, df, max_leverage_limit=5)
        elapsed = time.time() - t0

        trades = result["trades"]
        n = len(trades)
        wins = sum(1 for t in trades if t["r_mult"] > 0)
        losses = sum(1 for t in trades if t["r_mult"] <= 0)
        longs = sum(1 for t in trades if t["direction"] == "LONG")
        shorts = sum(1 for t in trades if t["direction"] == "SHORT")
        wr = wins / n * 100 if n > 0 else 0

        print(f" → {ok(f'{n} işlem')} ({elapsed:.1f}sn)  WR: {wr:.0f}%  L:{longs} S:{shorts}")

        sym_stats[sym] = {
            "n": n, "wins": wins, "losses": losses,
            "longs": longs, "shorts": shorts, "wr": wr,
        }
        all_raw_trades.extend(trades)

    if not all_raw_trades:
        print(bad("\nHİÇ İŞLEM ÜRETİLEMEDİ!")); return

    # 2) Sort all trades by date (chronological portfolio)
    all_raw_trades.sort(key=lambda x: x["entry_date"])

    # 3) Run ORP on combined portfolio
    h2("BİRLEŞİK PORTFÖY — ORP %5 SİMÜLASYONU")
    orp = run_orp_detailed(all_raw_trades, start_capital=100.0, target_step_pct=0.05, max_lev_cap=5.0)

    n_trades_str = str(len(orp['trades']))
    final_eq_str = f"${orp['final_eq']:,.2f}"
    steps_str = str(orp['steps'])
    dd_str = f"{orp['max_dd']:.1f}%"
    lev_str = f"{orp['max_lev_used']:.2f}x"
    print(f"\n  Toplam İşlem: {ok(n_trades_str)}")
    print(f"  Bitiş Değeri: {ok(final_eq_str)}")
    print(f"  %5 Adım: {ok(steps_str)}")
    print(f"  Max DD: {warn(dd_str)}")
    print(f"  Max Kaldıraç: {nfo(lev_str)}")

    # 4) Detailed trade log
    h2("DETAYLI İŞLEM LOGU (İLK 30 İŞLEM)")
    print(f"  {'#':>3} {'Tarih':16} {'Sembol':10} {'Yön':5} {'Giriş':>10} {'Çıkış':>10} {'SL':>10} "
          f"{'Sonuç':10} {'R':>6} {'PnL($)':>8} {'Kasa':>10} {'Lev':>4} {'SL%':>5}")
    print(f"  {'─'*120}")
    for idx, t in enumerate(orp["trades"][:30], 1):
        d = t["direction"][:1]
        dc = ok("L") if d == "L" else bad("S")
        r_c = ok(f"+{t['r_mult']:.2f}") if t["r_mult"] > 0 else bad(f"{t['r_mult']:.2f}")
        pnl_c = ok(f"+${t['orp_dollar_pnl']:.2f}") if t["orp_dollar_pnl"] > 0 else bad(f"${t['orp_dollar_pnl']:.2f}")
        res = t["result"]
        res_c = ok(res) if "WIN" in res else bad(res)
        print(f"  {idx:>3} {t['entry_date']:16} {t['symbol']:10} {dc}    "
              f"${t['entry']:>9,.2f} ${t['exit_price']:>9,.2f} ${t['sl']:>9,.2f} "
              f"{res_c:10} {r_c:>6} {pnl_c:>8} ${t['orp_equity_after']:>9,.2f} "
              f"{t['orp_leverage']:>4.1f}x {t['sl_pct']:>4.1f}%")

    if len(orp["trades"]) > 30:
        print(f"\n  ... ve {len(orp['trades'])-30} işlem daha (toplam {len(orp['trades'])})")

    # 5) Monthly breakdown
    h2("AYLIK PERFORMANS DAĞILIMI")
    monthly = defaultdict(lambda: {"count": 0, "wins": 0, "pnl": 0.0, "longs": 0, "shorts": 0})
    for t in orp["trades"]:
        m = t["month"]
        monthly[m]["count"] += 1
        monthly[m]["pnl"] += t["orp_dollar_pnl"]
        if t["r_mult"] > 0: monthly[m]["wins"] += 1
        if t["direction"] == "LONG": monthly[m]["longs"] += 1
        else: monthly[m]["shorts"] += 1

    print(f"  {'Ay':8} {'İşlem':>6} {'Long':>5} {'Short':>6} {'Kazanma':>8} {'WR':>6} {'PnL($)':>12}")
    print(f"  {'─'*60}")
    for m in sorted(monthly.keys()):
        d = monthly[m]
        wr = d["wins"]/d["count"]*100 if d["count"]>0 else 0
        pnl_c = ok(f"+${d['pnl']:,.2f}") if d["pnl"]>0 else bad(f"${d['pnl']:,.2f}")
        print(f"  {m:8} {d['count']:>6} {d['longs']:>5} {d['shorts']:>6} {d['wins']:>5}/{d['count']:<3} {wr:>5.0f}% {pnl_c:>12}")

    # 6) Symbol breakdown
    h2("SEMBOL BAZINDA ÖZET")
    sym_orp = defaultdict(lambda: {"n": 0, "wins": 0, "pnl": 0.0, "longs": 0, "shorts": 0, "r_sum": 0.0})
    for t in orp["trades"]:
        s = t["symbol"]
        sym_orp[s]["n"] += 1
        sym_orp[s]["pnl"] += t["orp_dollar_pnl"]
        sym_orp[s]["r_sum"] += t["r_mult"]
        if t["r_mult"] > 0: sym_orp[s]["wins"] += 1
        if t["direction"] == "LONG": sym_orp[s]["longs"] += 1
        else: sym_orp[s]["shorts"] += 1

    print(f"  {'Sembol':12} {'İşlem':>6} {'Long':>5} {'Short':>6} {'WR':>6} {'Ort R':>7} {'PnL($)':>12}")
    print(f"  {'─'*60}")
    for s in sorted(sym_orp.keys()):
        d = sym_orp[s]
        wr = d["wins"]/d["n"]*100 if d["n"]>0 else 0
        avg_r = d["r_sum"]/d["n"] if d["n"]>0 else 0
        pnl_c = ok(f"+${d['pnl']:,.2f}") if d["pnl"]>0 else bad(f"${d['pnl']:,.2f}")
        print(f"  {s:12} {d['n']:>6} {d['longs']:>5} {d['shorts']:>6} {wr:>5.0f}% {avg_r:>+6.2f}R {pnl_c:>12}")

    # 7) Exit type distribution
    h2("ÇIKIŞ TİPİ DAĞILIMI")
    exit_types = defaultdict(int)
    for t in orp["trades"]:
        exit_types[t["result"]] += 1
    for et, count in sorted(exit_types.items(), key=lambda x: -x[1]):
        pct = count / len(orp["trades"]) * 100
        bar = "█" * int(pct / 2)
        label = ok(et) if "WIN" in et else bad(et)
        print(f"  {label:20} {count:>4} ({pct:>5.1f}%)  {bar}")

    # 8) Overall summary
    total_trades = len(orp["trades"])
    total_wins = sum(1 for t in orp["trades"] if t["r_mult"] > 0)
    total_losses = total_trades - total_wins
    total_longs = sum(1 for t in orp["trades"] if t["direction"] == "LONG")
    total_shorts = total_trades - total_longs
    avg_r = np.mean([t["r_mult"] for t in orp["trades"]])
    avg_win_r = np.mean([t["r_mult"] for t in orp["trades"] if t["r_mult"] > 0]) if total_wins > 0 else 0
    avg_loss_r = np.mean([t["r_mult"] for t in orp["trades"] if t["r_mult"] <= 0]) if total_losses > 0 else 0
    profit_factor = abs(sum(t["orp_dollar_pnl"] for t in orp["trades"] if t["orp_dollar_pnl"]>0) /
                       (sum(t["orp_dollar_pnl"] for t in orp["trades"] if t["orp_dollar_pnl"]<0) or -1))
    avg_bars = np.mean([t["bars_held"] for t in orp["trades"]])

    h2("═══ NİHAİ SONUÇLAR ═══")
    print(f"""
  ┌─────────────────────────────────────────────────┐
  │  BAŞLANGIÇ SERMAYESİ  :  $100.00                │
  │  BİTİŞ SERMAYESİ     :  ${orp['final_eq']:>10,.2f}             │
  │  NET GETİRİ           :  +{(orp['final_eq']/100-1)*100:,.1f}%                 │
  │  BİLEŞİK ÇARPAN       :  {orp['final_eq']/100:,.1f}x                  │
  │                                                 │
  │  TOPLAM İŞLEM         :  {total_trades:>4}                      │
  │  ├── LONG              :  {total_longs:>4}                      │
  │  └── SHORT             :  {total_shorts:>4}                      │
  │                                                 │
  │  KAZANMA / KAYIP      :  {total_wins:>3} / {total_losses:<3}                 │
  │  WIN RATE             :  {total_wins/total_trades*100:>5.1f}%                  │
  │  PROFIT FACTOR        :  {profit_factor:>5.2f}                   │
  │                                                 │
  │  ORT. R-ÇARPANI       :  {avg_r:>+5.2f}R                  │
  │  ORT. KAZANÇ          :  {avg_win_r:>+5.2f}R                  │
  │  ORT. KAYIP           :  {avg_loss_r:>+5.2f}R                  │
  │                                                 │
  │  %5 ADIM TAMAMLANAN   :  {orp['steps']:>4}                      │
  │  MAX DRAWDOWN         :  {orp['max_dd']:>5.1f}%                  │
  │  MAX KALDIRAC KULLANM :  {orp['max_lev_used']:>5.2f}x                 │
  │  LİKİDASYON           :  0                      │
  │                                                 │
  │  ORT. İŞLEM SÜRESİ   :  {avg_bars:>5.1f} bar (~{avg_bars*4:.0f} saat)       │
  └─────────────────────────────────────────────────┘
""")

    # 9) Print markdown tables for report
    h2("MARKDOWN RAPOR ÇIKTISI")
    print("\n### Aylık Performans Tablosu\n")
    print("| Ay | İşlem | Long | Short | Kazanma | WR | PnL ($) |")
    print("|-----|-------|------|-------|---------|-----|---------|")
    for m in sorted(monthly.keys()):
        d = monthly[m]
        wr = d["wins"]/d["count"]*100 if d["count"]>0 else 0
        pnl_s = f"+${d['pnl']:,.2f}" if d["pnl"]>0 else f"${d['pnl']:,.2f}"
        print(f"| {m} | {d['count']} | {d['longs']} | {d['shorts']} | {d['wins']}/{d['count']} | {wr:.0f}% | **{pnl_s}** |")

    print("\n### Sembol Bazında Performans\n")
    print("| Sembol | İşlem | Long | Short | WR | Ort R | PnL ($) |")
    print("|--------|-------|------|-------|-----|-------|---------|")
    for s in sorted(sym_orp.keys()):
        d = sym_orp[s]
        wr = d["wins"]/d["n"]*100 if d["n"]>0 else 0
        avg_r_ = d["r_sum"]/d["n"] if d["n"]>0 else 0
        pnl_s = f"+${d['pnl']:,.2f}" if d["pnl"]>0 else f"${d['pnl']:,.2f}"
        print(f"| **{s}** | {d['n']} | {d['longs']} | {d['shorts']} | {wr:.0f}% | {avg_r_:+.2f}R | **{pnl_s}** |")

    print("\n### Çıkış Tipi Dağılımı\n")
    print("| Çıkış Tipi | Sayı | Oran |")
    print("|-----------|------|------|")
    for et, count in sorted(exit_types.items(), key=lambda x: -x[1]):
        pct = count / len(orp["trades"]) * 100
        print(f"| {et} | {count} | {pct:.1f}% |")


if __name__ == "__main__":
    main()
