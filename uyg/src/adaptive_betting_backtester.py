#!/usr/bin/env python3
"""
adaptive_betting_backtester.py — MULTI-COIN REGIME-ADAPTIVE HYBRID SIMULATOR
════════════════════════════════════════════════════════════════════════════
Simulates and compares standard risk models against our newly developed
Regime-Adaptive Hybrid Progression Engine across BTC, ETH, SOL, BNB, XRP on 4H.
"""
import os, sys, math, time, warnings
import numpy as np
import pandas as pd
from collections import defaultdict

warnings.filterwarnings("ignore")

# Import indicators and scoring
from backtest_multi_tf import (
    score_slice_v2, WARMUP, EMA_TREND_PERIOD,
    SL_ATR_MULT, TP1_R, TP2_R, TP3_R, TRAIL_ATR,
    TP1_CLOSE, TP2_CLOSE, TP3_CLOSE
)
from live_scan import order_blocks, fair_value_gaps, B, R, GR, RD, YL, CY, DM, ok, bad, warn, nfo, dim, head, h2

# Costs
COMMISSION_HC = 0.0004   # 0.04%
SLIPPAGE_HC   = 0.0010   # 0.10%
LIMIT_SLIPPAGE = 0.0002  # 0.02%

CAPITAL = 100.0
TIMEOUT_BARS = 12
MAX_OPEN_TRADES = 4

def _trend_1d(df_slice):
    cp = float(df_slice["close"].iloc[-1])
    try:
        ema = float(df_slice["close"].ewm(span=EMA_TREND_PERIOD, adjust=False).mean().iloc[-1])
    except:
        ema = float(df_slice["close"].iloc[-1])
    if cp > ema: return "BULLISH"
    elif cp < ema: return "BEARISH"
    return "NEUTRAL"

def get_entry_levels(df_slice, trend, atr_val):
    cp = float(df_slice["close"].iloc[-1])
    try:
        bull_obs, bear_obs, _, _ = order_blocks(df_slice)
        bull_fvg, bear_fvg = fair_value_gaps(df_slice)
    except Exception:
        bull_obs, bear_obs, bull_fvg, bear_fvg = [], [], [], []
    
    ob_high = ob_mid = ob_low = None
    if trend == "BULLISH":
        if bull_obs:
            ob = bull_obs[0]
            ob_high = float(ob["high"])
            ob_mid = float(ob["mid"])
            ob_low = float(ob["low"])
        elif bull_fvg:
            fvg = bull_fvg[0]
            ob_high = float(fvg["high"])
            ob_mid = float(fvg["mid"])
            ob_low = float(fvg["low"])
        else:
            ob_high = cp
            ob_mid = cp
            ob_low = cp - atr_val * 1.5
    elif trend == "BEARISH":
        if bear_obs:
            ob = bear_obs[0]
            ob_high = float(ob["low"])
            ob_mid = float(ob["mid"])
            ob_low = float(ob["high"])
        elif bear_fvg:
            fvg = bear_fvg[0]
            ob_high = float(fvg["low"])
            ob_mid = float(fvg["mid"])
            ob_low = float(fvg["high"])
        else:
            ob_high = cp
            ob_mid = cp
            ob_low = cp + atr_val * 1.5
            
    if ob_high is None or ob_mid is None or ob_low is None:
        ob_high, ob_mid, ob_low = cp, cp, cp - atr_val * 1.5 if trend == "BULLISH" else cp + atr_val * 1.5
    return ob_high, ob_mid, ob_low

def precalculate_signals_for_portfolio(coins):
    btc_csv = "data/historical/BTC_USDT_4h.csv"
    if not os.path.exists(btc_csv):
        print("BTC/USDT historical data not found!")
        btc_trends = {}
    else:
        btc_df = pd.read_csv(btc_csv)
        btc_df["ts"] = pd.to_datetime(btc_df["ts"])
        btc_df.set_index("ts", inplace=True)
        btc_df = btc_df.sort_index()
        btc_trends = {}
        for i in range(max(WARMUP, len(btc_df) - 1100), len(btc_df) - 1):
            slice_df = btc_df.iloc[max(0, i-300):i]
            btc_trends[btc_df.index[i]] = _trend_1d(slice_df)
            
    signals_by_coin = {}
    for sym in coins:
        csv_path = f"data/historical/{sym.replace('/', '_')}_4h.csv"
        if not os.path.exists(csv_path):
            print(f"Data file not found for {sym}")
            continue
        df = pd.read_csv(csv_path)
        df["ts"] = pd.to_datetime(df["ts"])
        df.set_index("ts", inplace=True)
        df = df.sort_index()
        
        signals = {}
        for i in range(max(WARMUP, len(df) - 1100), len(df) - 1):
            ts = df.index[i]
            btc_macro_trend = btc_trends.get(ts, "NEUTRAL")
            if btc_macro_trend == "NEUTRAL":
                continue
            df_slice = df.iloc[max(0, i-300):i]
            comp, trend, entry_, sl_, atr_, vol_ok_ = score_slice_v2(df_slice)
            if comp < 4.5 or trend == "NEUTRAL" or entry_ is None:
                continue
            trend_1d = _trend_1d(df_slice)
            if trend_1d != "NEUTRAL" and trend_1d != trend:
                continue
            if trend != btc_macro_trend:
                continue
            if not vol_ok_:
                continue
            sl_dist = abs(entry_ - sl_) / entry_
            if not (0.005 < sl_dist <= 0.10):
                continue
            ob_high, ob_mid, ob_low = get_entry_levels(df_slice, trend, atr_)
            signals[ts] = {
                "comp": comp,
                "trend": trend,
                "entry_": entry_,
                "sl_": sl_,
                "atr_": atr_,
                "ob_high": ob_high,
                "ob_mid": ob_mid,
                "ob_low": ob_low
            }
        signals_by_coin[sym] = {"df": df, "signals": signals}
    return signals_by_coin

def run_portfolio_backtest(signals_by_coin, money_mgmt="fixed_risk", step_pct=0.05, base_risk=0.02):
    all_timestamps = set()
    for sym, data in signals_by_coin.items():
        all_timestamps.update(data["df"].index)
    sorted_timestamps = sorted(list(all_timestamps))
    
    equity = CAPITAL
    equity_curve = []
    trades_log = []
    
    active_trades = {}
    pending_orders = {}
    
    last_long_loss_ts = pd.Timestamp("2000-01-01")
    last_short_loss_ts = pd.Timestamp("2000-01-01")
    
    # Streaks / Rolling win history for Adaptive Hybrid
    # We maintain a list of past trade results (True for win, False for loss)
    trade_results = []
    consec_wins = 0
    fib_seq = [1, 1, 2, 3, 5, 8]
    
    # ORP variables
    orp_step = 0
    orp_target = CAPITAL
    
    for ts in sorted_timestamps:
        month = str(ts)[:7]
        open_positions = len(active_trades)
        
        # ─── 1. EXIT CHECKER ───
        for coin, t in list(active_trades.items()):
            df_coin = signals_by_coin[coin]["df"]
            if ts not in df_coin.index:
                continue
            hi = float(df_coin.loc[ts, "high"])
            lo = float(df_coin.loc[ts, "low"])
            cl = float(df_coin.loc[ts, "close"])
            
            exited = False
            pnl_r = 0.0
            exit_result = ""
            exit_price = 0.0
            sl_dist = abs(t["entry"] - t["sl_orig"]) / t["entry"]
            
            # Trailing SL
            if t["trail_active"]:
                if t["direction"] == "LONG":
                    new_trail = cl - t["atr"] * TRAIL_ATR
                    if new_trail > t["trail_sl"]: t["trail_sl"] = new_trail
                    if lo <= t["trail_sl"]:
                        pnl_r = t["locked_pnl"] + (t["trail_sl"] - t["entry"]) / t["entry"] / sl_dist
                        exit_result = "WIN_TRAIL"; exit_price = t["trail_sl"]; exited = True
                else:
                    new_trail = cl + t["atr"] * TRAIL_ATR
                    if new_trail < t["trail_sl"]: t["trail_sl"] = new_trail
                    if hi >= t["trail_sl"]:
                        pnl_r = t["locked_pnl"] + (t["entry"] - t["trail_sl"]) / t["entry"] / sl_dist
                        exit_result = "WIN_TRAIL"; exit_price = t["trail_sl"]; exited = True
                        
            # SL or TP Checks
            if not exited:
                if t["direction"] == "LONG":
                    if lo <= t["sl"]:
                        pnl_r = t["locked_pnl"] if t["tp1_hit"] else -1.0
                        exit_result = "WIN_BE" if t["tp1_hit"] else "LOSS"
                        exit_price = t["sl"]; exited = True
                    elif hi >= t["tp3"]:
                        pnl_r = t["locked_pnl"] + TP3_CLOSE * TP3_R
                        exit_result = "WIN_TP3"; exit_price = t["tp3"]; exited = True
                    elif not t["tp2_hit"] and hi >= t["tp2"]:
                        t["locked_pnl"] += TP2_CLOSE * TP2_R; t["tp2_hit"] = True
                        t["remaining"] -= TP2_CLOSE
                        t["trail_sl"] = max(t["trail_sl"], t["entry"] + t["atr"] * 0.5)
                    elif not t["tp1_hit"] and hi >= t["tp1"]:
                        t["locked_pnl"] += TP1_CLOSE * TP1_R; t["tp1_hit"] = True
                        t["remaining"] -= TP1_CLOSE
                        t["sl"] = t["entry"] * 1.001
                        t["trail_active"] = True
                        t["trail_sl"] = t["entry"] - t["atr"] * TRAIL_ATR
                else:
                    if hi >= t["sl"]:
                        pnl_r = t["locked_pnl"] if t["tp1_hit"] else -1.0
                        exit_result = "WIN_BE" if t["tp1_hit"] else "LOSS"
                        exit_price = t["sl"]; exited = True
                    elif lo <= t["tp3"]:
                        pnl_r = t["locked_pnl"] + TP3_CLOSE * TP3_R
                        exit_result = "WIN_TP3"; exit_price = t["tp3"]; exited = True
                    elif not t["tp2_hit"] and lo <= t["tp2"]:
                        t["locked_pnl"] += TP2_CLOSE * TP2_R; t["tp2_hit"] = True
                        t["remaining"] -= TP2_CLOSE
                        t["trail_sl"] = min(t["trail_sl"], t["entry"] - t["atr"] * 0.5)
                    elif not t["tp1_hit"] and lo <= t["tp1"]:
                        t["locked_pnl"] += TP1_CLOSE * TP1_R; t["tp1_hit"] = True
                        t["remaining"] -= TP1_CLOSE
                        t["sl"] = t["entry"] * 0.999
                        t["trail_active"] = True
                        t["trail_sl"] = t["entry"] + t["atr"] * TRAIL_ATR
                        
            if exited:
                cost = (COMMISSION_HC * 2) + LIMIT_SLIPPAGE + SLIPPAGE_HC
                net_r = pnl_r - cost / sl_dist if sl_dist > 0 else pnl_r
                
                dollar_pnl = t["risk_capital"] * net_r * t["size_mult"]
                equity += dollar_pnl
                if equity < 1.0: equity = 0.0
                
                trades_log.append({
                    "coin": coin,
                    "direction": t["direction"],
                    "entry_date": t["entry_date"],
                    "exit_date": str(ts)[:16],
                    "entry": t["entry"],
                    "exit": exit_price,
                    "result": exit_result,
                    "r_mult": net_r,
                    "dollar_pnl": dollar_pnl,
                    "equity": equity,
                    "month": month,
                    "size_mult": t["size_mult"]
                })
                
                # Update rolling win-rate tracker and streaks
                is_win = (net_r > 0)
                trade_results.append(is_win)
                
                if is_win:
                    consec_wins += 1
                else:
                    consec_wins = 0
                    if t["direction"] == "LONG":
                        last_long_loss_ts = ts
                    else:
                        last_short_loss_ts = ts
                    
                del active_trades[coin]
                open_positions -= 1
                
        # ─── 2. PENDING ORDER CHECKER ───
        for coin, p in list(pending_orders.items()):
            df_coin = signals_by_coin[coin]["df"]
            if ts not in df_coin.index:
                continue
            hi = float(df_coin.loc[ts, "high"])
            lo = float(df_coin.loc[ts, "low"])
            
            p["bars_waited"] += 1
            if p["bars_waited"] > TIMEOUT_BARS:
                del pending_orders[coin]
                continue
                
            if p["direction"] == "LONG" and hi >= p["tp1_if_filled"]:
                del pending_orders[coin]
                continue
            elif p["direction"] == "SHORT" and lo <= p["tp1_if_filled"]:
                del pending_orders[coin]
                continue
                
            high_hit = (p["direction"] == "LONG" and lo <= p["limit_high"]) or (p["direction"] == "SHORT" and hi >= p["limit_high"])
            mid_hit = (p["direction"] == "LONG" and lo <= p["limit_mid"]) or (p["direction"] == "SHORT" and hi >= p["limit_mid"])
            
            filled = False
            entry_price = 0.0
            size_mult = 1.0
            
            if mid_hit:
                filled = True
                entry_price = (p["limit_high"] + p["limit_mid"]) / 2
                size_mult = 1.0
            elif high_hit:
                is_timeout = p["bars_waited"] == TIMEOUT_BARS
                is_tp1_reached = (p["direction"] == "LONG" and hi >= p["tp1_if_filled"]) or (p["direction"] == "SHORT" and lo <= p["tp1_if_filled"])
                if is_timeout or is_tp1_reached:
                    filled = True
                    entry_price = p["limit_high"]
                    size_mult = 0.5
                    
            if filled:
                if open_positions >= MAX_OPEN_TRADES:
                    del pending_orders[coin]
                    continue
                    
                long_count = sum(1 for tc, tdata in active_trades.items() if tdata["direction"] == "LONG")
                short_count = sum(1 for tc, tdata in active_trades.items() if tdata["direction"] == "SHORT")
                
                if p["direction"] == "LONG":
                    hours_since_loss = (ts - last_long_loss_ts).total_seconds() / 3600.0
                    if hours_since_loss < 24.0 or long_count >= 1:
                        del pending_orders[coin]
                        continue
                elif p["direction"] == "SHORT":
                    hours_since_loss = (ts - last_short_loss_ts).total_seconds() / 3600.0
                    if hours_since_loss < 24.0 or short_count >= 1:
                        del pending_orders[coin]
                        continue
                    
                # Calculate dynamic risk size
                risk_pct = base_risk
                
                if money_mgmt == "fixed_risk":
                    risk_pct = base_risk
                elif money_mgmt == "paroli":
                    streak = min(consec_wins, 3)
                    if streak >= 3:
                        streak = 0
                        consec_wins = 0
                    risk_pct = min(base_risk * (2 ** streak), 0.15)
                elif money_mgmt == "fibonacci":
                    level = fib_seq[min(consec_wins, len(fib_seq)-1)]
                    risk_pct = min(base_risk * level, 0.15)
                elif money_mgmt == "orp":
                    while equity >= orp_target:
                        orp_step += 1
                        orp_target = CAPITAL * ((1.0 + step_pct) ** orp_step)
                    delta = orp_target - equity
                    base_orp = equity * 0.025
                    risk_pct = max(base_orp, delta / 1.5) / equity
                    if risk_pct > 0.15: risk_pct = 0.15
                elif money_mgmt == "adaptive_hybrid":
                    # --- Regime-Adaptive Hybrid Progression Engine ---
                    # 1. Calculate Rolling Win Rate of last 10 trades (default to 55% if < 4 trades)
                    last_10 = trade_results[-10:] if len(trade_results) >= 4 else [True, True, False, True]
                    rolling_wr = sum(last_10) / len(last_10) if len(last_10) > 0 else 0.55
                    
                    # 2. Determine Regime
                    if rolling_wr >= 0.70:
                        # HOT REGIME: scale risk up exponentially based on streak!
                        streak = min(consec_wins, 4)
                        risk_pct = min(base_risk * (1.8 ** streak), 0.15)
                    elif rolling_wr <= 0.40:
                        # COLD REGIME: defensive minimum risk
                        risk_pct = 0.01 
                    else:
                        # NEUTRAL REGIME: baseline ORP %5 step model
                        while equity >= orp_target:
                            orp_step += 1
                            orp_target = CAPITAL * ((1.0 + 0.05) ** orp_step)
                        delta = orp_target - equity
                        base_orp = equity * 0.025
                        risk_pct = max(base_orp, delta / 1.5) / equity
                        if risk_pct > 0.15: risk_pct = 0.15
                    
                # SL & Size Calculations
                sl_low = p["sl_low"]
                atr = p["atr"]
                if p["direction"] == "LONG":
                    sl_orig = min(sl_low, entry_price - atr * SL_ATR_MULT)
                    sl_dist = (entry_price - sl_orig) / entry_price
                else:
                    sl_orig = max(sl_low, entry_price + atr * SL_ATR_MULT)
                    sl_dist = (sl_orig - entry_price) / entry_price
                    
                if sl_dist < 0.005: sl_dist = 0.015
                risk_capital = equity * risk_pct
                
                active_trades[coin] = {
                    "direction": p["direction"],
                    "entry_date": str(ts)[:16],
                    "entry": entry_price,
                    "sl_orig": sl_orig,
                    "sl": sl_orig,
                    "tp1": entry_price + (entry_price - sl_orig) * TP1_R if p["direction"] == "LONG" else entry_price - (sl_orig - entry_price) * TP1_R,
                    "tp2": entry_price + (entry_price - sl_orig) * TP2_R if p["direction"] == "LONG" else entry_price - (sl_orig - entry_price) * TP2_R,
                    "tp3": entry_price + (entry_price - sl_orig) * TP3_R if p["direction"] == "LONG" else entry_price - (sl_orig - entry_price) * TP3_R,
                    "atr": atr,
                    "score": p["score"],
                    "size_mult": size_mult,
                    "risk_capital": risk_capital,
                    "tp1_hit": False,
                    "tp2_hit": False,
                    "trail_active": False,
                    "trail_sl": 0.0,
                    "locked_pnl": 0.0,
                    "remaining": 1.0
                }
                del pending_orders[coin]
                open_positions += 1
 
        # ─── 3. NEW SIGNAL SCANNER ───
        for coin, cdata in signals_by_coin.items():
            if coin in active_trades or coin in pending_orders:
                continue
            signals = cdata["signals"]
            if ts in signals:
                sig = signals[ts]
                limit_entry_est = sig["ob_mid"]
                if sig["trend"] == "BULLISH":
                    sl_est = min(sig["ob_low"], limit_entry_est - sig["atr_"] * SL_ATR_MULT)
                    tp1_est = limit_entry_est + (limit_entry_est - sl_est) * TP1_R
                else:
                    sl_est = max(sig["ob_low"], limit_entry_est + sig["atr_"] * SL_ATR_MULT)
                    tp1_est = limit_entry_est - (sl_est - limit_entry_est) * TP1_R
                    
                pending_orders[coin] = {
                    "direction": "LONG" if sig["trend"] == "BULLISH" else "SHORT",
                    "limit_high": sig["ob_high"],
                    "limit_mid": sig["ob_mid"],
                    "sl_low": sig["ob_low"],
                    "atr": sig["atr_"],
                    "score": sig["comp"],
                    "tp1_if_filled": tp1_est,
                    "bars_waited": 0
                }
                
        equity_curve.append(equity)
        
    return {"trades": trades_log, "equity_curve": equity_curve, "final_eq": equity}

def calculate_max_dd(eq):
    arr = np.array(eq)
    if len(arr) == 0: return 0.0
    peak = np.maximum.accumulate(arr)
    peak = np.where(peak == 0, 1.0, peak)
    dd = (arr - peak) / peak
    return float(abs(dd.min()) * 100)

def main():
    head("ADAPTIVE REGIME-ADAPTIVE HYBRID COMPARISON")
    print("Testing S3 Scale-In model on 5-coin portfolio (4H).")
    print("Evaluating baseline models vs the new Regime-Adaptive Hybrid Progression Engine.\n")
    
    coins = ["ETH/USDT"]
    
    print("1. Precalculating Signals...")
    signals_by_coin = precalculate_signals_for_portfolio(coins)
    
    print("\n2. Running Portfolio Simulations...")
    mm_modes = [
        ("Fixed Risk (%2)", "fixed_risk", 0.02, 0.02),
        ("ORP %2 (Safe Growth)", "orp", 0.02, 0.02),
        ("ORP %5 (Medium Risk)", "orp", 0.05, 0.02),
        ("Paroli (Positive Comp)", "paroli", 0.02, 0.02),
        ("Regime-Adaptive Hybrid 🚀", "adaptive_hybrid", 0.05, 0.02)
    ]
    
    print(f"┌{'─'*82}┐")
    print(f"│ {'Sermaye Yönetim Modu':32} │ {'İşlem':>5} │ {'Bitiş ($)':>12} │ {'Çarpan':>8} │ {'Max DD':>8} │")
    print(f"├{'─'*82}┤")
    
    for label, mode_key, step, base in mm_modes:
        res = run_portfolio_backtest(signals_by_coin, money_mgmt=mode_key, step_pct=step, base_risk=base)
        trades = res["trades"]
        n = len(trades)
        
        if n == 0:
            print(f"│ {label:32} │ {n:5d} │ {'$0.00':>12} │ {'0.0x':>8} │ {'0.0%':>8} │")
            continue
            
        final_eq = res["final_eq"]
        multiplier = final_eq / CAPITAL
        dd = calculate_max_dd(res["equity_curve"])
        
        # Color coding the hybrid engine
        col = CY if "Hybrid" in label else B
        print(f"│ {col}{label:<32}{R} │ {n:5d} │ {'${:>10,.2f}'.format(final_eq)} │ {multiplier:>7.2f}x │ {dd:>7.1f}% │")
        
    print(f"└{'─'*82}┘")
    print()

if __name__ == "__main__":
    main()
