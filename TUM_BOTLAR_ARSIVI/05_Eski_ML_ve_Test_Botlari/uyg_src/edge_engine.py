#!/usr/bin/env python3
"""
edge_engine.py — Sinyal taraması (pahalı, cache'li) ile fill-simülasyonu (ucuz) AYRI.
═══════════════════════════════════════════════════════════════════════
scan_signals(df): her sinyali (bar index + OB seviyeleri) çıkarır — coin başına BİR kez.
simulate_fills(df, signals, cfg): timeout/giriş-seviyesi/cancel kombinasyonunu ucuz replay eder.

Böylece "dolum oranı vs WR" eğrisini (deep target #1) saniyede süpürebiliriz.
Look-ahead yok: sinyal bar i'de df[:i] ile üretilir; fill ve exit i+1'den itibaren.
"""
import os, json, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
from backtest_multi_tf import (score_slice_v2, WARMUP, TP1_R, TP2_R, TP3_R,
                               TP1_CLOSE, TP2_CLOSE, TP3_CLOSE, COMMISSION)
from live_scan import order_blocks

SLIP_LIMIT = 0.0002
SLIP_MARKET = 0.0010
ROUND_TRIP = COMMISSION * 2


# ── PHASE A: pahalı sinyal taraması (cache'lenebilir) ──────────────────
def scan_signals(df):
    sigs = []
    n = len(df)
    close = df["close"].to_numpy()
    for i in range(WARMUP, n - 1):
        df_slice = df.iloc[max(0, i - 400):i]
        comp, trend, entry_, sl_, atr_, vol_ok_ = score_slice_v2(df_slice)
        if comp < 4.5 or trend == "NEUTRAL" or not vol_ok_:
            continue
        bull_obs, bear_obs, _, _ = order_blocks(df_slice)
        if trend == "BULLISH" and bull_obs:
            ob_mid = float(bull_obs[0]["mid"]); ob_high = float(bull_obs[0]["high"])
        elif trend == "BEARISH" and bear_obs:
            ob_mid = float(bear_obs[0]["mid"]); ob_high = float(bear_obs[0]["low"])
        else:
            continue
        sl_price = ob_mid - atr_ * 1.5 if trend == "BULLISH" else ob_mid + atr_ * 1.5
        sigs.append({"i": i, "dir": trend, "ob_mid": ob_mid, "ob_high": ob_high,
                     "sl": float(sl_price), "atr": float(atr_), "close": float(close[i]),
                     "comp": float(comp)})
    return sigs


# ── PHASE B: ucuz fill + exit simülasyonu ──────────────────────────────
def simulate_fills(df, signals, timeout=6, entry_mode="scalein", runaway=False, runaway_atr=3.0):
    """
    entry_mode: 'mid' | 'high' | 'scalein'(high+mid) | 'market'(sinyal sonrası açılış)
    runaway: True ise fiyat girişten runaway_atr*ATR uzaklaşınca emri iptal et.
    Dönüş: trades[], stats{signals, fills}
    """
    H = df["high"].to_numpy(); L = df["low"].to_numpy(); O = df["open"].to_numpy()
    n = len(df)
    trades = []
    filled = 0
    busy_until = -1  # aynı anda tek pozisyon (önceki trade'in exit barı)
    for s in signals:
        i = s["i"]
        if i <= busy_until:
            continue
        d = s["dir"]
        is_long = d in ("LONG", "BULLISH")
        if entry_mode == "market":
            levels = [O[i + 1]] if i + 1 < n else []
        elif entry_mode == "mid":
            levels = [s["ob_mid"]]
        elif entry_mode == "high":
            levels = [s["ob_high"]]
        else:  # scalein
            levels = [s["ob_high"], s["ob_mid"]]
        if not levels:
            continue

        # --- FILL ---
        fills = []
        if entry_mode == "market":
            fills = [levels[0]]
            fill_bar = i + 1
        else:
            fill_bar = None
            for k in range(i + 1, min(i + 1 + timeout, n)):
                for px in levels:
                    if px in [f[1] for f in fills]:
                        continue
                    if is_long and L[k] <= px:
                        fills.append((k, px))
                    elif (not is_long) and H[k] >= px:
                        fills.append((k, px))
                if runaway:
                    if is_long and H[k] >= s["ob_high"] + s["atr"] * runaway_atr:
                        break
                    if (not is_long) and L[k] <= s["ob_high"] - s["atr"] * runaway_atr:
                        break
                if fills:
                    fill_bar = k
                    break  # ilk dolan bardan gir (en az 1 emir)
            if not fills:
                continue
            if fill_bar is None:  # runaway break ile aynı barda dolum olduysa
                fill_bar = fills[-1][0]
            fills = [f[1] for f in fills]
        filled += 1
        entry = sum(fills) / len(fills)
        entry *= (1 + SLIP_LIMIT) if is_long else (1 - SLIP_LIMIT)
        sl0 = s["sl"]; atr = s["atr"]
        sl_dist = abs(entry - sl0) / entry
        if sl_dist <= 0 or sl_dist > 0.12:
            continue
        risk = abs(entry - sl0)
        if is_long:
            tp1, tp2, tp3 = entry + risk*TP1_R, entry + risk*TP2_R, entry + risk*TP3_R
        else:
            tp1, tp2, tp3 = entry - risk*TP1_R, entry - risk*TP2_R, entry - risk*TP3_R

        # --- EXIT replay ---
        sl = sl0; tp1_hit = tp2_hit = False; locked = 0.0; pnl_r = None; res = ""
        start = fill_bar + 1 if entry_mode != "market" else i + 2
        for k in range(start, n):
            hi = H[k]; lo = L[k]
            if is_long:
                if lo <= sl:
                    pnl_r = locked if tp1_hit else -1.0; res = "WIN_BE" if tp1_hit else "LOSS"; break
                if hi >= tp3:
                    pnl_r = locked + TP3_CLOSE * TP3_R; res = "WIN_TP3"; break
                if not tp2_hit and hi >= tp2:
                    locked += TP2_CLOSE * TP2_R; tp2_hit = True
                if not tp1_hit and hi >= tp1:
                    locked += TP1_CLOSE * TP1_R; tp1_hit = True; sl = entry * 1.001
            else:
                if hi >= sl:
                    pnl_r = locked if tp1_hit else -1.0; res = "WIN_BE" if tp1_hit else "LOSS"; break
                if lo <= tp3:
                    pnl_r = locked + TP3_CLOSE * TP3_R; res = "WIN_TP3"; break
                if not tp2_hit and lo <= tp2:
                    locked += TP2_CLOSE * TP2_R; tp2_hit = True
                if not tp1_hit and lo <= tp1:
                    locked += TP1_CLOSE * TP1_R; tp1_hit = True; sl = entry * 0.999
        if pnl_r is None:
            pnl_r = locked; res = "OPEN_END"; k = n - 1
        cost_r = (ROUND_TRIP + SLIP_LIMIT + SLIP_MARKET) / sl_dist if sl_dist > 0 else 0
        net_r = pnl_r - cost_r
        trades.append({"r_mult": round(net_r, 4), "sl_pct": sl_dist * 100, "result": res,
                       "dir": d, "exit_ts": str(df.index[k]), "comp": s["comp"], "sig_i": i})
        busy_until = k
    fr = filled / len(signals) * 100 if signals else 0
    return trades, {"signals": len(signals), "fills": filled, "fill_rate": fr}


def get_fills(df, signals, timeout=12, entry_mode="mid", runaway=False, runaway_atr=3.0):
    """Sadece DOLAN girişleri döndür (çıkış simüle etmeden) — exit-sweep için.
    Dönüş: entries[] {entry, sl, atr, dir, fill_bar, sig_i}"""
    H = df["high"].to_numpy(); L = df["low"].to_numpy(); O = df["open"].to_numpy()
    n = len(df); ent = []; busy_until = -1
    for s in signals:
        i = s["i"]
        if i <= busy_until:
            continue
        d = s["dir"]; is_long = d in ("LONG", "BULLISH")
        if entry_mode == "market":
            levels = [O[i + 1]] if i + 1 < n else []
        elif entry_mode == "mid":
            levels = [s["ob_mid"]]
        elif entry_mode == "high":
            levels = [s["ob_high"]]
        else:
            levels = [s["ob_high"], s["ob_mid"]]
        if not levels:
            continue
        fills = []; fill_bar = None
        if entry_mode == "market":
            fills = [levels[0]]; fill_bar = i + 1
        else:
            for k in range(i + 1, min(i + 1 + timeout, n)):
                for px in levels:
                    if px in [f[1] for f in fills]:
                        continue
                    if is_long and L[k] <= px:
                        fills.append((k, px))
                    elif (not is_long) and H[k] >= px:
                        fills.append((k, px))
                if fills:
                    fill_bar = k; break
            if not fills:
                continue
            fills = [f[1] for f in fills]
        entry = sum(fills) / len(fills)
        entry *= (1 + SLIP_LIMIT) if is_long else (1 - SLIP_LIMIT)
        sl0 = s["sl"]; sl_dist = abs(entry - sl0) / entry
        if sl_dist <= 0 or sl_dist > 0.12:
            continue
        # exit'i en az fill_bar+1'den başlatacağız; busy_until exit motorunda set edilir
        ent.append({"entry": entry, "sl": sl0, "atr": s["atr"], "dir": d,
                    "fill_bar": fill_bar, "sig_i": i, "sl_dist": sl_dist})
        # kaba busy: çıkış bilinmediği için bir sonraki sinyali fill_bar sonrası kabul et
        busy_until = fill_bar
    return ent


def edge_metrics(trades):
    if not trades:
        return {"n": 0}
    r = np.array([t["r_mult"] for t in trades])
    wins = r[r > 0]; losses = r[r <= 0]
    pf = wins.sum() / abs(losses.sum()) if len(losses) and losses.sum() != 0 else float("inf")
    streak = mx = 0
    for x in r:
        if x <= 0: streak += 1; mx = max(mx, streak)
        else: streak = 0
    return {"n": len(r), "wr": (r > 0).mean()*100, "avg_r": r.mean(), "sum_r": r.sum(),
            "pf": pf, "avg_win": wins.mean() if len(wins) else 0,
            "avg_loss": losses.mean() if len(losses) else 0, "max_loss_streak": mx}


def load_df(path):
    df = pd.read_csv(path); df["ts"] = pd.to_datetime(df["ts"])
    df.set_index("ts", inplace=True); return df.sort_index()


def scan_and_cache(coin, path, cache_dir="sigcache", tf="4h"):
    os.makedirs(cache_dir, exist_ok=True)
    cp = f"{cache_dir}/{coin}_{tf}.json"
    if os.path.exists(cp):
        return json.load(open(cp))
    df = load_df(path)
    sigs = scan_signals(df)
    json.dump(sigs, open(cp, "w"))
    return sigs
