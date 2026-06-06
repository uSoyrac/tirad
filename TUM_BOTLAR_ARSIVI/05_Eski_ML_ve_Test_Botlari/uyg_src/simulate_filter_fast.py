#!/usr/bin/env python3
"""
FAST FILTER SWEEP — Sadece ETH/USDT 1h (1 yıl)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
8 farklı filtre konfigürasyonunu tek coin üzerinde test eder.
Daha sonra en iyileri diğer coinlere genişletilir.
"""
import os, sys, time, math
import numpy as np
import pandas as pd

from backtest_multi_tf import (
    score_slice_v2, WARMUP, EMA_TREND_PERIOD,
    SL_ATR_MULT, TP1_R, TP2_R, TP3_R, TRAIL_ATR,
    TP1_CLOSE, TP2_CLOSE, TP3_CLOSE, ROUND_TRIP, CAPITAL
)
from simulate_orp import run_orp, calculate_max_dd
from live_scan import B, R, GR, RD, YL, CY, DM, ok, bad, warn, nfo, dim, head, h2

# ═══════════════════════════════════════════════════════════════
#  STEP 1: Tek seferde TÜM barları tara, ham sinyalleri topla
#  Bu sayede 8 config için 8 kez backtest yerine, 
#  1 kez sinyal taraması + 8 kez filtre+simülasyon yapılır
# ═══════════════════════════════════════════════════════════════

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

def scan_all_signals(symbol, df_full):
    """
    Tüm barları tarayarak ham sinyal listesi üretir.
    Filtre uygulamaz — sadece sinyal + metadata toplar.
    """
    signals = []
    total_bars = len(df_full)
    print(f"  Taranıyor: {total_bars} bar", end="", flush=True)

    for i in range(WARMUP, total_bars - 1):
        if i % 2000 == 0:
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


def simulate_trades(df_full, signals, config, max_leverage_limit=5):
    """
    Toplanan ham sinyallere filtre uygulayıp trade simülasyonu yapar.
    Sinyal taraması yapılmadığı için ÇOK HIZLI çalışır.
    """
    min_score = config["min_score"]
    require_vol = config["require_vol"]
    require_1d_trend = config["require_1d_trend"]
    sl_min, sl_max = config["sl_range"]

    trades = []
    equity = [CAPITAL]

    in_trade = False
    t_dir = ""; t_entry = t_sl = t_sl_original = 0.0
    t_tp1 = t_tp2 = t_tp3 = t_atr = t_score = 0.0
    t_entry_bar = 0; t_month = ""
    t_tp1_hit = t_tp2_hit = t_trail_active = False
    t_trail_sl = t_locked_pnl = 0.0
    t_remaining_qty = 1.0
    t_leverage = 1.0; t_liq_dist = 1.0; t_liquidated = False

    # Sinyalleri bar_idx ile indeksle
    sig_map = {s["bar_idx"]: s for s in signals}
    total_bars = len(df_full)

    for i in range(WARMUP, total_bars - 1):
        hi = float(df_full["high"].iloc[i])
        lo = float(df_full["low"].iloc[i])
        cl = float(df_full["close"].iloc[i])

        # ── EXIT ──
        if in_trade:
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
                        if t_tp1_hit: pnl_r = t_locked_pnl; exit_result = "WIN_BREAKEVEN"
                        else: pnl_r = -1.0; exit_result = "LOSS"
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
                        if t_tp1_hit: pnl_r = t_locked_pnl; exit_result = "WIN_BREAKEVEN"
                        else: pnl_r = -1.0; exit_result = "LOSS"
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
                    "symbol": "ETH/USDT", "direction": t_dir,
                    "entry": t_entry, "sl": t_sl_original,
                    "exit_price": exit_price, "result": exit_result,
                    "r_mult": round(net_r, 3), "dollar_pnl": round(dollar_pnl, 2),
                    "score": t_score, "equity": new_eq, "month": t_month,
                    "entry_bar": t_entry_bar, "exit_bar": i,
                    "sl_pct": sl_dist_t * 100, "atr": t_atr,
                    "tp1_hit": t_tp1_hit, "tp2_hit": t_tp2_hit,
                    "leverage": t_leverage,
                    "liq_dist_pct": t_liq_dist * 100, "liquidated": t_liquidated,
                })
                in_trade = t_tp1_hit = t_tp2_hit = t_trail_active = False
                t_locked_pnl = 0.0; t_remaining_qty = 1.0
            continue

        # ── SIGNAL & ENTRY ──
        sig = sig_map.get(i)
        if sig is None:
            continue

        comp = sig["composite"]
        trend = sig["trend"]
        entry_ = sig["entry"]
        sl_ = sig["sl"]
        atr_ = sig["atr"]
        vol_ok_ = sig["vol_ok"]
        sl_dist = sig["sl_dist"]
        trend_1d = sig["trend_1d"]

        # Filtre 1: Minimum Skor
        if comp < min_score:
            continue

        # Filtre 2: 1D Trend uyumu
        if require_1d_trend:
            if trend_1d != "NEUTRAL" and trend_1d != trend:
                continue

        # Filtre 3: Hacim onayı
        if require_vol and not vol_ok_:
            continue

        # Filtre 4: SL mesafesi
        if not (sl_min < sl_dist <= sl_max):
            continue

        # Kaldıraç
        if comp >= 8.0:     max_lev_by_score = 5
        elif comp >= 6.5:   max_lev_by_score = 4
        elif comp >= 5.5:   max_lev_by_score = 3
        else:               max_lev_by_score = 2

        max_lev_allowed = min(max_lev_by_score, max_leverage_limit)
        req_lev = math.ceil(0.02 / sl_dist)
        lev = max(1, min(req_lev, max_lev_allowed))
        liq_dist = 1.0 / lev

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
        t_entry_bar = i; t_month = sig["month"]
        t_tp1_hit = t_tp2_hit = t_trail_active = False
        t_trail_sl = t_locked_pnl = 0.0
        t_remaining_qty = 1.0
        t_leverage = lev; t_liq_dist = liq_dist
        t_liquidated = (sl_dist >= liq_dist)
        in_trade = True

    return trades


# ═══════════════════════════════════════════════════════════════
#  KONFİGÜRASYONLAR
# ═══════════════════════════════════════════════════════════════

CONFIGS = [
    {"name": "A — Mevcut (Sıkı)",           "min_score": 4.5, "require_vol": True,  "require_1d_trend": True,  "sl_range": (0.005, 0.10)},
    {"name": "B — Score≥3.5",                "min_score": 3.5, "require_vol": True,  "require_1d_trend": True,  "sl_range": (0.005, 0.10)},
    {"name": "C — Hacim Kapalı",             "min_score": 4.5, "require_vol": False, "require_1d_trend": True,  "sl_range": (0.005, 0.10)},
    {"name": "D — Score≥3.5 + Hacim Kapalı", "min_score": 3.5, "require_vol": False, "require_1d_trend": True,  "sl_range": (0.005, 0.10)},
    {"name": "E — Score≥3.0 + Hepsi Kapalı", "min_score": 3.0, "require_vol": False, "require_1d_trend": False, "sl_range": (0.005, 0.10)},
    {"name": "F — Score≥3.5 + Hepsi Kapalı", "min_score": 3.5, "require_vol": False, "require_1d_trend": False, "sl_range": (0.005, 0.10)},
    {"name": "G — Score≥4.0 + Hacim Kapalı", "min_score": 4.0, "require_vol": False, "require_1d_trend": True,  "sl_range": (0.005, 0.10)},
    {"name": "H — Score≥3.0 + Hepsi Gevşek", "min_score": 3.0, "require_vol": False, "require_1d_trend": False, "sl_range": (0.003, 0.12)},
]


def main():
    head("HIZLI FİLTRE GEVŞETMEMATRİSİ — ETH/USDT 1h")

    csv_path = "data/historical/ETH_USDT_1h.csv"
    if not os.path.exists(csv_path):
        print(f"  {bad('HATA')}: {csv_path} bulunamadı!")
        return

    df = pd.read_csv(csv_path)
    df["ts"] = pd.to_datetime(df["ts"])
    df.set_index("ts", inplace=True)
    df = df.sort_index()

    d0 = str(df.index[WARMUP])[:10]
    d1 = str(df.index[-1])[:10]
    print(f"  Veri: {len(df)} bar — {d0} → {d1}")

    # STEP 1: Tek seferde tüm sinyalleri topla (AĞIR İŞLEM — ama sadece 1 kez)
    h2("ADIM 1: TÜM SİNYALLERİ TARA (tek seferlik)")
    t0 = time.time()
    raw_signals = scan_all_signals("ETH/USDT", df)
    scan_time = time.time() - t0
    print(f"  Tarama süresi: {scan_time:.1f} saniye")

    # Sinyal dağılımı
    scores = [s["composite"] for s in raw_signals]
    print(f"  Skor dağılımı: min={min(scores):.2f}, max={max(scores):.2f}, ort={np.mean(scores):.2f}")
    for threshold in [3.0, 3.5, 4.0, 4.5, 5.0]:
        n = sum(1 for s in scores if s >= threshold)
        print(f"    Score >= {threshold}: {n} sinyal")

    # STEP 2: Her config için hızlı simülasyon
    h2("ADIM 2: 8 KONFİGÜRASYON SİMÜLASYONU")

    results = []
    for cfg in CONFIGS:
        sys.stdout.write(f"  {cfg['name']:40s} ... ")
        sys.stdout.flush()

        t0 = time.time()
        trades = simulate_trades(df, raw_signals, cfg, max_leverage_limit=5)
        elapsed = time.time() - t0

        n_trades = len(trades)
        if n_trades == 0:
            print(f" {dim('0 işlem')}")
            results.append({
                "config": cfg["name"], "n_trades": 0, "win_rate": 0,
                "losses": 0, "avg_r": 0,
                "orp_final": 100.0, "orp_steps": 0, "orp_dd": 0,
                "orp_max_lev": 0, "wiped": False,
            })
            continue

        wins = sum(1 for t in trades if "WIN" in t["result"])
        losses = sum(1 for t in trades if t["result"] == "LOSS")
        win_rate = wins / n_trades * 100
        avg_r = sum(t["r_mult"] for t in trades) / n_trades

        # ORP %5 simülasyonu
        orp = run_orp(trades, start_capital=100.0, target_step_pct=0.05, max_lev_cap=5.0)

        print(f" {n_trades:>3} işlem | WR: {win_rate:.0f}% | "
              f"W:{wins} L:{losses} | "
              f"ORP: ${orp['final_eq']:>12,.2f} ({orp['steps_achieved']} adım) | "
              f"DD: {orp['max_drawdown']:.1f}% | ({elapsed:.1f}sn)")

        results.append({
            "config": cfg["name"], "n_trades": n_trades,
            "win_rate": win_rate, "wins": wins, "losses": losses,
            "avg_r": avg_r,
            "orp_final": orp["final_eq"], "orp_steps": orp["steps_achieved"],
            "orp_dd": orp["max_drawdown"], "orp_max_lev": orp["max_lev_used"],
            "wiped": orp["wiped_out"],
        })

    # ═══════════════════════════════════════════════════════════════
    #  SONUÇ TABLOSU
    # ═══════════════════════════════════════════════════════════════
    print("\n")
    head("ETH/USDT 1h — FİLTRE GEVŞETMEMATRİSİ SONUÇLARI")
    print()
    print("| # | Konfigürasyon | İşlem | Kazanç | Kayıp | WR% | Ort R | ORP Bitiş ($) | %5 Adım | Max DD | Battı? |")
    print("|---|---------------|-------|--------|-------|-----|-------|---------------|---------|--------|--------|")

    for idx, r in enumerate(results, 1):
        wiped = "❌ EVET" if r["wiped"] else "✅ HAYIR"
        orp_str = f"${r['orp_final']:,.2f}"
        marker = " 🏆" if r["orp_final"] == max(x["orp_final"] for x in results) else ""
        print(f"| {idx} | {r['config']} | {r['n_trades']} | {r.get('wins',0)} | {r.get('losses',0)} | "
              f"{r['win_rate']:.0f}% | {r['avg_r']:+.2f} | **{orp_str}**{marker} | "
              f"{r['orp_steps']} | {r['orp_dd']:.1f}% | {wiped} |")

    # En iyi analiz
    best = max(results, key=lambda x: x["orp_final"])
    current = results[0]  # A — Mevcut

    print(f"\n{'='*70}")
    print(f"  🏆 EN İYİ KONFİGÜRASYON: {best['config']}")
    print(f"     İşlem: {best['n_trades']}, WR: {best['win_rate']:.0f}%, ORP: ${best['orp_final']:,.2f}")
    print(f"     Adım: {best['orp_steps']}, DD: {best['orp_dd']:.1f}%")

    if best["config"] != current["config"]:
        pct_gain = (best["orp_final"] / current["orp_final"] - 1) * 100 if current["orp_final"] > 0 else 0
        trade_diff = best["n_trades"] - current["n_trades"]
        wr_diff = best["win_rate"] - current["win_rate"]
        print(f"\n  📊 MEVCUT (A) ile karşılaştırma:")
        print(f"     İşlem farkı: +{trade_diff} ({current['n_trades']} → {best['n_trades']})")
        print(f"     WR farkı:    {wr_diff:+.1f}% ({current['win_rate']:.0f}% → {best['win_rate']:.0f}%)")
        print(f"     Kar farkı:   ${best['orp_final'] - current['orp_final']:+,.2f} ({pct_gain:+.1f}%)")
    else:
        print(f"\n  📊 Mevcut konfigürasyon zaten en iyi!")


if __name__ == "__main__":
    main()
