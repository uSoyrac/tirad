#!/usr/bin/env python3
"""
FILTER SWEEP SIMULATOR
━━━━━━━━━━━━━━━━━━━━━━
Farklı filtre konfigürasyonlarını test ederek,
"daha çok işlem + yüksek doğruluk" dengesini bulur.
Her konfigürasyon ORP %5 stratejisi ile değerlendirilir.
"""
import os, sys, time, math
import numpy as np
import pandas as pd
from collections import defaultdict

from backtest_multi_tf import (
    score_slice_v2, WARMUP, EMA_TREND_PERIOD, VOL_MULT,
    SL_ATR_MULT, TP1_R, TP2_R, TP3_R, TRAIL_ATR,
    TP1_CLOSE, TP2_CLOSE, TP3_CLOSE, COMMISSION, SLIPPAGE, ROUND_TRIP, CAPITAL
)
from simulate_orp import run_orp, calculate_max_dd
from live_scan import B, R, GR, RD, YL, CY, DM, ok, bad, warn, nfo, dim, head, h2

# ═══════════════════════════════════════════════════════════════
#  KONFIGÜRASYONLAR
# ═══════════════════════════════════════════════════════════════

CONFIGS = [
    {
        "name": "A — Mevcut (Sıkı)",
        "min_score": 4.5,
        "require_vol": True,
        "require_1d_trend": True,
        "sl_range": (0.005, 0.10),
    },
    {
        "name": "B — Score 3.5",
        "min_score": 3.5,
        "require_vol": True,
        "require_1d_trend": True,
        "sl_range": (0.005, 0.10),
    },
    {
        "name": "C — Hacim Kapalı",
        "min_score": 4.5,
        "require_vol": False,
        "require_1d_trend": True,
        "sl_range": (0.005, 0.10),
    },
    {
        "name": "D — Score 3.5 + Hacim Kapalı",
        "min_score": 3.5,
        "require_vol": False,
        "require_1d_trend": True,
        "sl_range": (0.005, 0.10),
    },
    {
        "name": "E — Score 3.0 + Hacim&1D Kapalı",
        "min_score": 3.0,
        "require_vol": False,
        "require_1d_trend": False,
        "sl_range": (0.005, 0.10),
    },
    {
        "name": "F — Score 3.5 + Hacim&1D Kapalı",
        "min_score": 3.5,
        "require_vol": False,
        "require_1d_trend": False,
        "sl_range": (0.005, 0.10),
    },
    {
        "name": "G — Score 4.0 + Hacim Kapalı",
        "min_score": 4.0,
        "require_vol": False,
        "require_1d_trend": True,
        "sl_range": (0.005, 0.10),
    },
    {
        "name": "H — Score 3.0 + Tüm Filtreler Kapalı",
        "min_score": 3.0,
        "require_vol": False,
        "require_1d_trend": False,
        "sl_range": (0.003, 0.12),   # SL aralığı da gevşetildi
    },
]


# ═══════════════════════════════════════════════════════════════
#  PARAMETRELI BACKTEST FONKSİYONU
# ═══════════════════════════════════════════════════════════════

def _ema(series, span):
    try:
        return float(series.ewm(span=span, adjust=False).mean().iloc[-1])
    except:
        return float(series.iloc[-1])

def _trend_1d(df_slice):
    cp  = float(df_slice["close"].iloc[-1])
    ema_val = _ema(df_slice["close"], EMA_TREND_PERIOD)
    if cp > ema_val: return "BULLISH"
    elif cp < ema_val: return "BEARISH"
    return "NEUTRAL"


def backtest_with_config(symbol, df_full, config, max_leverage_limit=5):
    """
    Parametreli backtest: config dict'ine göre filtreleri açar/kapar.
    """
    min_score = config["min_score"]
    require_vol = config["require_vol"]
    require_1d_trend = config["require_1d_trend"]
    sl_min, sl_max = config["sl_range"]

    trades = []
    equity = [CAPITAL]

    in_trade = False
    t_dir = t_entry = t_sl = t_sl_original = 0.0
    t_tp1 = t_tp2 = t_tp3 = t_atr = t_score = 0.0
    t_entry_bar = 0
    t_month = ""
    t_tp1_hit = t_tp2_hit = t_trail_active = False
    t_trail_sl = t_locked_pnl = 0.0
    t_remaining_qty = 1.0
    t_leverage = 1.0
    t_liq_dist = 1.0
    t_liquidated = False

    total_bars = len(df_full)
    signals_seen = 0    # Kaç sinyal değerlendirdik
    signals_passed = 0  # Kaçı filtrelerden geçti

    for i in range(WARMUP, total_bars - 1):
        if i % 5000 == 0:
            sys.stdout.write(".")
            sys.stdout.flush()

        df_slice = df_full.iloc[max(0, i - 300):i]

        hi  = float(df_full["high"].iloc[i])
        lo  = float(df_full["low"].iloc[i])
        cl  = float(df_full["close"].iloc[i])
        bar_ts = df_full.index[i]
        month  = str(bar_ts)[:7]

        # ── EXIT ──
        if in_trade:
            exited = False
            pnl_r = 0.0
            exit_result = ""
            exit_price = 0.0
            sl_dist = abs(t_entry - t_sl_original) / t_entry

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
                        if t_tp1_hit:
                            pnl_r = t_locked_pnl; exit_result = "WIN_BREAKEVEN"
                        else:
                            pnl_r = -1.0; exit_result = "LOSS"
                        exit_price = t_sl; exited = True
                    elif hi >= t_tp3:
                        pnl_r = t_locked_pnl + TP3_CLOSE * TP3_R
                        exit_result = "WIN_TP3"; exit_price = t_tp3; exited = True
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
                        if t_tp1_hit:
                            pnl_r = t_locked_pnl; exit_result = "WIN_BREAKEVEN"
                        else:
                            pnl_r = -1.0; exit_result = "LOSS"
                        exit_price = t_sl; exited = True
                    elif lo <= t_tp3:
                        pnl_r = t_locked_pnl + TP3_CLOSE * TP3_R
                        exit_result = "WIN_TP3"; exit_price = t_tp3; exited = True
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
                net_r = pnl_r - ROUND_TRIP / sl_dist if sl_dist > 0 else pnl_r
                dollar_pnl = equity[-1] * 0.02 * net_r
                new_eq = equity[-1] + dollar_pnl
                equity.append(new_eq)

                trades.append({
                    "symbol": symbol, "direction": t_dir,
                    "entry": t_entry, "sl": t_sl_original,
                    "exit_price": exit_price, "result": exit_result,
                    "r_mult": round(net_r, 3), "dollar_pnl": round(dollar_pnl, 2),
                    "score": t_score, "equity": new_eq, "month": t_month,
                    "entry_bar": t_entry_bar, "exit_bar": i,
                    "sl_pct": sl_dist * 100, "atr": t_atr,
                    "tp1_hit": t_tp1_hit, "tp2_hit": t_tp2_hit,
                    "leverage": t_leverage,
                    "liq_dist_pct": t_liq_dist * 100, "liquidated": t_liquidated,
                })
                in_trade = t_tp1_hit = t_tp2_hit = t_trail_active = False
                t_locked_pnl = 0.0; t_remaining_qty = 1.0
            continue

        # ── SIGNAL & ENTRY ──
        comp, trend, entry_, sl_, atr_, vol_ok_ = score_slice_v2(df_slice)

        # Filtre 1: Minimum Skor
        if comp < min_score or trend == "NEUTRAL" or entry_ is None:
            continue

        signals_seen += 1

        # Filtre 2: 1D Trend uyumu (opsiyonel)
        if require_1d_trend:
            trend_1d = _trend_1d(df_slice)
            if trend_1d != "NEUTRAL" and trend_1d != trend:
                continue

        # Filtre 3: Hacim onayı (opsiyonel)
        if require_vol and not vol_ok_:
            continue

        # Filtre 4: SL mesafesi aralığı
        sl_dist = abs(entry_ - sl_) / entry_
        if not (sl_min < sl_dist <= sl_max):
            continue

        signals_passed += 1

        # Kaldıraç hesabı
        if comp >= 8.0:     max_lev_by_score = 5
        elif comp >= 6.5:   max_lev_by_score = 4
        elif comp >= 5.5:   max_lev_by_score = 3
        else:               max_lev_by_score = 2

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
            d_ = "LONG"
        else:
            tp1_ = entry_ - risk_amount * TP1_R
            tp2_ = entry_ - risk_amount * TP2_R
            tp3_ = entry_ - risk_amount * TP3_R
            d_ = "SHORT"

        t_entry = entry_; t_sl = sl_; t_sl_original = sl_
        t_tp1 = tp1_; t_tp2 = tp2_; t_tp3 = tp3_
        t_atr = atr_; t_dir = d_; t_score = comp
        t_entry_bar = i; t_month = month
        t_tp1_hit = t_tp2_hit = t_trail_active = False
        t_trail_sl = t_locked_pnl = 0.0
        t_remaining_qty = 1.0
        t_leverage = lev; t_liq_dist = liq_dist
        t_liquidated = liquidated; in_trade = True

    return {
        "trades": trades,
        "signals_seen": signals_seen,
        "signals_passed": signals_passed,
    }


# ═══════════════════════════════════════════════════════════════
#  ANA ÇALIŞTIRICI
# ═══════════════════════════════════════════════════════════════

def main():
    head("FİLTRE GEVŞETMEMATRİSİ — ORP %5 OPTİMİZASYON TESTİ")

    # Birden fazla coin ve timeframe test edilecek
    test_pairs = [
        ("ETH/USDT", "1h"),
        ("BTC/USDT", "1h"),
        ("SOL/USDT", "1h"),
        ("ETH/USDT", "4h"),
        ("BTC/USDT", "4h"),
    ]

    all_results = []

    for symbol, tf in test_pairs:
        csv_path = f"data/historical/{symbol.replace('/', '_')}_{tf}.csv"
        if not os.path.exists(csv_path):
            print(f"\n  {bad('HATA')}: {csv_path} bulunamadı, atlanıyor.")
            continue

        df = pd.read_csv(csv_path)
        df["ts"] = pd.to_datetime(df["ts"])
        df.set_index("ts", inplace=True)
        df = df.sort_index()

        d0 = str(df.index[WARMUP])[:10]
        d1 = str(df.index[-1])[:10]

        h2(f"{symbol} {tf} — {len(df)} bar — {d0} → {d1}")

        for cfg in CONFIGS:
            sys.stdout.write(f"  {cfg['name']:40s} ... ")
            sys.stdout.flush()

            t0 = time.time()
            res = backtest_with_config(symbol, df, cfg, max_leverage_limit=5)
            elapsed = time.time() - t0

            trades = res["trades"]
            n_trades = len(trades)

            if n_trades == 0:
                print(f" {dim('0 işlem')} ({elapsed:.1f}sn)")
                all_results.append({
                    "symbol": symbol, "tf": tf, "config": cfg["name"],
                    "n_trades": 0, "win_rate": 0, "avg_r": 0,
                    "orp_final": 100.0, "orp_steps": 0,
                    "orp_dd": 0, "orp_max_lev": 0,
                    "signals_seen": res["signals_seen"],
                    "signals_passed": res["signals_passed"],
                })
                continue

            # Win rate hesapla
            wins = sum(1 for t in trades if "WIN" in t["result"])
            losses = sum(1 for t in trades if t["result"] == "LOSS")
            win_rate = wins / n_trades * 100 if n_trades > 0 else 0
            avg_r = sum(t["r_mult"] for t in trades) / n_trades

            # ORP %5 simülasyonu
            orp = run_orp(trades, start_capital=100.0, target_step_pct=0.05, max_lev_cap=5.0)

            print(f" {ok('OK')}: {n_trades:>3} işlem, WR: {win_rate:.0f}%, "
                  f"ORP: ${orp['final_eq']:>10,.2f} ({orp['steps_achieved']} adım), "
                  f"DD: {orp['max_drawdown']:.1f}% ({elapsed:.1f}sn)")

            all_results.append({
                "symbol": symbol, "tf": tf, "config": cfg["name"],
                "n_trades": n_trades, "win_rate": win_rate, "avg_r": avg_r,
                "orp_final": orp["final_eq"], "orp_steps": orp["steps_achieved"],
                "orp_dd": orp["max_drawdown"], "orp_max_lev": orp["max_lev_used"],
                "signals_seen": res["signals_seen"],
                "signals_passed": res["signals_passed"],
                "wiped": orp["wiped_out"],
            })

    # ═══════════════════════════════════════════════════════════════
    #  SONUÇ TABLOLARI
    # ═══════════════════════════════════════════════════════════════

    print("\n")
    head("FİLTRE GEVŞETMEMATRİSİ — SONUÇ KARŞILAŞTIRMA TABLOSU")
    print()

    # Markdown tablo
    print("| Sembol | TF | Konfigürasyon | İşlem | WR% | Ort R | ORP Bitiş ($) | %5 Adım | Max DD | Battı mı? |")
    print("|--------|----|---------------|-------|-----|-------|---------------|---------|--------|-----------|")

    for r in all_results:
        wiped = "EVET ❌" if r.get("wiped") else "HAYIR ✅"
        orp_val = f"${r['orp_final']:,.2f}" if r['orp_final'] > 0 else "$0.00"
        print(f"| **{r['symbol'].replace('/USDT','')}** | {r['tf']} | {r['config']} | "
              f"{r['n_trades']} | {r['win_rate']:.0f}% | {r['avg_r']:+.2f} | "
              f"**{orp_val}** | {r['orp_steps']} | {r['orp_dd']:.1f}% | {wiped} |")

    # En iyi konfigürasyonu bul (ETH 1h bazında)
    print("\n")
    h2("EN İYİ KONFİGÜRASYON ANALİZİ")

    eth_results = [r for r in all_results if r["symbol"] == "ETH/USDT" and r["tf"] == "1h"]
    if eth_results:
        best = max(eth_results, key=lambda x: x["orp_final"])
        current = next((r for r in eth_results if "Mevcut" in r["config"]), None)

        print(f"\n  🏆 EN İYİ: {best['config']}")
        print(f"     İşlem: {best['n_trades']}, WR: {best['win_rate']:.0f}%, ORP: ${best['orp_final']:,.2f}, DD: {best['orp_dd']:.1f}%")

        if current and best["config"] != current["config"]:
            pct_gain = (best["orp_final"] / current["orp_final"] - 1) * 100 if current["orp_final"] > 0 else 0
            trade_gain = best["n_trades"] - current["n_trades"]
            print(f"\n  📊 MEVCUT ile karşılaştırma:")
            print(f"     Mevcut: {current['n_trades']} işlem, ${current['orp_final']:,.2f}")
            print(f"     Yeni:   {best['n_trades']} işlem (+{trade_gain}), ${best['orp_final']:,.2f}")
            print(f"     Fark:   {ok(f'+{pct_gain:.1f}%') if pct_gain > 0 else bad(f'{pct_gain:.1f}%')}")


if __name__ == "__main__":
    main()
