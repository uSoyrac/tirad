#!/usr/bin/env python3
"""
SIMPLIFIED DECISION INPUTS TEST (ELIMINATING REDUNDANT INDICATORS)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Investigates if we can reduce the 16 decision inputs down to a few core orthogonal features,
boosting trade frequency while keeping win rate high.
"""
import os, sys, time, math
import numpy as np
import pandas as pd

from backtest_multi_tf import (
    WARMUP, EMA_TREND_PERIOD, SL_ATR_MULT, TP1_R, TP2_R, TP3_R, TRAIL_ATR,
    TP1_CLOSE, TP2_CLOSE, TP3_CLOSE, ROUND_TRIP, CAPITAL, _atr
)
from simulate_orp import run_orp
from live_scan import (
    market_structure, order_blocks, fair_value_gaps, liquidity_map,
    classic_indicators, cvd, ok, bad, warn, head, h2
)

COINS = ["ETH", "BTC", "SOL"]

def _ema(series, span):
    try:
        return float(series.ewm(span=span, adjust=False).mean().iloc[-1])
    except:
        return float(series.iloc[-1])

def _trend_1d(df_slice):
    cp = float(df_slice["close"].iloc[-1])
    ema_val = _ema(df_slice["close"], EMA_TREND_PERIOD)
    return "BULLISH" if cp > ema_val else "BEARISH"

def scan_raw_components(symbol, df_full, max_bars=4000):
    """
    Tüm gösterge ve SMC bileşenlerini bir kez hesaplayıp ham veri seti döndürür.
    """
    signals = []
    total_bars = len(df_full)
    start_bar = max(WARMUP, total_bars - max_bars)
    print(f"  Taranıyor: {total_bars - start_bar} bar", end="", flush=True)

    for i in range(start_bar, total_bars - 1):
        if i % 1000 == 0:
            sys.stdout.write(".")
            sys.stdout.flush()

        df_slice = df_full.iloc[max(0, i - 300):i]
        cp = float(df_slice["close"].iloc[-1])

        # 1. SMC Bileşenleri
        try:
            ms_r = market_structure(df_slice, 10)
            bull_obs, bear_obs, _, _ = order_blocks(df_slice)
            _, _, sweep_up, sweep_dn = liquidity_map(df_slice)
            cl = classic_indicators(df_slice)
            cvd_up = cvd(df_slice)
            atr_val = _atr(df_slice)
        except:
            continue

        trend_1d = _trend_1d(df_slice)

        signals.append({
            "bar_idx": i,
            "cp": cp,
            "hi": float(df_full["high"].iloc[i]),
            "lo": float(df_full["low"].iloc[i]),
            "cl_val": float(df_full["close"].iloc[i]),
            "month": str(df_full.index[i])[:7],
            # SMC indicators
            "trend": ms_r["trend"],
            "trend_1d": trend_1d,
            "bull_obs": bull_obs,
            "bear_obs": bear_obs,
            "sweep_dn": sweep_dn,
            "sweep_up": sweep_up,
            # Classic
            "macd_bull": cl["macd_bull"],
            "macd_bear": cl["macd_hist"] < 0,
            "macd_hist": cl["macd_hist"],
            "e8": cl["e8"], "e21": cl["e21"], "e55": cl["e55"],
            # CVD
            "cvd_up": cvd_up,
            "atr": atr_val,
        })

    print(f" {ok('OK')}: {len(signals)} bar tarandı.")
    return signals

def simulate_pruned_setup(df_full, signals, setup_name):
    """
    Sadece belirlenen kurallara göre işlem açar. Diğer tüm filtreleri eler.
    """
    trades = []
    equity = [CAPITAL]
    in_trade = False
    t_dir = ""; t_entry = t_sl = t_sl_original = 0.0
    t_tp1 = t_tp2 = t_tp3 = t_atr = 0.0
    t_entry_bar = 0; t_month = ""
    t_tp1_hit = t_tp2_hit = t_trail_active = False
    t_trail_sl = t_locked_pnl = 0.0
    t_remaining_qty = 1.0
    t_leverage = 1.0; t_liq_dist = 1.0; t_liquidated = False

    sig_map = {s["bar_idx"]: s for s in signals}
    total_bars = len(df_full)

    for i in range(WARMUP, total_bars - 1):
        hi = float(df_full["high"].iloc[i])
        lo = float(df_full["low"].iloc[i])
        cl = float(df_full["close"].iloc[i])

        if in_trade:
            # Standart ORP Exit Mantığı
            exited = False; pnl_r = 0.0; exit_result = ""; exit_price = 0.0
            sl_dist_t = abs(t_entry - t_sl_original) / t_entry

            if t_trail_active:
                if t_dir == "LONG":
                    new_trail = cl - t_atr * TRAIL_ATR
                    if new_trail > t_trail_sl: t_trail_sl = new_trail
                    if lo <= t_trail_sl:
                        pnl_r = t_locked_pnl + (t_trail_sl - t_entry) / t_entry / sl_dist_t
                        exit_result = "WIN_TRAIL"; exit_price = t_trail_sl; exited = True
                else:
                    new_trail = cl + t_atr * TRAIL_ATR
                    if new_trail < t_trail_sl: t_trail_sl = new_trail
                    if hi >= t_trail_sl:
                        pnl_r = t_locked_pnl + (t_entry - t_trail_sl) / t_entry / sl_dist_t
                        exit_result = "WIN_TRAIL"; exit_price = t_trail_sl; exited = True

            if not exited:
                if t_dir == "LONG":
                    if lo <= t_sl:
                        pnl_r = t_locked_pnl if t_tp1_hit else -1.0
                        exit_result = "WIN_BREAKEVEN" if t_tp1_hit else "LOSS"
                        exit_price = t_sl; exited = True
                    elif hi >= t_tp3:
                        pnl_r = t_locked_pnl + TP3_CLOSE * TP3_R; exit_result = "WIN_TP3"
                        exit_price = t_tp3; exited = True
                    elif not t_tp2_hit and hi >= t_tp2:
                        t_locked_pnl += TP2_CLOSE * TP2_R; t_tp2_hit = True
                        t_remaining_qty -= TP2_CLOSE
                        t_trail_sl = max(t_trail_sl, t_entry + t_atr * 0.5)
                    elif not t_tp1_hit and hi >= t_tp1:
                        t_locked_pnl += TP1_CLOSE * TP1_R; t_tp1_hit = True
                        t_remaining_qty -= TP1_CLOSE
                        t_sl = t_entry * 1.001; t_trail_active = True
                        t_trail_sl = t_entry - t_atr * TRAIL_ATR
                else:
                    if hi >= t_sl:
                        pnl_r = t_locked_pnl if t_tp1_hit else -1.0
                        exit_result = "WIN_BREAKEVEN" if t_tp1_hit else "LOSS"
                        exit_price = t_sl; exited = True
                    elif lo <= t_tp3:
                        pnl_r = t_locked_pnl + TP3_CLOSE * TP3_R; exit_result = "WIN_TP3"
                        exit_price = t_tp3; exited = True
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
                net_r = pnl_r - ROUND_TRIP / sl_dist_t if sl_dist_t > 0 else pnl_r
                dollar_pnl = equity[-1] * 0.02 * net_r
                new_eq = equity[-1] + dollar_pnl
                equity.append(new_eq)
                trades.append({
                    "result": exit_result,
                    "r_mult": round(net_r, 3),
                    "equity": new_eq,
                    "sl_pct": sl_dist_t * 100.0,
                })
                in_trade = t_tp1_hit = t_tp2_hit = t_trail_active = False
                t_locked_pnl = 0.0; t_remaining_qty = 1.0
            continue

        sig = sig_map.get(i)
        if sig is None:
            continue

        # ── KURALLARI TEST ET ──
        trigger_long = False
        trigger_short = False

        trend = sig["trend"]
        trend_1d = sig["trend_1d"]
        bull_obs = sig["bull_obs"]
        bear_obs = sig["bear_obs"]
        sweep_dn = sig["sweep_dn"]
        sweep_up = sig["sweep_up"]
        macd_bull = sig["macd_bull"]
        macd_bear = sig["macd_bear"]
        cvd_up = sig["cvd_up"]
        cp = sig["cp"]
        atr_val = sig["atr"]

        # EMA Trend Proxy
        ema_trend = "NEUTRAL"
        if sig["e8"] > sig["e21"] > sig["e55"]: ema_trend = "BULLISH"
        elif sig["e8"] < sig["e21"] < sig["e55"]: ema_trend = "BEARISH"
        eff_trend = trend if trend != "NEUTRAL" else ema_trend

        # Setup Tanımları
        if setup_name == "S1_Pure_SMC":
            # Kural: Sadece 1D Trend Yönünde ve OB veya Sweep varsa gir
            if trend_1d == "BULLISH" and eff_trend == "BULLISH" and (bull_obs or sweep_dn):
                trigger_long = True
            elif trend_1d == "BEARISH" and eff_trend == "BEARISH" and (bear_obs or sweep_up):
                trigger_short = True

        elif setup_name == "S2_SMC_Momentum":
            # Kural: 1D Trend + OB/Sweep + MACD Onayı (3 Girdi)
            if trend_1d == "BULLISH" and eff_trend == "BULLISH" and (bull_obs or sweep_dn) and macd_bull:
                trigger_long = True
            elif trend_1d == "BEARISH" and eff_trend == "BEARISH" and (bear_obs or sweep_up) and macd_bear:
                trigger_short = True

        elif setup_name == "S3_Trend_OB_Only":
            # Kural: En sade model. 1D Trend Yönünde lokal taze OB (2 Girdi)
            if trend_1d == "BULLISH" and bull_obs:
                trigger_long = True
            elif trend_1d == "BEARISH" and bear_obs:
                trigger_short = True

        elif setup_name == "S4_Trend_Sweep_CVD":
            # Kural: Likidite süpürülmesi (Sweep) + CVD Hacim Uyumsuzluğu (3 Girdi)
            if trend_1d == "BULLISH" and sweep_dn and cvd_up:
                trigger_long = True
            elif trend_1d == "BEARISH" and sweep_up and not cvd_up:
                trigger_short = True

        if not (trigger_long or trigger_short):
            continue

        # Pozisyon Bilgileri Belirleme
        entry_price = cp
        if trigger_long:
            if bull_obs: entry_price = (bull_obs[0]["low"] + bull_obs[0]["high"]) / 2
            sl_price = entry_price - atr_val * SL_ATR_MULT
            if bull_obs: sl_price = min(sl_price, bull_obs[0]["low"] * 0.998)
            tp_mult = 1.0
            direction = "LONG"
        else:
            if bear_obs: entry_price = (bear_obs[0]["low"] + bear_obs[0]["high"]) / 2
            sl_price = entry_price + atr_val * SL_ATR_MULT
            if bear_obs: sl_price = max(sl_price, bear_obs[0]["high"] * 1.002)
            tp_mult = -1.0
            direction = "SHORT"

        sl_dist = abs(entry_price - sl_price) / entry_price
        if not (0.005 <= sl_dist <= 0.10): # Standart stop mesafesi kuralı
            continue

        # TP Noktaları
        tp1_ = entry_price + entry_price * sl_dist * TP1_R * tp_mult
        tp2_ = entry_price + entry_price * sl_dist * TP2_R * tp_mult
        tp3_ = entry_price + entry_price * sl_dist * TP3_R * tp_mult

        t_entry = entry_price; t_sl = sl_price; t_sl_original = sl_price
        t_tp1 = tp1_; t_tp2 = tp2_; t_tp3 = tp3_
        t_atr = atr_val; t_dir = direction
        t_entry_bar = i; t_month = sig["month"]
        t_tp1_hit = t_tp2_hit = t_trail_active = False
        t_trail_sl = t_locked_pnl = 0.0
        t_remaining_qty = 1.0
        t_leverage = max(1, min(math.ceil(0.02 / sl_dist), 5)) # 5x Cap
        in_trade = True

    return trades

def main():
    head("KARAR GİRDİSİ ARINDIRMA (FEATURE ABLATION) TESTİ")
    print("16 indikatörü eleyerek, sadece 2-3 temel girdiyle sistemin performansını test ediyoruz...\n")

    setups = ["S1_Pure_SMC", "S2_SMC_Momentum", "S3_Trend_OB_Only", "S4_Trend_Sweep_CVD"]

    results = []

    for coin in COINS:
        csv_path = f"data/historical/{coin}_USDT_1h.csv"
        if not os.path.exists(csv_path):
            continue

        print(f"\n{'-'*60}\n🤖 {coin}/USDT 1h yükleniyor...")
        df = pd.read_csv(csv_path)
        df["ts"] = pd.to_datetime(df["ts"])
        df.set_index("ts", inplace=True)
        df = df.sort_index()

        # Son 4000 barı tarayıp ham verileri çıkarıyoruz
        raw_components = scan_raw_components(coin, df, max_bars=4000)

        for setup in setups:
            print(f"  Test ediliyor: {setup}... ", end="", flush=True)
            trades = simulate_pruned_setup(df, raw_components, setup)
            n_trades = len(trades)

            if n_trades == 0:
                print("0 işlem")
                continue

            wins = sum(1 for t in trades if "WIN" in t["result"])
            win_rate = (wins / n_trades) * 100
            orp = run_orp(trades, start_capital=100.0, target_step_pct=0.05, max_lev_cap=5.0)

            print(f"{n_trades} işlem | WR: {win_rate:.0f}% | ORP Final: ${orp['final_eq']:,.2f} | DD: {orp['max_drawdown']:.1f}%")

            results.append({
                "coin": coin, "setup": setup, "trades": n_trades, "win_rate": win_rate,
                "final_eq": orp["final_eq"], "steps": orp["steps_achieved"], "dd": orp["max_drawdown"],
                "wiped": orp["wiped_out"]
            })

    # Genel Sonuç Tablosu
    print("\n\n" + "="*85)
    print("                     ARINDIRILMIŞ SADECE EN DEĞERLİ GİRDİLER TABLOSU")
    print("="*85)
    print("| Coin | Karar Modeli (Girdiler)   | İşlem | Win Rate | ORP Bitiş ($) | %5 Adım | Max DD |")
    print("|------|---------------------------|-------|----------|---------------|---------|--------|")
    for r in results:
        eq_str = f"${r['final_eq']:,.2f}"
        print(f"| {r['coin']:4s} | {r['setup']:25s} | {r['trades']:5d} | {r['win_rate']:7.1f}% | {eq_str:13s} | {r['steps']:7d} | {r['dd']:5.1f}% |")
    print("="*85)

if __name__ == "__main__":
    main()
