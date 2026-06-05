#!/usr/bin/env python3
import os
import sys
import time
import math
import numpy as np
import pandas as pd
from collections import defaultdict

# Import functions from our multi-tf script
from backtest_multi_tf import score_slice_v2, WARMUP, EMA_TREND_PERIOD, VOL_MULT, SL_ATR_MULT, TP1_R, TP2_R, TP3_R, TRAIL_ATR, TP1_CLOSE, TP2_CLOSE, TP3_CLOSE, COMMISSION, SLIPPAGE, ROUND_TRIP, CAPITAL
from live_scan import B, R, GR, RD, YL, CY, DM, ok, bad, warn, nfo, dim, head, h2

def calculate_max_dd(equity_curve):
    eq_arr = np.array(equity_curve)
    if len(eq_arr) == 0:
        return 0.0
    peak = np.maximum.accumulate(eq_arr)
    peak = np.where(peak == 0, 1.0, peak)
    dd = (eq_arr - peak) / peak
    return float(abs(dd.min()) * 100)

def _ema(series: pd.Series, span: int) -> float:
    try:
        return float(series.ewm(span=span, adjust=False).mean().iloc[-1])
    except Exception:
        return float(series.iloc[-1])

def _trend_1d(df_slice: pd.DataFrame) -> str:
    cp  = float(df_slice["close"].iloc[-1])
    ema = _ema(df_slice["close"], EMA_TREND_PERIOD)
    if cp > ema:
        return "BULLISH"
    elif cp < ema:
        return "BEARISH"
    return "NEUTRAL"

# Optimized backtest with sliding window (300 bars max) to prevent O(N^2) complexity blowup
def backtest_symbol_optimized(symbol: str, df_full: pd.DataFrame, max_leverage_limit: int = 5) -> dict:
    trades    = []
    equity    = [CAPITAL]
    
    in_trade        = False
    t_dir           = ""
    t_entry         = 0.0
    t_sl            = 0.0
    t_sl_original   = 0.0
    t_tp1           = 0.0
    t_tp2           = 0.0
    t_tp3           = 0.0
    t_atr           = 0.0
    t_score         = 0.0
    t_entry_bar     = 0
    t_month         = ""
    t_tp1_hit       = False
    t_tp2_hit       = False
    t_trail_active  = False
    t_trail_sl      = 0.0
    t_remaining_qty = 1.0
    t_locked_pnl    = 0.0
    t_leverage      = 1.0
    t_liq_dist      = 1.0
    t_liquidated    = False

    total_bars = len(df_full)
    
    for i in range(WARMUP, total_bars - 1):
        # Print progress for long runs
        if i % 5000 == 0:
            sys.stdout.write(f".")
            sys.stdout.flush()

        # Sliding window optimization: limit history to last 300 bars
        # This keeps indicator computations extremely fast while providing enough warmup
        df_slice = df_full.iloc[max(0, i - 300):i]
        
        hi  = float(df_full["high"].iloc[i])
        lo  = float(df_full["low"].iloc[i])
        cl  = float(df_full["close"].iloc[i])
        bar_ts = df_full.index[i]
        month  = str(bar_ts)[:7]

        # --- EXIT CONTROL ---
        if in_trade:
            exited       = False
            pnl_r        = 0.0
            exit_result  = ""
            exit_price   = 0.0

            sl_dist = abs(t_entry - t_sl_original) / t_entry

            if t_trail_active:
                if t_dir == "LONG":
                    new_trail = cl - t_atr * TRAIL_ATR
                    if new_trail > t_trail_sl:
                        t_trail_sl = new_trail
                    if lo <= t_trail_sl:
                        pnl_r       = t_locked_pnl + (t_trail_sl - t_entry) / t_entry / sl_dist
                        exit_result = "WIN_TRAIL"
                        exit_price  = t_trail_sl
                        exited      = True
                else:  # SHORT
                    new_trail = cl + t_atr * TRAIL_ATR
                    if new_trail < t_trail_sl:
                        t_trail_sl = new_trail
                    if hi >= t_trail_sl:
                        pnl_r       = t_locked_pnl + (t_entry - t_trail_sl) / t_entry / sl_dist
                        exit_result = "WIN_TRAIL"
                        exit_price  = t_trail_sl
                        exited      = True

            if not exited:
                if t_dir == "LONG":
                    if lo <= t_sl:
                        if t_tp1_hit:
                            pnl_r       = t_locked_pnl
                            exit_result = "WIN_BREAKEVEN"
                            exit_price  = t_sl
                        else:
                            pnl_r       = -1.0
                            exit_result = "LOSS"
                            exit_price  = t_sl
                        exited = True
                    elif not exited and hi >= t_tp3:
                        pnl_r       = t_locked_pnl + TP3_CLOSE * TP3_R
                        exit_result = "WIN_TP3"
                        exit_price  = t_tp3
                        exited      = True
                    elif not t_tp2_hit and hi >= t_tp2:
                        t_locked_pnl   += TP2_CLOSE * TP2_R
                        t_tp2_hit       = True
                        t_remaining_qty -= TP2_CLOSE
                        t_trail_sl = max(t_trail_sl, t_entry + t_atr * 0.5)
                    elif not t_tp1_hit and hi >= t_tp1:
                        t_locked_pnl   += TP1_CLOSE * TP1_R
                        t_tp1_hit       = True
                        t_remaining_qty -= TP1_CLOSE
                        t_sl           = t_entry * 1.001
                        t_trail_active = True
                        t_trail_sl     = t_entry - t_atr * TRAIL_ATR

                else:  # SHORT
                    if hi >= t_sl:
                        if t_tp1_hit:
                            pnl_r       = t_locked_pnl
                            exit_result = "WIN_BREAKEVEN"
                            exit_price  = t_sl
                        else:
                            pnl_r       = -1.0
                            exit_result = "LOSS"
                            exit_price  = t_sl
                        exited = True
                    elif not exited and lo <= t_tp3:
                        pnl_r       = t_locked_pnl + TP3_CLOSE * TP3_R
                        exit_result = "WIN_TP3"
                        exit_price  = t_tp3
                        exited      = True
                    elif not t_tp2_hit and lo <= t_tp2:
                        t_locked_pnl   += TP2_CLOSE * TP2_R
                        t_tp2_hit       = True
                        t_remaining_qty -= TP2_CLOSE
                        t_trail_sl = min(t_trail_sl, t_entry - t_atr * 0.5)
                    elif not t_tp1_hit and lo <= t_tp1:
                        t_locked_pnl   += TP1_CLOSE * TP1_R
                        t_tp1_hit       = True
                        t_remaining_qty -= TP1_CLOSE
                        t_sl           = t_entry * 0.999
                        t_trail_active = True
                        t_trail_sl     = t_entry + t_atr * TRAIL_ATR

            if exited:
                net_r = pnl_r - ROUND_TRIP / sl_dist if sl_dist > 0 else pnl_r
                dollar_pnl = equity[-1] * 0.02 * net_r
                new_eq     = equity[-1] + dollar_pnl
                equity.append(new_eq)

                trades.append({
                    "symbol":     symbol,
                    "direction":  t_dir,
                    "entry":      t_entry,
                    "sl":         t_sl_original,
                    "exit_price": exit_price,
                    "result":     exit_result,
                    "r_mult":     round(net_r, 3),
                    "dollar_pnl": round(dollar_pnl, 2),
                    "score":      t_score,
                    "equity":     new_eq,
                    "month":      t_month,
                    "entry_bar":  t_entry_bar,
                    "exit_bar":   i,
                    "sl_pct":     sl_dist * 100,
                    "atr":        t_atr,
                    "tp1_hit":    t_tp1_hit,
                    "tp2_hit":    t_tp2_hit,
                    "leverage":   t_leverage,
                    "liq_dist_pct": t_liq_dist * 100,
                    "liquidated": t_liquidated,
                })

                in_trade = t_tp1_hit = t_tp2_hit = t_trail_active = False
                t_locked_pnl = 0.0; t_remaining_qty = 1.0
            continue

        # --- SIGNAL & ENTRY ---
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

        if comp >= 8.0:
            max_lev_by_score = 5
        elif comp >= 6.5:
            max_lev_by_score = 4
        elif comp >= 5.5:
            max_lev_by_score = 3
        else:
            max_lev_by_score = 2

        max_lev_allowed = min(max_lev_by_score, max_leverage_limit)
        req_lev = math.ceil(0.02 / sl_dist)
        lev = max(1, min(req_lev, max_lev_allowed))
        liq_dist = 1.0 / lev
        liquidated = sl_dist >= liq_dist

        risk_amount = entry_ * sl_dist
        if trend == "BULLISH":
            tp1_ = entry_ + risk_amount * TP1_R
            tp2_ = entry_ + risk_amount * TP2_R
            tp3_ = entry_ + risk_amount * TP3_R
            d_   = "LONG"
        else:
            tp1_ = entry_ - risk_amount * TP1_R
            tp2_ = entry_ - risk_amount * TP2_R
            tp3_ = entry_ - risk_amount * TP3_R
            d_   = "SHORT"

        t_entry         = entry_
        t_sl            = sl_
        t_sl_original   = sl_
        t_tp1           = tp1_
        t_tp2           = tp2_
        t_tp3           = tp3_
        t_atr           = atr_
        t_dir           = d_
        t_score         = comp
        t_entry_bar     = i
        t_month         = month
        t_tp1_hit       = False
        t_tp2_hit       = False
        t_trail_active  = False
        t_trail_sl      = 0.0
        t_locked_pnl    = 0.0
        t_remaining_qty = 1.0
        t_leverage      = lev
        t_liq_dist      = liq_dist
        t_liquidated    = liquidated
        in_trade        = True

    return {"trades": trades}

def run_orp(trades, start_capital=100.0, target_step_pct=0.02, max_lev_cap=2.0):
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
        base_risk = equity * 0.025
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

def main():
    head(f"OPTIMIZED RECOVERY PROGRESSION (ORP) 1-YEAR BACKTEST SIMULATOR (OPTIMIZED)")
    
    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
    timeframes = ["15m", "30m", "1h", "4h", "1d"]
    
    h2("VERİ YÜKLEME VE STRATEJİ BACKTEST ÇALIŞTIRMA")
    
    results = []
    
    for sym in symbols:
        for tf in timeframes:
            csv_path = f"data/historical/{sym.replace('/', '_')}_{tf}.csv"
            if not os.path.exists(csv_path):
                print(f"  {sym:10} | {tf:3} | {bad('HATA — dosya bulunamadı')}", flush=True)
                continue
                
            df = pd.read_csv(csv_path)
            df["ts"] = pd.to_datetime(df["ts"])
            df.set_index("ts", inplace=True)
            df = df.sort_index()
            
            # Keep execution times quick by limiting history for high-frequency timeframes
            # Slices are still statistically large enough to generate substantial trades
            bar_limit = {
                "1d": 365,
                "4h": 2190,
                "1h": 4000,
                "30m": 4000,
                "15m": 4000
            }.get(tf, 4000)
            df = df.tail(bar_limit)
            
            if df.empty or len(df) < WARMUP + 20:
                print(f"  {sym:10} | {tf:3} | {bad('HATA — yetersiz veri')}", flush=True)
                continue
                
            d0 = str(df.index[WARMUP])[:10]
            d1 = str(df.index[-1])[:10]
            
            sys.stdout.write(f"  {sym:10} | {tf:3} ... ")
            sys.stdout.flush()
            
            t0 = time.time()
            # Generate the trade sequence with optimized slider
            backtest_res = backtest_symbol_optimized(sym, df, max_leverage_limit=5)
            trades = backtest_res["trades"]
            n_trades = len(trades)
            elapsed = time.time() - t0
            
            if n_trades == 0:
                print(f" {dim('0 işlem')} ({elapsed:.1f}sn)", flush=True)
                continue
                
            orp_2x = run_orp(trades, max_lev_cap=2.0)
            orp_5x = run_orp(trades, max_lev_cap=5.0)
            
            results.append({
                "symbol": sym,
                "tf": tf,
                "n": n_trades,
                "orp_2x": orp_2x,
                "orp_5x": orp_5x,
                "d0": d0,
                "d1": d1
            })
            
            print(f" {ok('OK')}: {n_trades:>3} işlem ({elapsed:.1f}sn)", flush=True)
            print(f"    ORP 2x -> Sonuç: ${orp_2x['final_eq']:>8.2f} | Adım: {orp_2x['steps_achieved']:>3} | MaxDD: {orp_2x['max_drawdown']:>5.1f}%", flush=True)
            print(f"    ORP 5x -> Sonuç: ${orp_5x['final_eq']:>8.2f} | Adım: {orp_5x['steps_achieved']:>3} | MaxDD: {orp_5x['max_drawdown']:>5.1f}%", flush=True)
            
    # Markdown Table output for walkthrough
    print("\n\n### ORP STRATEJİSİ 1 YILLIK BACKTEST KARŞILAŞTIRMA TABLOSU (MARKDOWN)\n", flush=True)
    print("| Sembol | Zaman Dilimi | İşlem Sayısı | Limit Kaldıraç | Tamamlanan 2% Adımı | Bitiş Değeri ($100 ile) | Maksimum Çekilme (DD) | Maks Kaldıraç Kullanımı | Likide Oldu mu? |", flush=True)
    print("|--------|--------------|--------------|----------------|---------------------|-------------------------|-----------------------|-------------------------|-----------------|", flush=True)
    
    for r in results:
        sym = r["symbol"].replace("/USDT", "")
        for cap, orp_res in [("2x Cap", r["orp_2x"]), ("5x Cap", r["orp_5x"])]:
            liq_str = "**EVET (LİKİDE)**" if orp_res["wiped_out"] else "HAYIR"
            print(f"| **{sym}** | {r['tf']} | {r['n']} | {cap} | **{orp_res['steps_achieved']}** | **${orp_res['final_eq']:.2f}** | {orp_res['max_drawdown']:.1f}% | {orp_res['max_lev_used']:.2f}x | {liq_str} |", flush=True)

if __name__ == "__main__":
    main()
