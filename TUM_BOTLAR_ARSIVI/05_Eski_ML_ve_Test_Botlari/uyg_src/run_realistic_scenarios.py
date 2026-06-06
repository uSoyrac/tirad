#!/usr/bin/env python3
"""
run_realistic_scenarios.py — 180 GÜNLÜK GERÇEKÇİ SENARYO RAPORLAYICI
═════════════════════════════════════════════════════════════════════
Runs the Hardcore Recovery Progression simulator on two highly realistic
scenarios over the last 180 days (6 months / 1100 4H bars / 4300 1H bars).

Scenario 1: 5-Coin Portfolio on 4H (BTC, ETH, SOL, BNB, XRP)
Scenario 2: Single Coin ETH on 1H Timeframe (High Frequency)
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

# Hardcore costs
COMMISSION_HC = 0.0004
SLIPPAGE_HC   = 0.0010
LIMIT_SLIPPAGE = 0.0002

CAPITAL = 100.0
TIMEOUT_BARS = 12
MAX_OPEN_TRADES = 4
RISK_CAP = 0.15

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

def precalculate_signals(coins, tf="4h", limit_bars=1100):
    """Precalculates S3 signals for the specified timeframe and limit bars."""
    # 1. Load BTC trend first
    btc_csv = f"data/historical/BTC_USDT_{tf}.csv"
    if not os.path.exists(btc_csv):
        btc_trends = {}
    else:
        btc_df = pd.read_csv(btc_csv)
        btc_df["ts"] = pd.to_datetime(btc_df["ts"])
        btc_df.set_index("ts", inplace=True)
        btc_df = btc_df.sort_index()
        btc_trends = {}
        # Warmup and loop over target range
        for i in range(max(WARMUP, len(btc_df) - limit_bars), len(btc_df) - 1):
            slice_df = btc_df.iloc[max(0, i-300):i]
            btc_trends[btc_df.index[i]] = _trend_1d(slice_df)
            
    signals_by_coin = {}
    for sym in coins:
        csv_path = f"data/historical/{sym.replace('/', '_')}_{tf}.csv"
        if not os.path.exists(csv_path):
            continue
        df = pd.read_csv(csv_path)
        df["ts"] = pd.to_datetime(df["ts"])
        df.set_index("ts", inplace=True)
        df = df.sort_index()
        
        signals = {}
        for i in range(max(WARMUP, len(df) - limit_bars), len(df) - 1):
            ts = df.index[i]
            btc_macro_trend = btc_trends.get(ts, "NEUTRAL")
            if btc_macro_trend == "NEUTRAL":
                continue
            df_slice = df.iloc[max(0, i-300):i]
            
            # For 1H, we relax score slightly to 3.5 to get more trades (Config D)
            score_threshold = 3.5 if tf == "1h" else 4.5
            
            comp, trend, entry_, sl_, atr_, vol_ok_ = score_slice_v2(df_slice)
            if comp < score_threshold or trend == "NEUTRAL" or entry_ is None:
                continue
                
            # Filter: 1D Trend check for 4H, or local trend check
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

def run_recovery_backtest(signals_by_coin, target_cycle_profit=5.0):
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
    
    peak_equity = CAPITAL
    target_equity = peak_equity + target_cycle_profit
    
    for ts in sorted_timestamps:
        # Exit checker
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
                        t["trail_sl"] = max(t["trail_sl"], t["entry"] + t["atr"] * 0.5)
                    elif not t["tp1_hit"] and hi >= t["tp1"]:
                        t["locked_pnl"] += TP1_CLOSE * TP1_R; t["tp1_hit"] = True
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
                        t["trail_sl"] = min(t["trail_sl"], t["entry"] - t["atr"] * 0.5)
                    elif not t["tp1_hit"] and lo <= t["tp1"]:
                        t["locked_pnl"] += TP1_CLOSE * TP1_R; t["tp1_hit"] = True
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
                    "r_mult": net_r,
                    "dollar_pnl": dollar_pnl,
                    "equity": equity
                })
                
                if net_r > 0:
                    if equity >= target_equity:
                        peak_equity = equity
                        target_equity = peak_equity + target_cycle_profit
                else:
                    if t["direction"] == "LONG":
                        last_long_loss_ts = ts
                    else:
                        last_short_loss_ts = ts
                    
                del active_trades[coin]
                
        # Pending checks
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
                if len(active_trades) >= MAX_OPEN_TRADES:
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
                    
                # Recovery sizing
                deficit = target_equity - equity
                risk_pct = deficit / 1.5 / equity if equity > 0 else 0.02
                
                if risk_pct > RISK_CAP: risk_pct = RISK_CAP
                if risk_pct < 0.01: risk_pct = 0.01
                    
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
 
        # New signal scanner
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
    head("180 GÜNLÜK GERÇEKÇİ SENARYO ANALİZİ")
    print("Son 180 Günde (6 Ay) 5% Hedef-Döngülü Kurtarma İlerlemesi.")
    print("Komisyon ve Slippage Dahil | 1 Bar İşlem Gecikmesi.")
    
    coins_5 = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
    
    # ----------------------------------------------------
    # SENARYO 1: 5 Coin Portföyü (4H) - Son 180 Gün (1100 Bar)
    # ----------------------------------------------------
    h2("SENARYO 1: 5 Coinlik 4H Portföyü (Son 180 Gün)")
    print("  Sinyaller hesaplanıyor...")
    sig_4h = precalculate_signals(coins_5, tf="4h", limit_bars=1100)
    res_4h = run_recovery_backtest(sig_4h, target_cycle_profit=5.0)
    
    trades_4h = res_4h["trades"]
    n_4h = len(trades_4h)
    
    if n_4h > 0:
        wins_4h = sum(1 for t in trades_4h if t["r_mult"] > 0)
        wr_4h = wins_4h / n_4h * 100
        final_4h = res_4h["final_eq"]
        mdd_4h = calculate_max_dd(res_4h["equity_curve"])
        completed_4h = 0
        target_4h = CAPITAL + 5.0
        for t in trades_4h:
            if t["equity"] >= target_4h:
                completed_4h += 1
                target_4h = t["equity"] + 5.0
        print(f"  {ok('✅')} İşlem Sayısı : {n_4h}  |  Win Rate: %{wr_4h:.1f}")
        print(f"  {ok('✅')} Bitiş Bakiyesi : ${final_4h:.2f} ({final_4h/CAPITAL:.2f}x)")
        print(f"  {ok('✅')} Max Drawdown    : %{mdd_4h:.1f}")
        print(f"  {ok('✅')} Tamamlanan %5 : {completed_4h} döngü")
    else:
        print("  İşlem gerçekleşmedi.")
        
    # ----------------------------------------------------
    # SENARYO 2: Tek Coin ETH (1H) - Son 180 Gün (4300 Bar, Config D)
    # ----------------------------------------------------
    h2("SENARYO 2: Yüksek Frekanslı ETH 1H (Son 180 Gün)")
    print("  Sinyaller hesaplanıyor (Bu işlem ~30sn sürebilir)...")
    sig_1h = precalculate_signals(["ETH/USDT"], tf="1h", limit_bars=4300)
    res_1h = run_recovery_backtest(sig_1h, target_cycle_profit=5.0)
    
    trades_1h = res_1h["trades"]
    n_1h = len(trades_1h)
    
    if n_1h > 0:
        wins_1h = sum(1 for t in trades_1h if t["r_mult"] > 0)
        wr_1h = wins_1h / n_1h * 100
        final_1h = res_1h["final_eq"]
        mdd_1h = calculate_max_dd(res_1h["equity_curve"])
        completed_1h = 0
        target_1h = CAPITAL + 5.0
        for t in trades_1h:
            if t["equity"] >= target_1h:
                completed_1h += 1
                target_1h = t["equity"] + 5.0
        print(f"  {ok('✅')} İşlem Sayısı : {n_1h}  |  Win Rate: %{wr_1h:.1f}")
        print(f"  {ok('✅')} Bitiş Bakiyesi : ${final_1h:.2f} ({final_1h/CAPITAL:.2f}x)")
        print(f"  {ok('✅')} Max Drawdown    : %{mdd_1h:.1f}")
        print(f"  {ok('✅')} Tamamlanan %5 : {completed_1h} döngü")
    else:
        print("  İşlem gerçekleşmedi.")

if __name__ == "__main__":
    main()
