#!/usr/bin/env python3
"""
SMC TOP-DOWN CONFLUENCE SIMULATOR (1H Macro OB + 15M Structure Break Entry)
═══════════════════════════════════════════════════════════════════════════
Optimized Version:
- SL = 2.0 * ATR (more room to breathe)
- TP1 = 2.0R, TP2 = 4.0R, TP3 = 6.0R (earlier scale-out profit locking)
- Breakout volume filter (vol > 1.1x avg 10-bar vol)
"""
import os, sys, time, math, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

def head(msg): print(f"\n\033[95m\033[1m════════════════════════════════════════════════════════════════════\n  {msg}\n════════════════════════════════════════════════════════════════════\033[0m")
def h2(msg): print(f"\n\033[96m\033[1m─── {msg} ──────────────────────────────────────────────────────────\033[0m")
def ok(msg): return f"\033[92m{msg}\033[0m"
def bad(msg): return f"\033[91m{msg}\033[0m"
def warn(msg): return f"\033[93m{msg}\033[0m"
def dim(msg): return f"\033[90m{msg}\033[0m"

# ═══════════════════════════════════════════════════════════════
#  MATEMATİKSEL İNDİKATÖRLER VE YARDIMCI HESAPLAMALAR
# ═══════════════════════════════════════════════════════════════

def calculate_atr(df, period=14):
    high = df["high"]
    low = df["low"]
    close = df["close"]
    
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    return atr.fillna(method="bfill")

def detect_1h_order_blocks(df, n=3):
    c = df["close"]
    o = df["open"]
    h = df["high"]
    l = df["low"]
    
    bull_obs = []
    bear_obs = []
    
    body_sz = (c - o).abs()
    avg_body = body_sz.rolling(20).mean()
    
    for i in range(20, len(df) - n):
        bar_sz = body_sz.iloc[i]
        avg = avg_body.iloc[i]
        is_impulse = bar_sz > avg * 1.3
        
        if not is_impulse:
            continue
            
        nxt = c.iloc[i+1 : i+1+n]
        if len(nxt) < n:
            continue
            
        # Bullish OB
        if nxt.iloc[-1] > nxt.iloc[0] and c.iloc[i] < o.iloc[i]:
            ob_low = float(l.iloc[i])
            ob_high = float(h.iloc[i])
            
            # Find when this OB is mitigated (close goes below ob_low)
            sliced = df.iloc[i+n:]
            mitigated_bars = sliced[sliced["close"] < ob_low]
            mitigation_ts = mitigated_bars.index[0] if not mitigated_bars.empty else pd.Timestamp("2200-01-01")
            
            bull_obs.append({
                "low": ob_low,
                "high": ob_high,
                "mid": (ob_low + ob_high) / 2,
                "formed_bar_idx": i,
                "ts": df.index[i],
                "mitigation_ts": mitigation_ts
            })
        # Bearish OB
        elif nxt.iloc[-1] < nxt.iloc[0] and c.iloc[i] > o.iloc[i]:
            ob_low = float(l.iloc[i])
            ob_high = float(h.iloc[i])
            
            # Find when this OB is mitigated (close goes above ob_high)
            sliced = df.iloc[i+n:]
            mitigated_bars = sliced[sliced["close"] > ob_high]
            mitigation_ts = mitigated_bars.index[0] if not mitigated_bars.empty else pd.Timestamp("2200-01-01")
            
            bear_obs.append({
                "low": ob_low,
                "high": ob_high,
                "mid": (ob_low + ob_high) / 2,
                "formed_bar_idx": i,
                "ts": df.index[i],
                "mitigation_ts": mitigation_ts
            })
            
    return bull_obs, bear_obs

# ═══════════════════════════════════════════════════════════════
#  ORP MOTORU
# ═══════════════════════════════════════════════════════════════

def calculate_max_dd(equity_curve):
    arr = np.array(equity_curve)
    if len(arr) == 0: return 0.0
    peak = np.maximum.accumulate(arr)
    peak = np.where(peak == 0, 1.0, peak)
    dd = (arr - peak) / peak
    return float(abs(dd.min()) * 100)

def run_orp(trades, start_capital=100.0, target_step_pct=0.05, max_lev_cap=5.0):
    equity = start_capital
    target_step = 0
    target_equity = start_capital
    equity_curve = [start_capital]
    wiped_out = False
    max_lev_used = 1.0
    
    for t in trades:
        if wiped_out:
            equity_curve.append(0.0)
            continue
            
        while equity >= target_equity:
            target_step += 1
            target_equity = start_capital * ((1.0 + target_step_pct) ** target_step)
            
        delta = target_equity - equity
        base_risk = equity * 0.02
        required_risk = max(base_risk, delta / 1.5)
        
        sl_fraction = t["sl_pct"] / 100.0
        if sl_fraction <= 0.0:
            sl_fraction = 0.015
            
        pos_size = required_risk / sl_fraction
        req_lev = pos_size / equity
        
        actual_lev = min(req_lev, max_lev_cap)
        max_lev_used = max(max_lev_used, actual_lev)
        
        actual_pos_size = actual_lev * equity
        actual_risk = actual_pos_size * sl_fraction
        
        if actual_risk > equity * 0.15:
            actual_risk = equity * 0.15
            actual_pos_size = actual_risk / sl_fraction
            actual_lev = actual_pos_size / equity
            
        dollar_pnl = actual_risk * t["r_mult"]
        equity += dollar_pnl
        
        if equity <= 1.0:
            equity = 0.0
            wiped_out = True
            
        equity_curve.append(equity)
        
    if equity <= 0.0:
        steps_achieved = 0
    else:
        steps_achieved = int(math.log(equity / start_capital) / math.log(1.0 + target_step_pct)) if equity > start_capital else 0
        
    return {
        "final_eq": equity,
        "max_drawdown": calculate_max_dd(equity_curve),
        "max_lev_used": max_lev_used,
        "wiped_out": wiped_out,
        "steps_achieved": steps_achieved
    }

# ═══════════════════════════════════════════════════════════════
#  MULTI-TIMEFRAME CONFLUENCE BACKTESTER
# ═══════════════════════════════════════════════════════════════

def run_confluence_backtest(symbol, limit_days=180):
    h1_path = f"data/historical/{symbol}_USDT_1h.csv"
    m15_path = f"data/historical/{symbol}_USDT_15m.csv"
    
    if not os.path.exists(h1_path) or not os.path.exists(m15_path):
        return None
        
    df_1h = pd.read_csv(h1_path)
    df_1h["ts"] = pd.to_datetime(df_1h["ts"])
    df_1h.set_index("ts", inplace=True)
    df_1h = df_1h.sort_index()
    
    df_15m = pd.read_csv(m15_path)
    df_15m["ts"] = pd.to_datetime(df_15m["ts"])
    df_15m.set_index("ts", inplace=True)
    df_15m = df_15m.sort_index()
    
    cutoff_date = df_15m.index[-1] - pd.Timedelta(days=limit_days)
    df_15m = df_15m.loc[df_15m.index >= cutoff_date]
    df_1h = df_1h.loc[df_1h.index >= cutoff_date - pd.Timedelta(days=10)]
    
    print(f"  1H Veri boyutu: {len(df_1h)} bar | 15M Veri boyutu: {len(df_15m)} bar")
    print(f"  Tarih Aralığı: {df_15m.index[0]} → {df_15m.index[-1]}")
    
    bull_obs_1h, bear_obs_1h = detect_1h_order_blocks(df_1h)
    ema_200_1h = df_1h["close"].ewm(span=200, adjust=False).mean()
    atr_15m = calculate_atr(df_15m)
    
    # 15M rolling mean volume to filter breakouts
    vol_mean_15m = df_15m["volume"].rolling(10).mean().fillna(method="bfill")
    
    active_trades = {}
    pending_orders = {}
    trades_log = []
    n_signals = 0
    
    COMMISSION = 0.0004
    SLIPPAGE_MARKET = 0.0010
    SLIPPAGE_LIMIT = 0.0002
    
    total_15m = len(df_15m)
    warmup_15m = 50
    
    for i in range(warmup_15m, total_15m - 1):
        ts_15m = df_15m.index[i]
        
        hi_15m = float(df_15m["high"].iloc[i])
        lo_15m = float(df_15m["low"].iloc[i])
        cl_15m = float(df_15m["close"].iloc[i])
        op_15m = float(df_15m["open"].iloc[i])
        vol_15m = float(df_15m["volume"].iloc[i])
        
        ts_1h_closed = ts_15m.floor("H") - pd.Timedelta(hours=1)
        if ts_1h_closed not in df_1h.index:
            continue
            
        close_1h = float(df_1h.loc[ts_1h_closed, "close"])
        ema_1h = float(ema_200_1h.loc[ts_1h_closed])
        macro_trend = "BULLISH" if close_1h > ema_1h else "BEARISH"
        
        active_bull_obs = [ob for ob in bull_obs_1h if ob["ts"] < ts_1h_closed and ts_1h_closed < ob["mitigation_ts"]]
        active_bear_obs = [ob for ob in bear_obs_1h if ob["ts"] < ts_1h_closed and ts_1h_closed < ob["mitigation_ts"]]
                    
        # Check Exits on Active Trades
        for trade_sym, t in list(active_trades.items()):
            exited = False
            pnl_r = 0.0
            exit_price = 0.0
            
            sl_dist = abs(t["entry"] - t["sl_orig"]) / t["entry"]
            
            if t["trail_active"]:
                if t["direction"] == "LONG":
                    new_trail = cl_15m - t["atr"] * 2.0
                    if new_trail > t["trail_sl"]: t["trail_sl"] = new_trail
                    if lo_15m <= t["trail_sl"]:
                        pnl_r = t["locked_pnl"] + (t["trail_sl"] - t["entry"]) / t["entry"] / sl_dist
                        exit_price = t["trail_sl"]; exited = True
                else:
                    new_trail = cl_15m + t["atr"] * 2.0
                    if new_trail < t["trail_sl"]: t["trail_sl"] = new_trail
                    if hi_15m >= t["trail_sl"]:
                        pnl_r = t["locked_pnl"] + (t["entry"] - t["trail_sl"]) / t["entry"] / sl_dist
                        exit_price = t["trail_sl"]; exited = True
                        
            if not exited:
                if t["direction"] == "LONG":
                    if lo_15m <= t["sl"]:
                        pnl_r = t["locked_pnl"] if t["tp1_hit"] else -1.0
                        exit_price = t["sl"]; exited = True
                    elif hi_15m >= t["tp3"]:
                        pnl_r = t["locked_pnl"] + 0.3 * 6.0 # TP3 scale-out close 30% at 6.0R
                        exit_price = t["tp3"]; exited = True
                    elif not t["tp2_hit"] and hi_15m >= t["tp2"]:
                        t["locked_pnl"] += 0.3 * 4.0 # TP2 scale-out close 30% at 4.0R
                        t["tp2_hit"] = True
                        t["trail_sl"] = max(t["trail_sl"], t["entry"] + t["atr"] * 0.5)
                    elif not t["tp1_hit"] and hi_15m >= t["tp1"]:
                        t["locked_pnl"] += 0.4 * 2.0 # TP1 scale-out close 40% at 2.0R
                        t["tp1_hit"] = True
                        t["sl"] = t["entry"] * 1.001
                        t["trail_active"] = True
                        t["trail_sl"] = t["entry"] - t["atr"] * 2.0
                else:
                    if hi_15m >= t["sl"]:
                        pnl_r = t["locked_pnl"] if t["tp1_hit"] else -1.0
                        exit_price = t["sl"]; exited = True
                    elif lo_15m <= t["tp3"]:
                        pnl_r = t["locked_pnl"] + 0.3 * 6.0
                        exit_price = t["tp3"]; exited = True
                    elif not t["tp2_hit"] and lo_15m <= t["tp2"]:
                        t["locked_pnl"] += 0.3 * 4.0
                        t["tp2_hit"] = True
                        t["trail_sl"] = min(t["trail_sl"], t["entry"] - t["atr"] * 0.5)
                    elif not t["tp1_hit"] and lo_15m <= t["tp1"]:
                        t["locked_pnl"] += 0.4 * 2.0
                        t["tp1_hit"] = True
                        t["sl"] = t["entry"] * 0.999
                        t["trail_active"] = True
                        t["trail_sl"] = t["entry"] + t["atr"] * 2.0
                        
            if exited:
                cost = (COMMISSION * 2) + SLIPPAGE_MARKET + SLIPPAGE_LIMIT
                net_r = pnl_r - cost / sl_dist if sl_dist > 0 else pnl_r
                
                trades_log.append({
                    "symbol": symbol,
                    "direction": t["direction"],
                    "entry_date": t["entry_date"],
                    "exit_date": str(ts_15m)[:16],
                    "r_mult": net_r,
                    "sl_pct": sl_dist * 100
                })
                del active_trades[trade_sym]
                
        # Check Pending Orders
        for trade_sym, p in list(pending_orders.items()):
            p["bars_waited"] += 1
            if p["bars_waited"] > 24:
                del pending_orders[trade_sym]
                continue
                
            filled = False
            if p["direction"] == "LONG" and lo_15m <= p["limit_price"]:
                filled = True
            elif p["direction"] == "SHORT" and hi_15m >= p["limit_price"]:
                filled = True
                
            if filled:
                if len(active_trades) >= 1:
                    del pending_orders[trade_sym]
                    continue
                    
                entry_price = p["limit_price"]
                sl_orig = p["sl"]
                atr = p["atr"]
                
                active_trades[trade_sym] = {
                    "direction": p["direction"],
                    "entry_date": str(ts_15m)[:16],
                    "entry": entry_price,
                    "sl_orig": sl_orig,
                    "sl": sl_orig,
                    "tp1": entry_price + (entry_price - sl_orig) * 2.0 if p["direction"] == "LONG" else entry_price - (sl_orig - entry_price) * 2.0,
                    "tp2": entry_price + (entry_price - sl_orig) * 4.0 if p["direction"] == "LONG" else entry_price - (sl_orig - entry_price) * 4.0,
                    "tp3": entry_price + (entry_price - sl_orig) * 6.0 if p["direction"] == "LONG" else entry_price - (sl_orig - entry_price) * 6.0,
                    "atr": atr,
                    "tp1_hit": False,
                    "tp2_hit": False,
                    "trail_active": False,
                    "trail_sl": 0.0,
                    "locked_pnl": 0.0
                }
                del pending_orders[trade_sym]
                
        # Scan for signals
        if not active_trades and not pending_orders:
            atr_val = float(atr_15m.iloc[i])
            avg_vol = float(vol_mean_15m.iloc[i])
            
            # --- Bullish Bias Setup ---
            is_in_bull_ob = False
            for ob in active_bull_obs:
                if cl_15m <= ob["high"] and cl_15m >= ob["low"] - atr_val:
                    is_in_bull_ob = True
                    break
                    
            if is_in_bull_ob and macro_trend == "BULLISH":
                prev_highs = df_15m["high"].iloc[i-4:i]
                # Breakout check + Volume confirmation
                if cl_15m > prev_highs.max() and vol_15m > avg_vol * 1.1:
                    limit_price = (op_15m + cl_15m) / 2
                    sl_price = lo_15m - atr_val * 2.0 # Wider SL
                    
                    sl_dist = (limit_price - sl_price) / limit_price
                    if 0.003 <= sl_dist <= 0.02:
                        pending_orders[symbol] = {
                            "direction": "LONG",
                            "limit_price": limit_price,
                            "sl": sl_price,
                            "atr": atr_val,
                            "bars_waited": 0
                        }
                        n_signals += 1
                        
            # --- Bearish Bias Setup ---
            is_in_bear_ob = False
            for ob in active_bear_obs:
                if cl_15m >= ob["low"] and cl_15m <= ob["high"] + atr_val:
                    is_in_bear_ob = True
                    break
                    
            if is_in_bear_ob and macro_trend == "BEARISH":
                prev_lows = df_15m["low"].iloc[i-4:i]
                if cl_15m < prev_lows.min() and vol_15m > avg_vol * 1.1:
                    limit_price = (op_15m + cl_15m) / 2
                    sl_price = hi_15m + atr_val * 2.0 # Wider SL
                    
                    sl_dist = (sl_price - limit_price) / limit_price
                    if 0.003 <= sl_dist <= 0.02:
                        pending_orders[symbol] = {
                            "direction": "SHORT",
                            "limit_price": limit_price,
                            "sl": sl_price,
                            "atr": atr_val,
                            "bars_waited": 0
                        }
                        n_signals += 1
                        
    return {"trades": trades_log, "signals": n_signals}

# ═══════════════════════════════════════════════════════════════
#  MAIN RUNNER
# ═══════════════════════════════════════════════════════════════

def main():
    head("SMC MULTI-TIMEFRAME CONFLUENCE BACKTEST (180 GÜN) - OPTİMİZE")
    print("SL: 2.0*ATR | TPs: 2R/4R/6R | Hacim Filtresi: > 1.1x")
    print("Komisyon (%0.04), Slippage (%0.10 market, %0.02 limit) ve 1 bar gecikme dahil.")
    
    test_coins = ["BTC", "ETH", "SOL"]
    
    for coin in test_coins:
        h2(f"{coin}/USDT 1H + 15M Confluence Testi")
        
        t0 = time.time()
        res = run_confluence_backtest(coin, limit_days=180)
        elapsed = time.time() - t0
        
        if not res or not res["trades"]:
            print(f"  {bad('HATA')}: Simülasyon çalıştırılamadı veya işlem üretilmedi.")
            continue
            
        trades = res["trades"]
        n_trades = len(trades)
        
        wins = sum(1 for t in trades if t["r_mult"] > 0)
        win_rate = (wins / n_trades) * 100 if n_trades > 0 else 0
        
        avg_sl = sum(t["sl_pct"] for t in trades) / n_trades
        avg_r = sum(t["r_mult"] for t in trades) / n_trades
        
        # Run ORP compounding
        orp_res = run_orp(trades, start_capital=100.0, target_step_pct=0.05, max_lev_cap=5.0)
        
        print(f"\n  📊 {ok('İŞLEM ÖZETİ')} ({elapsed:.1f}sn):")
        print(f"     Sinyal Sayısı     : {res['signals']}")
        print(f"     Gerçekleşen İşlem  : {n_trades} (Ortalama ayda {n_trades/6:.1f} işlem)")
        print(f"     Kazanma Oranı (WR) : %{win_rate:.1f}")
        print(f"     Ortalama SL        : %{avg_sl:.2f}")
        print(f"     Ortalama R-Getiri  : +{avg_r:.2f}R")
        print(f"     Tamamlanan %5 Adım : {orp_res['steps_achieved']} döngü")
        print(f"     Maksimum Drawdown  : %{orp_res['max_drawdown']:.1f}")
        print(f"     Bitiş Sermayesi    : ${orp_res['final_eq']:,.2f} ({orp_res['final_eq']/100:.2f}x)")
        
if __name__ == "__main__":
    main()
