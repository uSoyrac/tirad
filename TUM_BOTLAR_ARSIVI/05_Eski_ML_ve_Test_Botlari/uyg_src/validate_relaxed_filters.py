#!/usr/bin/env python3
"""
MULTI-COIN VALIDATION OF RELAXED FILTERS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests Config A (Tight), Config D (Score>=3.5 + No Vol), and Config H (Score>=3.0 + All Loose)
across ETH, BTC, SOL (1h timeframe, last 4000 bars)
to ensure consistency and check if looser filters cause liquidation on other pairs.
"""
import os, sys, time, math
import numpy as np
import pandas as pd

from backtest_multi_tf import (
    score_slice_v2, WARMUP, EMA_TREND_PERIOD,
    SL_ATR_MULT, TP1_R, TP2_R, TP3_R, TRAIL_ATR,
    TP1_CLOSE, TP2_CLOSE, TP3_CLOSE, ROUND_TRIP, CAPITAL
)
from simulate_orp import run_orp
from live_scan import B, R, GR, RD, YL, CY, DM, ok, bad, warn, nfo, dim, head, h2
from simulate_filter_fast import simulate_trades

COINS = ["ETH", "BTC", "SOL"]
CONFIGS_TO_TEST = [
    {"name": "A (Tight/Mevcut)", "min_score": 4.5, "require_vol": True,  "require_1d_trend": True,  "sl_range": (0.005, 0.10)},
    {"name": "D (Score>=3.5 + NoVol)", "min_score": 3.5, "require_vol": False, "require_1d_trend": True,  "sl_range": (0.005, 0.10)},
    {"name": "H (Score>=3.0 + Loose)", "min_score": 3.0, "require_vol": False, "require_1d_trend": False, "sl_range": (0.003, 0.12)},
]

def _ema(series, span):
    try:
        return float(series.ewm(span=span, adjust=False).mean().iloc[-1])
    except:
        return float(series.iloc[-1])

def _trend_1d(df_slice):
    cp = float(df_slice["close"].iloc[-1])
    ema_val = _ema(df_slice["close"], EMA_TREND_PERIOD)
    if cp > ema_val: return "BULLISH"
    elif cp < ema_val: return "BEARISH"
    return "NEUTRAL"

def scan_all_signals_limited(symbol, df_full, max_bars=4000):
    """
    Sadece son max_bars barı tarayarak ham sinyal listesi üretir.
    """
    signals = []
    total_bars = len(df_full)
    start_bar = max(WARMUP, total_bars - max_bars)
    print(f"  Taranıyor: son {total_bars - start_bar} bar", end="", flush=True)

    for i in range(start_bar, total_bars - 1):
        if i % 1000 == 0:
            sys.stdout.write(".")
            sys.stdout.flush()

        df_slice = df_full.iloc[max(0, i - 300):i]

        comp, trend, entry_, sl_, atr_, vol_ok_ = score_slice_v2(df_slice)

        if comp < 2.5 or trend == "NEUTRAL" or entry_ is None:
            continue

        trend_1d = _trend_1d(df_slice)
        sl_dist = abs(entry_ - sl_) / entry_ if entry_ > 0 else 0

        signals.append({
            "bar_idx": i,
            "composite": comp,
            "trend": trend,
            "trend_1d": trend_1d,
            "entry": entry_,
            "sl": sl_,
            "atr": atr_,
            "vol_ok": vol_ok_,
            "sl_dist": sl_dist,
            "hi": float(df_full["high"].iloc[i]),
            "lo": float(df_full["low"].iloc[i]),
            "cl": float(df_full["close"].iloc[i]),
            "month": str(df_full.index[i])[:7],
        })

    print(f" {ok('OK')}: {len(signals)} ham sinyal bulundu")
    return signals

def main():
    head("COIN ÇAPRAZ DOĞRULAMA TESTİ (SON 4000 BAR ~6 AY)")
    print("Mevcut vs Gevşetilmiş Filtreleri ETH, BTC ve SOL üzerinde deniyoruz...\n")

    results = []

    for coin in COINS:
        csv_path = f"data/historical/{coin}_USDT_1h.csv"
        if not os.path.exists(csv_path):
            print(f"  {bad('HATA')}: {csv_path} bulunamadı, geçiliyor.")
            continue

        print(f"\n{'-'*60}\n🤖 {coin}/USDT 1h yükleniyor...")
        df = pd.read_csv(csv_path)
        df["ts"] = pd.to_datetime(df["ts"])
        df.set_index("ts", inplace=True)
        df = df.sort_index()

        d0 = str(df.index[-4000])[:10] if len(df) > 4000 else str(df.index[WARMUP])[:10]
        d1 = str(df.index[-1])[:10]
        print(f"  Veri: {len(df)} bar — Tarama aralığı: {d0} → {d1}")

        # Sinyal tara (sadece 1 kez)
        t0 = time.time()
        raw_signals = scan_all_signals_limited(f"{coin}/USDT", df, max_bars=4000)
        scan_time = time.time() - t0
        print(f"  Sinyal tarama süresi: {scan_time:.1f} saniye")

        # Configleri simüle et
        for cfg in CONFIGS_TO_TEST:
            print(f"  Simüle ediliyor: {cfg['name']}... ", end="", flush=True)
            t_sim_0 = time.time()
            trades = simulate_trades(df, raw_signals, cfg, max_leverage_limit=5)
            sim_time = time.time() - t_sim_0

            n_trades = len(trades)
            if n_trades == 0:
                print("0 işlem")
                results.append({
                    "coin": coin, "config": cfg["name"], "trades": 0, "win_rate": 0,
                    "final_eq": 100.0, "steps": 0, "dd": 0, "wiped": False
                })
                continue

            wins = sum(1 for t in trades if "WIN" in t["result"])
            win_rate = (wins / n_trades) * 100
            orp = run_orp(trades, start_capital=100.0, target_step_pct=0.05, max_lev_cap=5.0)

            print(f"{n_trades} işlem | WR: {win_rate:.0f}% | ORP Final: ${orp['final_eq']:,.2f} | DD: {orp['max_drawdown']:.1f}%")

            results.append({
                "coin": coin,
                "config": cfg["name"],
                "trades": n_trades,
                "win_rate": win_rate,
                "final_eq": orp["final_eq"],
                "steps": orp["steps_achieved"],
                "dd": orp["max_drawdown"],
                "wiped": orp["wiped_out"]
            })

    # Sonuçları Tablo Halinde Yazdır
    print("\n\n" + "="*80)
    print("                 GENEL ÇAPRAZ DOĞRULAMA (CROSS-VALIDATION) TABLOSU")
    print("="*80)
    print("| Coin | Filtre Modu | İşlem Sayısı | Win Rate | ORP Bitiş ($) | %5 Adım | Max DD | Battı? |")
    print("|------|-------------|--------------|----------|---------------|---------|--------|--------|")
    for r in results:
        wiped_str = "❌ EVET" if r["wiped"] else "✅ HAYIR"
        eq_str = f"${r['final_eq']:,.2f}"
        print(f"| {r['coin']:4s} | {r['config']:20s} | {r['trades']:12d} | {r['win_rate']:7.1f}% | {eq_str:13s} | {r['steps']:7d} | {r['dd']:5.1f}% | {wiped_str:7s} |")
    print("="*80)

if __name__ == "__main__":
    main()
