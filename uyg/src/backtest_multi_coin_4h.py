#!/usr/bin/env python3
"""
MULTI-COIN 4H PORTFOLIO BACKTESTER (AKILLI LİMİT EMİR MOTORU)
═══════════════════════════════════════════════════════════════
- Zaman Dilimi: 4H
- Kapsam: 15-20 Likit Coin
- Giriş Stratejisi: Scale-In (50% OB High, 50% OB Mid)
- Timeout: 3 bar (12 saat)
- Gerçekçi Maliyetler: Limit Order %0.02 kayma, %0.04 komisyon
"""
import os, sys, time, warnings
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

# Import indicators and scoring
from backtest_multi_tf import score_slice_v2, WARMUP, EMA_TREND_PERIOD, TP1_R, TP2_R, TP3_R, TP1_CLOSE, TP2_CLOSE, TP3_CLOSE, _atr
from live_scan import order_blocks, fair_value_gaps

# Configuration
COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]
TIMEFRAME = "4h"
BAR_LIMIT = 2000  # Approx 333 days on 4H
TIMEOUT_BARS = 3  # 12 hours on 4H
COMMISSION = 0.0004
SLIPPAGE_LIMIT = 0.0002
SLIPPAGE_MARKET = 0.0010

def _trend_1d(df_slice):
    cp = float(df_slice["close"].iloc[-1])
    try:
        ema = float(df_slice["close"].ewm(span=EMA_TREND_PERIOD, adjust=False).mean().iloc[-1])
    except:
        ema = cp
    return "BULLISH" if cp > ema else "BEARISH" if cp < ema else "NEUTRAL"

def simulate_coin(symbol):
    csv_path = f"data/historical/{symbol}_USDT_{TIMEFRAME}.csv"
    if not os.path.exists(csv_path):
        return []
        
    df = pd.read_csv(csv_path)
    if df.empty or len(df) < WARMUP + 50:
        return []
        
    df["ts"] = pd.to_datetime(df["ts"])
    df.set_index("ts", inplace=True)
    df = df.sort_index().tail(BAR_LIMIT)
    
    total = len(df)
    trades = []
    
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
    
    # Pre-calculate to speed up
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    
    for i in range(WARMUP, total - 1):
        hi = highs[i]
        lo = lows[i]
        cl = closes[i]
        
        # --- EXIT MANAGEMENT ---
        if in_trade:
            exited = False
            pnl_r = 0.0
            
            sl_dist = abs(t_entry - t_sl_orig) / t_entry
            
            if t_dir == "LONG":
                if lo <= t_sl:
                    pnl_r = t_locked_pnl if t_tp1_hit else -1.0
                    exited = True
                elif hi >= t_tp3:
                    pnl_r = t_locked_pnl + TP3_CLOSE * TP3_R
                    exited = True
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
                elif lo <= t_tp3:
                    pnl_r = t_locked_pnl + TP3_CLOSE * TP3_R
                    exited = True
                elif not t_tp2_hit and lo <= t_tp2:
                    t_locked_pnl += TP2_CLOSE * TP2_R
                    t_tp2_hit = True
                elif not t_tp1_hit and lo <= t_tp1:
                    t_locked_pnl += TP1_CLOSE * TP1_R
                    t_tp1_hit = True
                    t_sl = t_entry * 0.999
            
            if exited:
                # Calculate blended entry cost for scale-in: 
                # we just use limit slippage + commission for entry, and market slippage for stop out or limit for TP
                cost = (COMMISSION * 2) + SLIPPAGE_LIMIT + (SLIPPAGE_MARKET if not t_tp1_hit else SLIPPAGE_LIMIT)
                net_r = pnl_r - cost / sl_dist if sl_dist > 0 else pnl_r
                
                trades.append({
                    "symbol": symbol,
                    "exit_ts": df.index[i],
                    "r_mult": net_r,
                    "sl_pct": sl_dist * 100
                })
                in_trade = t_tp1_hit = t_tp2_hit = False
                t_locked_pnl = 0.0
            continue
            
        # --- PENDING ORDERS MANAGEMENT (SCALE-IN) ---
        if pending_orders and not in_trade:
            filled_count = 0
            avg_entry = 0.0
            p_sl = 0.0
            p_dir = ""
            p_atr = 0.0
            
            for p in pending_orders:
                p["wait"] += 1
                
                if not p["filled"]:
                    # Is it cancelled because TP1 reached before entry?
                    # Since we don't have entry yet, we check if price went away too far
                    if p["dir"] == "LONG" and hi >= p["price"] + p["atr"] * 2.0:
                        p["cancelled"] = True
                    elif p["dir"] == "SHORT" and lo <= p["price"] - p["atr"] * 2.0:
                        p["cancelled"] = True
                        
                    if not p.get("cancelled", False):
                        if p["dir"] == "LONG" and lo <= p["price"]:
                            p["filled"] = True
                        elif p["dir"] == "SHORT" and hi >= p["price"]:
                            p["filled"] = True
            
            # Remove cancelled or timed out
            pending_orders = [p for p in pending_orders if not p.get("cancelled", False) and p["wait"] <= TIMEOUT_BARS]
            
            # Check if we should activate the trade (we activate if at least 1 fills and we move to next bar, or if both fill)
            # For simplicity in this backtest, if ANY order fills, we enter the trade with that avg price
            fills = [p for p in pending_orders if p.get("filled", False)]
            if fills:
                in_trade = True
                t_entry = sum(f["price"] for f in fills) / len(fills)
                t_sl = fills[0]["sl"]
                t_sl_orig = t_sl
                t_dir = fills[0]["dir"]
                t_atr = fills[0]["atr"]
                
                risk = abs(t_entry - t_sl)
                if t_dir == "LONG":
                    t_tp1 = t_entry + risk * TP1_R
                    t_tp2 = t_entry + risk * TP2_R
                    t_tp3 = t_entry + risk * TP3_R
                else:
                    t_tp1 = t_entry - risk * TP1_R
                    t_tp2 = t_entry - risk * TP2_R
                    t_tp3 = t_entry - risk * TP3_R
                
                pending_orders = []
                continue
                
        # --- SIGNAL DETECTION ---
        if not in_trade and not pending_orders:
            df_slice = df.iloc[max(0, i-400):i]
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
                
            if ob_mid and ob_high:
                # 2-Level Scale-In (50% OB High, 50% OB Mid)
                sl_price = ob_mid - atr_ * 1.5 if trend == "BULLISH" else ob_mid + atr_ * 1.5
                
                pending_orders.append({
                    "dir": trend,
                    "price": ob_high,
                    "sl": sl_price,
                    "atr": atr_,
                    "wait": 0,
                    "filled": False
                })
                pending_orders.append({
                    "dir": trend,
                    "price": ob_mid,
                    "sl": sl_price,
                    "atr": atr_,
                    "wait": 0,
                    "filled": False
                })

    return trades

def run_orp_portfolio(all_trades, start_cap=100.0, cycle_pct=0.10, rec_factor=1.0, max_risk=0.20, base_risk=0.04):
    all_trades.sort(key=lambda x: x["exit_ts"])
    
    equity = start_cap
    peak_eq = start_cap
    target_eq = start_cap
    step = 0
    eq_curve = [equity]
    
    for t in all_trades:
        while equity >= target_eq:
            step += 1
            target_eq = start_cap * ((1.0 + cycle_pct) ** step)
            
        if equity > peak_eq:
            peak_eq = equity
            
        delta = target_eq - equity
        req_risk = max(equity * base_risk, delta / rec_factor)
        actual_risk = min(req_risk, equity * max_risk)
        
        sl_pct = t["sl_pct"] / 100.0
        if sl_pct <= 0: sl_pct = 0.01
        
        # Max leverage check
        pos_size = actual_risk / sl_pct
        if pos_size > equity * 10.0:
            pos_size = equity * 10.0
            actual_risk = pos_size * sl_pct
            
        equity += actual_risk * t["r_mult"]
        eq_curve.append(equity)
        
        if equity <= 1.0:
            equity = 0.0
            break
            
    eq_arr = np.array(eq_curve)
    peak_arr = np.maximum.accumulate(eq_arr)
    peak_arr = np.where(peak_arr == 0, 1.0, peak_arr)
    dd_arr = (eq_arr - peak_arr) / peak_arr
    max_dd = float(abs(dd_arr.min()) * 100) if len(dd_arr) > 0 else 0
    
    return equity, step, max_dd

def download_data_if_needed():
    import subprocess
    print("Veriler kontrol ediliyor/indiriliyor...")
    # Just a placeholder, assuming user has data or will run download script
    pass

def main():
    print("\n" + "="*80)
    print("  🚀 4H MULTI-COIN PORTFÖY BACKTESTER (20 COİN) — SCALE-IN DCA")
    print("="*80)
    
    all_trades = []
    
    t0 = time.time()
    for i, coin in enumerate(COINS):
        sys.stdout.write(f"\r  [{i+1}/{len(COINS)}] {coin}/USDT taranıyor...")
        sys.stdout.flush()
        
        trades = simulate_coin(coin)
        all_trades.extend(trades)
        
    elapsed = time.time() - t0
    
    print(f"\n\n  ✅ Tarama tamamlandı! ({elapsed:.1f}s)")
    print(f"  📊 Toplam İşlem (Portföy): {len(all_trades)}")
    
    if not all_trades:
        print("İşlem bulunamadı.")
        return
        
    wins = sum(1 for t in all_trades if t["r_mult"] > 0)
    wr = (wins / len(all_trades)) * 100
    avg_r = sum(t["r_mult"] for t in all_trades) / len(all_trades)
    
    print(f"  📈 Win Rate (WR)  : %{wr:.1f}")
    print(f"  📈 Ortalama Getiri : {avg_r:+.2f}R")
    
    print("\n  🧠 ORP BİLEŞİK BÜYÜME SİMÜLASYONU (Dinamik Optimize Parametreler)")
    eq, steps, mdd = run_orp_portfolio(
        all_trades, 
        start_cap=100.0, 
        cycle_pct=0.10, 
        rec_factor=1.0, 
        max_risk=0.20, 
        base_risk=0.04
    )
    
    print(f"     Başlangıç      : $100.00")
    print(f"     Bitiş ($)      : ${eq:,.2f} ({eq/100:.1f}x)")
    print(f"     Tamamlanan Adım: {steps}")
    print(f"     Max Drawdown   : %{mdd:.1f}")
    
    print("\n" + "="*80)

if __name__ == "__main__":
    download_data_if_needed()
    main()
