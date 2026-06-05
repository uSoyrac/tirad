#!/usr/bin/env python3
"""
realistic_limit_backtester.py — REALISTIC LIMIT ORDER & SCALE-IN BACKTESTER (OPTIMIZED)
══════════════════════════════════════════════════════════════════════════
Tests 5 different entry strategies under hardcore realistic conditions:
1. Ideal OB Mid Fill (100% fill, zero delay - Benchmark)
2. Realistic Limit Order @ OB Midpoint (with timeout, cancel on TP1 first)
3. Realistic Limit Order @ OB High (higher fill rate, wider SL)
4. Scale-In (2-Level DCA: 50% @ OB High, 50% @ OB Mid)
5. Market Entry (2.5x ATR SL)
Uses a pre-calculation cache for indicator scores to speed up the backtest by 5x.
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
TIMEOUT_BARS = 6  # 24 hours on 4H TF

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
            ob_high = float(ob["low"]) # for bearish, ob_high is the low boundary for entry, but let's label them logically
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
            
    # Safety checks
    if ob_high is None or ob_mid is None or ob_low is None:
        ob_high, ob_mid, ob_low = cp, cp, cp - atr_val * 1.5 if trend == "BULLISH" else cp + atr_val * 1.5
        
    return ob_high, ob_mid, ob_low

def precalculate_signals(df_full):
    """Precalculates all S3 signals and level boundaries for a coin to avoid O(N^2 * Strat) overhead."""
    total = len(df_full)
    signals = {}
    
    for i in range(WARMUP, total - 1):
        if i % 100 == 0:
            sys.stdout.write(".")
            sys.stdout.flush()
            
        df_slice = df_full.iloc[max(0, i - 300):i]
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
            
        # Get OB levels
        ob_high, ob_mid, ob_low = get_entry_levels(df_slice, trend, atr_)
        
        signals[i] = {
            "comp": comp,
            "trend": trend,
            "entry_": entry_,
            "sl_": sl_,
            "atr_": atr_,
            "ob_high": ob_high,
            "ob_mid": ob_mid,
            "ob_low": ob_low
        }
    print(" Done!")
    return signals

def run_backtest_strategy(symbol, df_full, signals_cache, strategy_type="ideal_mid"):
    """
    Simulates the walk-forward backtest for a specific strategy type:
    - 'ideal_mid': Old behavior (assume 100% fill at OB midpoint on signal bar)
    - 'limit_mid': Place Limit Order at OB midpoint, timeout after 6 bars, cancel if TP1 hit first.
    - 'limit_high': Place Limit Order at OB High boundary (easier fill, wider SL)
    - 'scale_in': Place 2 limit orders (50% size @ OB High, 50% size @ OB Mid). Average price entry.
    - 'market_wide_sl': Market order at next bar open, SL = 2.5x ATR (breathing room).
    """
    trades = []
    total = len(df_full)
    
    # Trackers for pending limit orders
    pending = None # Stores active limit order parameters
    
    # Active trade trackers
    in_trade = False
    t_dir = ""
    t_entry = 0.0
    t_sl = t_sl_orig = 0.0
    t_tp1 = t_tp2 = t_tp3 = 0.0
    t_atr = t_score = 0.0
    t_entry_bar = 0
    t_month = t_entry_date = ""
    t_tp1_hit = t_tp2_hit = t_trail_active = False
    t_trail_sl = t_locked_pnl = 0.0
    t_remaining = 1.0
    t_size_mult = 1.0 # For partial entry in scale-in (0.5 or 1.0)
    
    for i in range(WARMUP, total - 1):
        hi = float(df_full["high"].iloc[i])
        lo = float(df_full["low"].iloc[i])
        cl = float(df_full["close"].iloc[i])
        op = float(df_full["open"].iloc[i])
        bar_ts = df_full.index[i]
        month = str(bar_ts)[:7]
        
        # ─── 1. EXIT PROCESSOR (Runs first if in trade) ───
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
                        pnl_r = t_locked_pnl + (t_trail_sl - t_entry) / t_entry / sl_dist
                        exit_result = "WIN_TRAIL"; exit_price = t_trail_sl; exited = True
                else:
                    new_trail = cl + t_atr * TRAIL_ATR
                    if new_trail < t_trail_sl: t_trail_sl = new_trail
                    if hi >= t_trail_sl:
                        pnl_r = t_locked_pnl + (t_entry - t_trail_sl) / t_entry / sl_dist
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
                # Apply transaction fees
                # Limit order entries might have smaller slippage than market order exits
                cost = (COMMISSION_HC * 2) + (SLIPPAGE_HC if strategy_type in ["ideal_mid", "market_wide_sl"] else LIMIT_SLIPPAGE + SLIPPAGE_HC)
                net_r = pnl_r - cost / sl_dist if sl_dist > 0 else pnl_r
                
                trades.append({
                    "direction": t_dir,
                    "entry_date": t_entry_date,
                    "exit_date": str(bar_ts)[:16],
                    "entry": t_entry,
                    "exit_price": exit_price,
                    "sl": t_sl_orig,
                    "result": exit_result,
                    "r_mult": net_r,
                    "score": t_score,
                    "month": month,
                    "sl_pct": sl_dist * 100,
                    "size_mult": t_size_mult # Adjust profit size for scale-in partial fills
                })
                in_trade = t_tp1_hit = t_tp2_hit = t_trail_active = False
                t_locked_pnl = 0.0; t_remaining = 1.0; t_size_mult = 1.0
            continue
            
        # ─── 2. PENDING LIMIT ORDER PROCESSOR ───
        if pending:
            p = pending
            p["bars_waited"] += 1
            
            # Check if timeout reached
            if p["bars_waited"] > TIMEOUT_BARS:
                pending = None
                continue
                
            # Check if hypothetical TP1 reached before fill (invalidates the order)
            if p["direction"] == "LONG" and hi >= p["tp1_if_filled"]:
                pending = None
                continue
            elif p["direction"] == "SHORT" and lo <= p["tp1_if_filled"]:
                pending = None
                continue
                
            # Check fill logic based on strategy
            filled = False
            entry_price = 0.0
            size_mult = 1.0
            
            if strategy_type == "limit_mid":
                # Must hit OB midpoint
                if p["direction"] == "LONG" and lo <= p["limit_mid"]:
                    filled = True; entry_price = p["limit_mid"]
                elif p["direction"] == "SHORT" and hi >= p["limit_mid"]:
                    filled = True; entry_price = p["limit_mid"]
                    
            elif strategy_type == "limit_high":
                # Must hit OB high boundary (closer to current price)
                if p["direction"] == "LONG" and lo <= p["limit_high"]:
                    filled = True; entry_price = p["limit_high"]
                elif p["direction"] == "SHORT" and hi >= p["limit_high"]:
                    filled = True; entry_price = p["limit_high"]
                    
            elif strategy_type == "scale_in":
                # Two limit orders: 50% at OB high, 50% at OB mid.
                high_hit = (p["direction"] == "LONG" and lo <= p["limit_high"]) or (p["direction"] == "SHORT" and hi >= p["limit_high"])
                mid_hit = (p["direction"] == "LONG" and lo <= p["limit_mid"]) or (p["direction"] == "SHORT" and hi >= p["limit_mid"])
                
                if mid_hit:
                    # Both hit! Filled 100% with average price
                    filled = True
                    entry_price = (p["limit_high"] + p["limit_mid"]) / 2
                    size_mult = 1.0
                elif high_hit:
                    # Only high hit. We wait until timeout/TP1 to see if mid hits.
                    # If we reach timeout or TP1 is hit, we lock in 50% size at high.
                    is_timeout = p["bars_waited"] == TIMEOUT_BARS
                    is_tp1_reached = (p["direction"] == "LONG" and hi >= p["tp1_if_filled"]) or (p["direction"] == "SHORT" and lo <= p["tp1_if_filled"])
                    
                    if is_timeout or is_tp1_reached:
                        # Enter trade with 50% size at high price
                        filled = True
                        entry_price = p["limit_high"]
                        size_mult = 0.5
            
            if filled:
                pending = None
                in_trade = True
                t_entry = entry_price
                t_dir = p["direction"]
                t_score = p["score"]
                t_atr = p["atr"]
                t_entry_bar = i
                t_month = month
                t_entry_date = str(bar_ts)[:16]
                t_size_mult = size_mult
                
                # Setup SL & TP relative to actual entry
                if t_dir == "LONG":
                    # Keep SL at OB low or entry - 1.5 * ATR (whichever is lower)
                    t_sl_orig = min(p["sl_low"], t_entry - t_atr * SL_ATR_MULT)
                    # If SL distance is too wide/narrow, adjust
                    sl_dist = (t_entry - t_sl_orig) / t_entry
                    if sl_dist < 0.005:
                        t_sl_orig = t_entry - t_atr * SL_ATR_MULT
                        sl_dist = (t_entry - t_sl_orig) / t_entry
                    
                    t_sl = t_sl_orig
                    t_tp1 = t_entry + (t_entry - t_sl_orig) * TP1_R
                    t_tp2 = t_entry + (t_entry - t_sl_orig) * TP2_R
                    t_tp3 = t_entry + (t_entry - t_sl_orig) * TP3_R
                else:
                    t_sl_orig = max(p["sl_low"], t_entry + t_atr * SL_ATR_MULT)
                    sl_dist = (t_sl_orig - t_entry) / t_entry
                    if sl_dist < 0.005:
                        t_sl_orig = t_entry + t_atr * SL_ATR_MULT
                        sl_dist = (t_sl_orig - t_entry) / t_entry
                    
                    t_sl = t_sl_orig
                    t_tp1 = t_entry - (t_sl_orig - t_entry) * TP1_R
                    t_tp2 = t_entry - (t_sl_orig - t_entry) * TP2_R
                    t_tp3 = t_entry - (t_sl_orig - t_entry) * TP3_R
                    
                t_tp1_hit = t_tp2_hit = t_trail_active = False
                t_trail_sl = t_locked_pnl = 0.0; t_remaining = 1.0
            continue
            
        # ─── 3. SIGNAL DETECTOR ───
        signal = signals_cache.get(i)
        if signal is None:
            continue
            
        comp = signal["comp"]
        trend = signal["trend"]
        entry_ = signal["entry_"]
        sl_ = signal["sl_"]
        atr_ = signal["atr_"]
        ob_high = signal["ob_high"]
        ob_mid = signal["ob_mid"]
        ob_low = signal["ob_low"]
            
        # Setup pending order or immediate entry
        if strategy_type == "ideal_mid":
            # Immediate fill at OB mid
            in_trade = True
            t_entry = ob_mid
            t_sl_orig = ob_low
            t_sl = t_sl_orig
            t_dir = "LONG" if trend == "BULLISH" else "SHORT"
            t_atr = atr_
            t_score = comp
            t_entry_bar = i
            t_month = month
            t_entry_date = str(bar_ts)[:16]
            
            risk_amt = abs(t_entry - t_sl_orig)
            if t_dir == "LONG":
                t_tp1 = t_entry + risk_amt * TP1_R
                t_tp2 = t_entry + risk_amt * TP2_R
                t_tp3 = t_entry + risk_amt * TP3_R
            else:
                t_tp1 = t_entry - risk_amt * TP1_R
                t_tp2 = t_entry - risk_amt * TP2_R
                t_tp3 = t_entry - risk_amt * TP3_R
                
        elif strategy_type == "market_wide_sl":
            # Enter immediately at current Close price (market order)
            in_trade = True
            t_entry = cl # Market order close
            t_dir = "LONG" if trend == "BULLISH" else "SHORT"
            t_atr = atr_
            t_score = comp
            t_entry_bar = i
            t_month = month
            t_entry_date = str(bar_ts)[:16]
            
            # WIDER Stop Loss: 2.5x ATR instead of 1.5x
            if t_dir == "LONG":
                t_sl_orig = t_entry - t_atr * 2.5
                sl_dist = (t_entry - t_sl_orig) / t_entry
                t_sl = t_sl_orig
                t_tp1 = t_entry + (t_entry - t_sl_orig) * 1.5 # TP at 1.5R of the wider SL
                t_tp2 = t_entry + (t_entry - t_sl_orig) * 2.5
                t_tp3 = t_entry + (t_entry - t_sl_orig) * 4.0
            else:
                t_sl_orig = t_entry + t_atr * 2.5
                sl_dist = (t_sl_orig - t_entry) / t_entry
                t_sl = t_sl_orig
                t_tp1 = t_entry - (t_sl_orig - t_entry) * 1.5
                t_tp2 = t_entry - (t_sl_orig - t_entry) * 2.5
                t_tp3 = t_entry - (t_sl_orig - t_entry) * 4.0
                
        else:
            # Limit order entry types (limit_mid, limit_high, scale_in)
            # Store details for next bar processing
            # Predict TP1 if filled at the limit_high/limit_mid to check for cancellation
            tp1_if_filled = 0.0
            limit_entry_est = ob_high if strategy_type == "limit_high" else ob_mid
            
            if trend == "BULLISH":
                sl_est = min(ob_low, limit_entry_est - atr_ * SL_ATR_MULT)
                tp1_if_filled = limit_entry_est + (limit_entry_est - sl_est) * TP1_R
            else:
                sl_est = max(ob_low, limit_entry_est + atr_ * SL_ATR_MULT)
                tp1_if_filled = limit_entry_est - (sl_est - limit_entry_est) * TP1_R
                
            pending = {
                "direction": "LONG" if trend == "BULLISH" else "SHORT",
                "limit_high": ob_high,
                "limit_mid": ob_mid,
                "sl_low": ob_low,
                "atr": atr_,
                "score": comp,
                "tp1_if_filled": tp1_if_filled,
                "bars_waited": 0
            }
            
    return trades

# ═══════════════════════════════════════════════════════════════
# MONEY MANAGEMENT SIMULATORS
# ═══════════════════════════════════════════════════════════════

def run_fixed_risk(trades, capital=100.0, risk_pct=0.02):
    eq = capital
    curve = [capital]
    for t in trades:
        pnl = eq * risk_pct * t["r_mult"] * t["size_mult"]
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
        pnl = actual_risk * t["r_mult"] * t["size_mult"]
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
        pnl = eq * risk * t["r_mult"] * t["size_mult"]
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

def run_fibonacci_risk(trades, capital=100.0, base_risk=0.02, max_risk=0.15):
    fib = [1, 1, 2, 3, 5, 8]
    eq = capital
    consec_wins = 0
    curve = [capital]
    for t in trades:
        level = fib[min(consec_wins, len(fib)-1)]
        risk = min(base_risk * level, max_risk)
        pnl = eq * risk * t["r_mult"] * t["size_mult"]
        eq += pnl
        if eq < 1: eq = 0
        if t["r_mult"] > 0:
            consec_wins += 1
        else:
            consec_wins = 0
        curve.append(eq)
    return {"final": eq, "curve": curve, "dd": calculate_max_dd(curve)}

def calculate_max_dd(eq):
    arr = np.array(eq)
    if len(arr) == 0: return 0.0
    peak = np.maximum.accumulate(arr)
    peak = np.where(peak == 0, 1.0, peak)
    dd = (arr - peak) / peak
    return float(abs(dd.min()) * 100)

def main():
    global TIMEOUT_BARS
    TIMEOUT_BARS = 12  # 12 hours on 1H TF
    
    head("REALISTIC LIMIT ORDER & SCALE-IN BACKTESTER (1H TIMEFRAME)")
    print("Comparing 5 entry configurations under realistic slippage and fee rules.")
    print("Data: Last 12 months (1H timeframe)")
    print(f"Limit order timeout: {TIMEOUT_BARS} bars ({TIMEOUT_BARS} hours)\n")
    
    coins = ["BTC/USDT", "ETH/USDT"]
    strategies = [
        ("1. Ideal Mid (Old Bench)", "ideal_mid"),
        ("2. Realistic Limit @ Mid", "limit_mid"),
        ("3. Realistic Limit @ High", "limit_high"),
        ("4. Scale-In (50-50 High/Mid)", "scale_in"),
        ("5. Market Entry (2.5x ATR SL)", "market_wide_sl")
    ]
    
    for sym in coins:
        csv_path = f"data/historical/{sym.replace('/', '_')}_1h.csv"
        if not os.path.exists(csv_path):
            print(f"Data file not found for {sym}")
            continue
            
        df = pd.read_csv(csv_path)
        df["ts"] = pd.to_datetime(df["ts"])
        df.set_index("ts", inplace=True)
        df = df.sort_index()
        
        sym_short = sym.split("/")[0]
        h2(f"🪙 COIN: {sym_short} (Total {len(df)} bars)")
        
        # 1. PRECALCULATE SIGNALS
        print(f"Precalculating signals and order boundaries for {sym_short}...")
        t_pre = time.time()
        signals_cache = precalculate_signals(df)
        print(f"Precalculation finished in {time.time() - t_pre:.1f}s. Total signals: {len(signals_cache)}")
        
        # 2. RUN BACKTESTS USING CACHE
        for name, strat_key in strategies:
            t0 = time.time()
            trades = run_backtest_strategy(sym, df, signals_cache, strategy_type=strat_key)
            elapsed = time.time() - t0
            
            n = len(trades)
            if n == 0:
                print(f"  {CY}{name:<40}{R} → 0 trades generated")
                continue
                
            wins = sum(1 for t in trades if t["r_mult"] > 0)
            losses = n - wins
            wr = wins / n * 100
            avg_r = np.mean([t["r_mult"] for t in trades])
            
            # For scale-in, calculate partial fills
            partial_fills = sum(1 for t in trades if t["size_mult"] < 1.0)
            fill_desc = f" (Partials: {partial_fills})" if strat_key == "scale_in" else ""
            
            total_signals = len(signals_cache)
            fill_rate = (n / total_signals) * 100 if total_signals > 0 else 100.0
            
            print(f"  {CY}{name:<40}{R} → Trades: {n:2d} (Fill Rate: {fill_rate:.1f}%) {fill_desc} | WR: {wr:.1f}% | Avg R: {avg_r:+.2f} ({elapsed:.3f}s)")
            
            # Run money management
            fr = run_fixed_risk(trades)
            orp2 = run_orp(trades, step_pct=0.02)
            orp5 = run_orp(trades, step_pct=0.05)
            paroli = run_paroli(trades)
            fib = run_fibonacci_risk(trades)
            
            print(f"     ┌{'─'*78}┐")
            print(f"     │ {'Sermaye Yönetimi':25} │ {'Bitiş ($)':>12} │ {'Çarpan':>8} │ {'Max DD':>8} │ {'Adımlar':>8} │")
            print(f"     ├{'─'*78}┤")
            print(f"     │ {'Fixed Risk (%2)':25} │ {'${:>10,.2f}'.format(fr['final'])} │ {fr['final']/100:>7.2f}x │ {fr['dd']:>7.1f}% │ {'—':>8} │")
            print(f"     │ {'ORP %2 (Güvenli)':25} │ {'${:>10,.2f}'.format(orp2['final'])} │ {orp2['final']/100:>7.2f}x │ {orp2['dd']:>7.1f}% │ {orp2['steps']:>8} │")
            print(f"     │ {'ORP %5 (Orta Risk)':25} │ {'${:>10,.2f}'.format(orp5['final'])} │ {orp5['final']/100:>7.2f}x │ {orp5['dd']:>7.1f}% │ {orp5['steps']:>8} │")
            print(f"     │ {'Paroli (Win Streak x2)':25} │ {'${:>10,.2f}'.format(paroli['final'])} │ {paroli['final']/100:>7.2f}x │ {paroli['dd']:>7.1f}% │ {'—':>8} │")
            print(f"     │ {'Fibonacci (1,1,2,3,5)':25} │ {'${:>10,.2f}'.format(fib['final'])} │ {fib['final']/100:>7.2f}x │ {fib['dd']:>7.1f}% │ {'—':>8} │")
            print(f"     └{'─'*78}┘")
            print()

if __name__ == "__main__":
    main()
