#!/usr/bin/env python3
"""
portfolio_limit_backtester.py — MULTI-COIN PORTFOLIO LIMIT ORDER SIMULATOR
══════════════════════════════════════════════════════════════════════════
Simulates the S3 Scale-In (50-50 High/Mid) strategy concurrently across:
BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, XRP/USDT (4H Timeframe)

Supports:
- Unified timeline execution
- Portfolio-level capital compounding (Fixed Risk, ORP, Paroli, Fibonacci)
- Concurrent position limits (Max 4 open trades)
- Realistic execution costs (2x commission + slippage)
- Proper limit timeout (12 bars / 48 hours) and cancel-on-target
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
    TP1_CLOSE, TP2_CLOSE, TP3_CLOSE, _atr
)
from live_scan import order_blocks, fair_value_gaps, B, R, GR, RD, YL, CY, DM, ok, bad, warn, nfo, dim, head, h2

# Hardcore costs
COMMISSION_HC = 0.0004   # 0.04% Taker / Limit (Conservative)
SLIPPAGE_HC   = 0.0010   # 0.10% Slippage (For Market / Taker fills)
LIMIT_SLIPPAGE = 0.0002  # 0.02% Slippage for Limit orders (unfavorable fill variance)

CAPITAL = 100.0
TIMEOUT_BARS = 12  # 48 hours on 4H TF
MAX_OPEN_TRADES = 4 # Max concurrent open positions in the portfolio

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
    except Exception as e:
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
    """Precalculates S3 signals for all portfolio coins to run simulation instantly."""
    # 1. Load BTC/USDT first to compute macro trend filter
    btc_csv = "data/historical/BTC_USDT_4h.csv"
    if not os.path.exists(btc_csv):
        print("BTC/USDT historical data not found! Cannot apply BTC macro trend filter.")
        btc_trends = {}
    else:
        btc_df = pd.read_csv(btc_csv)
        btc_df["ts"] = pd.to_datetime(btc_df["ts"])
        btc_df.set_index("ts", inplace=True)
        btc_df = btc_df.sort_index()
        
        btc_trends = {}
        for i in range(WARMUP, len(btc_df) - 1):
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
        
        sym_short = sym.split("/")[0]
        print(f"Precalculating {sym_short} with BTC Macro Trend Filter...")
        
        signals = {}
        for i in range(WARMUP, len(df) - 1):
            if i % 100 == 0:
                sys.stdout.write(".")
                sys.stdout.flush()
                
            ts = df.index[i]
            
            # Skip if we don't have BTC trend at this time
            btc_macro_trend = btc_trends.get(ts, "NEUTRAL")
            if btc_macro_trend == "NEUTRAL":
                continue
                
            df_slice = df.iloc[max(0, i - 300):i]
            comp, trend, entry_, sl_, atr_, vol_ok_ = score_slice_v2(df_slice)
            
            if comp < 4.5 or trend == "NEUTRAL" or entry_ is None:
                continue
                
            # Filter 1: Coin's own 1D trend
            trend_1d = _trend_1d(df_slice)
            if trend_1d != "NEUTRAL" and trend_1d != trend:
                continue
                
            # Filter 2: BTC Macro Trend Filter (Correlation Protection)
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
        print(f" Done. Sinyal sayısı: {len(signals)}")
        signals_by_coin[sym] = {"df": df, "signals": signals}
        
    return signals_by_coin

def run_portfolio_backtest(signals_by_coin, money_mgmt="fixed_risk", step_pct=0.05, base_risk=0.02):
    """
    Executes a unified multi-coin portfolio backtest:
    - Moves bar by bar across the shared timeline
    - Tracks active positions and pending limit orders per coin
    - Enforces portfolio-level constraints (MAX_OPEN_TRADES)
    - Applies selected Money Management (fixed_risk, ORP, Paroli, Fibonacci) on the global equity
    """
    # 1. Align timelines across all coins
    all_timestamps = set()
    for sym, data in signals_by_coin.items():
        all_timestamps.update(data["df"].index)
    sorted_timestamps = sorted(list(all_timestamps))
    
    # Capital tracker
    equity = CAPITAL
    equity_curve = []
    
    # Portfolio trade tracker
    trades_log = []
    
    # Active & pending state per coin
    active_trades = {} # coin -> active trade dict
    pending_orders = {} # coin -> pending order dict
    
    # Cooldown trackers for macro correlation protection
    last_long_loss_ts = pd.Timestamp("2000-01-01")
    last_short_loss_ts = pd.Timestamp("2000-01-01")
    
    # Global Paroli / Fibonacci win streak tracker
    consec_wins = 0
    fib_seq = [1, 1, 2, 3, 5, 8]
    
    # ORP variables
    orp_step = 0
    orp_target = CAPITAL
    
    # Iterate bar by bar
    for ts in sorted_timestamps:
        month = str(ts)[:7]
        
        # Count currently open positions
        open_positions = len(active_trades)
        
        # ─── 1. EXIT CHECKER (For all active trades) ───
        coins_to_exit = []
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
                        t["sl"] = t["entry"] * 1.001; t_trail_active = True
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
                        t["sl"] = t["entry"] * 0.999; t_trail_active = True
                        t["trail_active"] = True
                        t["trail_sl"] = t["entry"] + t["atr"] * TRAIL_ATR
                        
            if exited:
                cost = (COMMISSION_HC * 2) + LIMIT_SLIPPAGE + SLIPPAGE_HC
                net_r = pnl_r - cost / sl_dist if sl_dist > 0 else pnl_r
                
                # Apply compounding money management math
                # Calculate trade risk size relative to entry capital
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
                
                # Update streaks for Paroli & Fibonacci and track loss timestamps
                if net_r > 0:
                    consec_wins += 1
                else:
                    consec_wins = 0
                    if t["direction"] == "LONG":
                        last_long_loss_ts = ts
                    else:
                        last_short_loss_ts = ts
                    
                # Clean up active state
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
            
            # Check timeout
            if p["bars_waited"] > TIMEOUT_BARS:
                del pending_orders[coin]
                continue
                
            # Check cancel on target TP1 reached first
            if p["direction"] == "LONG" and hi >= p["tp1_if_filled"]:
                del pending_orders[coin]
                continue
            elif p["direction"] == "SHORT" and lo <= p["tp1_if_filled"]:
                del pending_orders[coin]
                continue
                
            # Fill Check (Scale-In Strategy)
            # Two limit orders: 50% at High, 50% at Mid
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
                # Only high hit. If timeout or TP1 reached during this bar, fill 50% size.
                is_timeout = p["bars_waited"] == TIMEOUT_BARS
                is_tp1_reached = (p["direction"] == "LONG" and hi >= p["tp1_if_filled"]) or (p["direction"] == "SHORT" and lo <= p["tp1_if_filled"])
                if is_timeout or is_tp1_reached:
                    filled = True
                    entry_price = p["limit_high"]
                    size_mult = 0.5
                    
            if filled:
                # Check portfolio open trades cap
                if open_positions >= MAX_OPEN_TRADES:
                    # Cancel order because we are already at capacity
                    del pending_orders[coin]
                    continue
                    
                # Correlation Protection: Enforce Max 1 Position per Direction & Cooldowns
                long_count = sum(1 for tc, tdata in active_trades.items() if tdata["direction"] == "LONG")
                short_count = sum(1 for tc, tdata in active_trades.items() if tdata["direction"] == "SHORT")
                
                if p["direction"] == "LONG":
                    # 24-hour cooldown after a LONG loss
                    hours_since_loss = (ts - last_long_loss_ts).total_seconds() / 3600.0
                    if hours_since_loss < 24.0:
                        del pending_orders[coin]
                        continue
                    if long_count >= 1:
                        del pending_orders[coin]
                        continue
                elif p["direction"] == "SHORT":
                    # 24-hour cooldown after a SHORT loss
                    hours_since_loss = (ts - last_short_loss_ts).total_seconds() / 3600.0
                    if hours_since_loss < 24.0:
                        del pending_orders[coin]
                        continue
                    if short_count >= 1:
                        del pending_orders[coin]
                        continue
                    
                # We can fill! Deduct risk capital from current equity
                # Money Management calculator
                risk_pct = base_risk
                
                if money_mgmt == "fixed_risk":
                    risk_pct = base_risk
                elif money_mgmt == "paroli":
                    # Double risk up to 15% max, reset streak after 3 wins
                    streak = min(consec_wins, 3)
                    if streak >= 3:
                        streak = 0
                        consec_wins = 0
                    risk_pct = min(base_risk * (2 ** streak), 0.15)
                elif money_mgmt == "fibonacci":
                    level = fib_seq[min(consec_wins, len(fib_seq)-1)]
                    risk_pct = min(base_risk * level, 0.15)
                elif money_mgmt == "orp":
                    # ORP Step calculator
                    while equity >= orp_target:
                        orp_step += 1
                        orp_target = CAPITAL * ((1.0 + step_pct) ** orp_step)
                    delta = orp_target - equity
                    base_orp = equity * 0.025
                    risk_pct = max(base_orp, delta / 1.5) / equity
                    if risk_pct > 0.15: risk_pct = 0.15
                    
                # Calculate SL distance
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
                
                # Active trade dict
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
                
                # Remove from pending
                del pending_orders[coin]
                open_positions += 1

        # ─── 3. NEW SIGNAL SCANNER ───
        for coin, cdata in signals_by_coin.items():
            # Skip if coin is already active or pending
            if coin in active_trades or coin in pending_orders:
                continue
                
            signals = cdata["signals"]
            if ts in signals:
                sig = signals[ts]
                
                # Place pending order
                # Calculate TP1 estimate to track cancel-on-target
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
    head("PORTFOLIO 4H LIMIT SCALE-IN SIMULATOR")
    print("Testing S3 Scale-In model on concurrent multi-coin portfolio.")
    print("Timeframe: 4H | Period: Last 12 months")
    print(f"Max Open Positions: {MAX_OPEN_TRADES} coins | Timeout: {TIMEOUT_BARS} bars ({TIMEOUT_BARS*4}h)\n")
    
    coins = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
    
    # Precalculate
    h2("1. Sinyal Ön Hesaplama Aşaması")
    signals_by_coin = precalculate_signals_for_portfolio(coins)
    
    h2("2. Portföy Simülasyon Çalıştırmaları")
    mm_modes = [
        ("Fixed Risk (%2)", "fixed_risk", 0.02, 0.02),
        ("ORP %2 (Güvenli)", "orp", 0.02, 0.02),
        ("ORP %5 (Orta Risk)", "orp", 0.05, 0.02),
        ("Paroli (Streak x2)", "paroli", 0.02, 0.02),
        ("Fibonacci (Staking)", "fibonacci", 0.02, 0.02)
    ]
    
    print(f"┌{'─'*78}┐")
    print(f"│ {'Sermaye Yönetim Modu':28} │ {'İşlem':>5} │ {'Bitiş ($)':>12} │ {'Çarpan':>8} │ {'Max DD':>8} │")
    print(f"├{'─'*78}┤")
    
    for label, mode_key, step, base in mm_modes:
        res = run_portfolio_backtest(signals_by_coin, money_mgmt=mode_key, step_pct=step, base_risk=base)
        trades = res["trades"]
        n = len(trades)
        
        if n == 0:
            print(f"│ {label:28} │ {n:5d} │ {'$0.00':>12} │ {'0.0x':>8} │ {'0.0%':>8} │")
            continue
            
        wins = sum(1 for t in trades if t["r_mult"] > 0)
        wr = wins / n * 100
        
        final_eq = res["final_eq"]
        multiplier = final_eq / CAPITAL
        
        # Calculate Max DD
        dd = calculate_max_dd(res["equity_curve"])
        
        print(f"│ {CY}{label:<28}{R} │ {n:5d} │ {'${:>10,.2f}'.format(final_eq)} │ {multiplier:>7.2f}x │ {dd:>7.1f}% │")
        
    print(f"└{'─'*78}┘")
    print()
    
    # Run a detailed print for the winner
    print("Örnek İşlem Detayları (ORP %5 Modu):")
    detailed_res = run_portfolio_backtest(signals_by_coin, money_mgmt="orp", step_pct=0.05, base_risk=0.02)
    detailed_trades = detailed_res["trades"]
    
    # Print last 10 trades
    print(f"  Son 10 Portföy İşlemi:")
    for t in detailed_trades[-10:]:
        res_color = ok if t["r_mult"] > 0 else bad
        size_type = "Full" if t["size_mult"] == 1.0 else "Half"
        print(f"    {t['exit_date']} | {t['coin']:9} | {t['direction']:5} | {size_type:4} | {res_color(t['result']):13} | R-Mult: {t['r_mult']:+.2f} | Equity: ${t['equity']:.2f}")

if __name__ == "__main__":
    main()
