#!/usr/bin/env python3
"""
HYBRID ENTRY OPTIMIZER
═══════════════════════════════════════════════════════════════
Giriş mekanizması sorununu çözmek için 4 farklı modeli test eder:
1. Limit @ OB Mid (Yüksek R:R, Düşük Dolum)
2. Scale-In DCA @ OB High & Mid (Dengeli)
3. Market Order @ Next Open + Geniş SL (Kesin Dolum, Düşük R:R)
4. Hibrit: Limit @ OB Mid, Timeout = 3 bar, if timeout -> Market Fallback
"""
import os, sys, time, warnings
import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")
from backtest_multi_tf import score_slice_v2, WARMUP, EMA_TREND_PERIOD, TP1_R, TP2_R, TP3_R, TP1_CLOSE, TP2_CLOSE, TP3_CLOSE
from live_scan import order_blocks, fair_value_gaps

COMMISSION = 0.0004
SLIPPAGE_MARKET = 0.0010
SLIPPAGE_LIMIT = 0.0002
CAPITAL = 100.0

def _trend_1d(df_slice):
    cp = float(df_slice["close"].iloc[-1])
    try:
        ema = float(df_slice["close"].ewm(span=EMA_TREND_PERIOD, adjust=False).mean().iloc[-1])
    except:
        ema = cp
    return "BULLISH" if cp > ema else "BEARISH" if cp < ema else "NEUTRAL"

def simulate_entry_model(df_full, symbol, model_name="limit_mid"):
    """
    model_name: "limit_mid", "scale_in", "market", "hybrid"
    """
    trades = []
    total = len(df_full)
    
    in_trade = False
    pending_orders = []
    
    t_dir = ""
    t_entry = 0.0
    t_sl = 0.0
    t_sl_orig = 0.0
    t_atr = 0.0
    t_tp1 = 0.0
    t_tp2 = 0.0
    t_tp3 = 0.0
    t_tp1_hit = False
    t_tp2_hit = False
    t_locked_pnl = 0.0
    
    for i in range(WARMUP, total - 1):
        df_slice = df_full.iloc[max(0, i-300):i]
        bar = df_full.iloc[i]
        
        hi = float(bar["high"])
        lo = float(bar["low"])
        cl = float(bar["close"])
        op = float(bar["open"])
        
        # --- EXIT MANAGEMENT ---
        if in_trade:
            exited = False
            pnl_r = 0.0
            exit_price = 0.0
            
            sl_dist = abs(t_entry - t_sl_orig) / t_entry
            
            if t_dir == "LONG":
                if lo <= t_sl:
                    pnl_r = t_locked_pnl if t_tp1_hit else -1.0
                    exited = True
                    exit_price = t_sl
                elif hi >= t_tp3:
                    pnl_r = t_locked_pnl + TP3_CLOSE * TP3_R
                    exited = True
                    exit_price = t_tp3
                elif not t_tp2_hit and hi >= t_tp2:
                    t_locked_pnl += TP2_CLOSE * TP2_R
                    t_tp2_hit = True
                elif not t_tp1_hit and hi >= t_tp1:
                    t_locked_pnl += TP1_CLOSE * TP1_R
                    t_tp1_hit = True
                    t_sl = t_entry * 1.001
            else:
                if hi >= t_sl:
                    pnl_r = t_locked_pnl if t_tp1_hit else -1.0
                    exited = True
                    exit_price = t_sl
                elif lo <= t_tp3:
                    pnl_r = t_locked_pnl + TP3_CLOSE * TP3_R
                    exited = True
                    exit_price = t_tp3
                elif not t_tp2_hit and lo <= t_tp2:
                    t_locked_pnl += TP2_CLOSE * TP2_R
                    t_tp2_hit = True
                elif not t_tp1_hit and lo <= t_tp1:
                    t_locked_pnl += TP1_CLOSE * TP1_R
                    t_tp1_hit = True
                    t_sl = t_entry * 0.999
            
            if exited:
                cost = (COMMISSION * 2) + SLIPPAGE_MARKET + (SLIPPAGE_LIMIT if model_name != "market" else SLIPPAGE_MARKET)
                net_r = pnl_r - cost / sl_dist if sl_dist > 0 else pnl_r
                
                trades.append({
                    "r_mult": net_r,
                    "sl_pct": sl_dist * 100,
                    "type": "trade"
                })
                in_trade = t_tp1_hit = t_tp2_hit = False
                t_locked_pnl = 0.0
            continue
            
        # --- PENDING ORDERS MANAGEMENT (for limit/hybrid/scale-in) ---
        if pending_orders and not in_trade:
            filled = False
            for p in pending_orders:
                p["wait"] += 1
                
                if p["dir"] == "LONG" and lo <= p["price"]:
                    filled = True; fill_price = p["price"]; sl_price = p["sl"]; d = "LONG"; atr = p["atr"]
                    break
                elif p["dir"] == "SHORT" and hi >= p["price"]:
                    filled = True; fill_price = p["price"]; sl_price = p["sl"]; d = "SHORT"; atr = p["atr"]
                    break
            
            if filled:
                in_trade = True
                t_entry = fill_price
                t_sl = sl_price
                t_sl_orig = sl_price
                t_dir = d
                t_atr = atr
                risk = abs(fill_price - sl_price)
                if d == "LONG":
                    t_tp1 = fill_price + risk * TP1_R
                    t_tp2 = fill_price + risk * TP2_R
                    t_tp3 = fill_price + risk * TP3_R
                else:
                    t_tp1 = fill_price - risk * TP1_R
                    t_tp2 = fill_price - risk * TP2_R
                    t_tp3 = fill_price - risk * TP3_R
                pending_orders = []
                continue
            
            # Timeout / Fallback logic
            if pending_orders:
                p = pending_orders[0]
                if p["wait"] > 3:
                    if model_name == "hybrid":
                        # Market fallback
                        in_trade = True
                        t_entry = op  # Next open
                        t_dir = p["dir"]
                        t_atr = p["atr"]
                        # Wider SL for market fallback
                        t_sl = t_entry - t_atr * 2.5 if t_dir == "LONG" else t_entry + t_atr * 2.5
                        t_sl_orig = t_sl
                        risk = abs(t_entry - t_sl)
                        if t_dir == "LONG":
                            t_tp1 = t_entry + risk * (TP1_R * 0.8)  # Reduced TP ratio
                            t_tp2 = t_entry + risk * (TP2_R * 0.8)
                            t_tp3 = t_entry + risk * (TP3_R * 0.8)
                        else:
                            t_tp1 = t_entry - risk * (TP1_R * 0.8)
                            t_tp2 = t_entry - risk * (TP2_R * 0.8)
                            t_tp3 = t_entry - risk * (TP3_R * 0.8)
                        pending_orders = []
                        continue
                    else:
                        pending_orders = []  # Just cancel
                        
        # --- SIGNAL DETECTION ---
        if not in_trade and not pending_orders:
            comp, trend, entry_, sl_, atr_, vol_ok_ = score_slice_v2(df_slice)
            if comp < 4.5 or trend == "NEUTRAL" or not vol_ok_:
                continue
                
            bull_obs, bear_obs, _, _ = order_blocks(df_slice)
            
            ob_mid, ob_high = None, None
            if trend == "BULLISH" and bull_obs:
                ob_mid = float(bull_obs[0]["mid"])
                ob_high = float(bull_obs[0]["high"])
            elif trend == "BEARISH" and bear_obs:
                ob_mid = float(bear_obs[0]["mid"])
                ob_high = float(bear_obs[0]["low"])
                
            if not ob_mid:
                continue
                
            if model_name == "market":
                in_trade = True
                t_entry = op  # Market open
                t_dir = trend
                t_atr = atr_
                t_sl = t_entry - atr_ * 2.5 if trend == "BULLISH" else t_entry + atr_ * 2.5
                t_sl_orig = t_sl
                risk = abs(t_entry - t_sl)
                if t_dir == "LONG":
                    t_tp1 = t_entry + risk * TP1_R
                    t_tp2 = t_entry + risk * TP2_R
                    t_tp3 = t_entry + risk * TP3_R
                else:
                    t_tp1 = t_entry - risk * TP1_R
                    t_tp2 = t_entry - risk * TP2_R
                    t_tp3 = t_entry - risk * TP3_R
            elif model_name == "limit_mid":
                pending_orders.append({
                    "dir": trend,
                    "price": ob_mid,
                    "sl": ob_mid - atr_ * 1.5 if trend == "BULLISH" else ob_mid + atr_ * 1.5,
                    "atr": atr_,
                    "wait": 0
                })
            elif model_name == "scale_in":
                # Simplified 50/50 scale-in by just targeting OB High with wider SL
                pending_orders.append({
                    "dir": trend,
                    "price": ob_high,
                    "sl": ob_high - atr_ * 2.0 if trend == "BULLISH" else ob_high + atr_ * 2.0,
                    "atr": atr_,
                    "wait": 0
                })
            elif model_name == "hybrid":
                pending_orders.append({
                    "dir": trend,
                    "price": ob_mid,
                    "sl": ob_mid - atr_ * 1.5 if trend == "BULLISH" else ob_mid + atr_ * 1.5,
                    "atr": atr_,
                    "wait": 0
                })
                
    return trades

def run_orp(trades, cycle_pct=0.10, max_risk=0.20, rec_factor=1.0):
    equity = 100.0
    peak_eq = 100.0
    target_eq = 100.0
    step = 0
    
    for t in trades:
        while equity >= target_eq:
            step += 1
            target_eq = 100.0 * ((1.0 + cycle_pct) ** step)
            
        if equity > peak_eq: peak_eq = equity
            
        delta = target_eq - equity
        req_risk = max(equity * 0.04, delta / rec_factor)
        actual_risk = min(req_risk, equity * max_risk)
        
        sl_pct = t["sl_pct"] / 100.0
        if sl_pct <= 0: sl_pct = 0.01
        
        pos_size = actual_risk / sl_pct
        if pos_size > equity * 10.0:  # Max lev 10x
            pos_size = equity * 10.0
            actual_risk = pos_size * sl_pct
            
        equity += actual_risk * t["r_mult"]
        if equity <= 1.0: return 0.0, step
        
    return equity, step

def main():
    print("HYBRID ENTRY OPTIMIZER (ETH 1H & 4H)")
    
    models = ["limit_mid", "scale_in", "market", "hybrid"]
    tfs = ["1h", "4h"]
    
    for tf in tfs:
        print(f"\n--- Zaman Dilimi: {tf.upper()} ---")
        csv_path = f"data/historical/ETH_USDT_{tf}.csv"
        if not os.path.exists(csv_path): continue
        
        df = pd.read_csv(csv_path).tail(2000)
        
        for model in models:
            t0 = time.time()
            trades = simulate_entry_model(df, "ETH", model)
            elapsed = time.time() - t0
            
            if not trades:
                print(f"{model:<12}: İşlem Yok")
                continue
                
            wins = sum(1 for t in trades if t["r_mult"] > 0)
            wr = wins / len(trades) * 100
            avg_r = sum(t["r_mult"] for t in trades) / len(trades)
            
            eq, steps = run_orp(trades)
            
            print(f"{model:<12} | İşlem: {len(trades):<3} | WR: %{wr:.1f} | Ort R: {avg_r:+.2f} | Bitiş: ${eq:>8.2f} ({eq/100:.1f}x) | Süre: {elapsed:.1f}s")

if __name__ == "__main__":
    main()
