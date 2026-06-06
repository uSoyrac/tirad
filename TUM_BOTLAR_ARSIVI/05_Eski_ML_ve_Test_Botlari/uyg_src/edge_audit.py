#!/usr/bin/env python3
"""
edge_audit.py — DÜRÜST EDGE ÖLÇÜMÜ (FAZ 1)
═══════════════════════════════════════════════════════════════════════
Amaç: S3 (Trend+OB) sinyalinin GERÇEK edge'ini, look-ahead'siz ve
gerçekçi limit-dolum + maliyet modeliyle ölçmek.

İki motor farkı (KANITLANMIŞ):
  - simulate_orp.backtest_symbol_optimized → ANLIK dolum (OB-mid'den hemen
    girilmiş sayar) → %87 WR FANTEZİ.
  - bu harness → PENDING limit: fiyat seviyeye GERÇEKTEN değmezse dolum YOK
    (strict cross), 3 bar timeout, kaçarsa iptal → gerçek WR + fill-rate.

Raporlar: sinyal sayısı, dolum oranı, WR, avg R, beklenti, profit factor,
          per-coin + havuz + zaman-dışı (ilk yarı / son yarı) stabilite.
"""
import os, sys, math, argparse, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from backtest_multi_tf import (score_slice_v2, WARMUP, TP1_R, TP2_R, TP3_R,
                               TP1_CLOSE, TP2_CLOSE, TP3_CLOSE, COMMISSION)
from live_scan import order_blocks

TIMEOUT_BARS = 3
SLIP_LIMIT = 0.0002     # limit giriş kayması
SLIP_MARKET = 0.0010    # market çıkış (SL) kayması
ROUND_TRIP = COMMISSION * 2  # %0.08 gidiş-dönüş komisyon


def honest_backtest(df, timeout=TIMEOUT_BARS, scale_in=True):
    """Look-ahead'siz, pending-limit dolumlu dürüst backtest.
    Dönüş: trades[], stats{signals, fills, fill_rate, ...}"""
    trades = []
    n = len(df)
    signals = 0           # üretilen sinyal (pending order kümesi)
    filled_signals = 0    # en az 1 emri dolan sinyal
    in_trade = False
    pending = []
    t = {}

    for i in range(WARMUP, n - 1):
        hi = float(df["high"].iloc[i]); lo = float(df["low"].iloc[i])
        cl = float(df["close"].iloc[i]); ts = df.index[i]

        # ---- EXIT ----
        if in_trade:
            exited = False; pnl_r = 0.0; res = ""
            sl_dist = abs(t["entry"] - t["sl_orig"]) / t["entry"]
            if t["dir"] == "LONG":
                if lo <= t["sl"]:
                    pnl_r = t["locked"] if t["tp1_hit"] else -1.0
                    res = "WIN_BE" if t["tp1_hit"] else "LOSS"; exited = True
                elif hi >= t["tp3"]:
                    pnl_r = t["locked"] + TP3_CLOSE * TP3_R; res = "WIN_TP3"; exited = True
                elif not t["tp2_hit"] and hi >= t["tp2"]:
                    t["locked"] += TP2_CLOSE * TP2_R; t["tp2_hit"] = True
                elif not t["tp1_hit"] and hi >= t["tp1"]:
                    t["locked"] += TP1_CLOSE * TP1_R; t["tp1_hit"] = True
                    t["sl"] = t["entry"] * 1.001
            else:  # SHORT
                if hi >= t["sl"]:
                    pnl_r = t["locked"] if t["tp1_hit"] else -1.0
                    res = "WIN_BE" if t["tp1_hit"] else "LOSS"; exited = True
                elif lo <= t["tp3"]:
                    pnl_r = t["locked"] + TP3_CLOSE * TP3_R; res = "WIN_TP3"; exited = True
                elif not t["tp2_hit"] and lo <= t["tp2"]:
                    t["locked"] += TP2_CLOSE * TP2_R; t["tp2_hit"] = True
                elif not t["tp1_hit"] and lo <= t["tp1"]:
                    t["locked"] += TP1_CLOSE * TP1_R; t["tp1_hit"] = True
                    t["sl"] = t["entry"] * 0.999
            if exited:
                # maliyet: giriş limit kayması+komisyon, çıkış market kayması+komisyon
                cost_r = (ROUND_TRIP + SLIP_LIMIT + SLIP_MARKET) / sl_dist if sl_dist > 0 else 0
                net_r = pnl_r - cost_r
                trades.append({"r_mult": round(net_r, 4), "sl_pct": sl_dist * 100,
                               "result": res, "dir": t["dir"], "exit_ts": str(ts)})
                in_trade = False; pending = []
            continue

        # ---- PENDING FILL CHECK ----
        if pending:
            for p in pending:
                p["wait"] += 1
                if p["filled"]:
                    continue
                # kaçtı mı? (fiyat girişe gelmeden TP yönüne çok gitti → iptal)
                if p["dir"] == "LONG" and hi >= p["price"] + p["atr"] * 2.0:
                    p["cancelled"] = True
                elif p["dir"] == "SHORT" and lo <= p["price"] - p["atr"] * 2.0:
                    p["cancelled"] = True
                else:
                    if p["dir"] == "LONG" and lo <= p["price"]:
                        p["filled"] = True
                    elif p["dir"] == "SHORT" and hi >= p["price"]:
                        p["filled"] = True
            pending = [p for p in pending if not p.get("cancelled") and p["wait"] <= timeout]
            fills = [p for p in pending if p["filled"]]
            if fills:
                filled_signals += 1
                entry = sum(f["price"] for f in fills) / len(fills)
                entry *= (1 + SLIP_LIMIT) if fills[0]["dir"] == "LONG" else (1 - SLIP_LIMIT)
                sl = fills[0]["sl"]; atr = fills[0]["atr"]; d = fills[0]["dir"]
                risk = abs(entry - sl)
                if d == "LONG":
                    tp1, tp2, tp3 = entry + risk*TP1_R, entry + risk*TP2_R, entry + risk*TP3_R
                else:
                    tp1, tp2, tp3 = entry - risk*TP1_R, entry - risk*TP2_R, entry - risk*TP3_R
                t = {"entry": entry, "sl": sl, "sl_orig": sl, "tp1": tp1, "tp2": tp2,
                     "tp3": tp3, "atr": atr, "dir": d, "tp1_hit": False, "tp2_hit": False,
                     "locked": 0.0}
                in_trade = True; pending = []
            elif not pending:
                pass  # tümü iptal/timeout → sinyal boşa düştü (dolmadı)
            continue

        # ---- SIGNAL ----
        df_slice = df.iloc[max(0, i - 400):i]
        comp, trend, entry_, sl_, atr_, vol_ok_ = score_slice_v2(df_slice)
        if comp < 4.5 or trend == "NEUTRAL" or not vol_ok_:
            continue
        bull_obs, bear_obs, _, _ = order_blocks(df_slice)
        ob_mid = ob_high = None
        if trend == "BULLISH" and bull_obs:
            ob_mid = float(bull_obs[0]["mid"]); ob_high = float(bull_obs[0]["high"])
        elif trend == "BEARISH" and bear_obs:
            ob_mid = float(bear_obs[0]["mid"]); ob_high = float(bear_obs[0]["low"])
        if not (ob_mid and ob_high):
            continue
        sl_price = ob_mid - atr_ * 1.5 if trend == "BULLISH" else ob_mid + atr_ * 1.5
        signals += 1
        levels = [ob_high, ob_mid] if scale_in else [ob_mid]
        for px in levels:
            pending.append({"dir": trend, "price": px, "sl": sl_price, "atr": atr_,
                            "wait": 0, "filled": False})

    fill_rate = filled_signals / signals * 100 if signals else 0
    return trades, {"signals": signals, "filled_signals": filled_signals, "fill_rate": fill_rate}


def edge_metrics(trades):
    if not trades:
        return {"n": 0}
    r = np.array([t["r_mult"] for t in trades])
    wins = r[r > 0]; losses = r[r <= 0]
    pf = wins.sum() / abs(losses.sum()) if len(losses) and losses.sum() != 0 else float("inf")
    return {"n": len(r), "wr": (r > 0).mean()*100, "avg_r": r.mean(), "sum_r": r.sum(),
            "expectancy": r.mean(), "pf": pf, "avg_win": wins.mean() if len(wins) else 0,
            "avg_loss": losses.mean() if len(losses) else 0,
            "max_loss_streak": _streak(trades)}


def _streak(trades):
    mx = cur = 0
    for t in trades:
        if t["r_mult"] <= 0: cur += 1; mx = max(mx, cur)
        else: cur = 0
    return mx


def load_df(path):
    df = pd.read_csv(path); df["ts"] = pd.to_datetime(df["ts"])
    df.set_index("ts", inplace=True); return df.sort_index()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data", help="veri klasörü (data | mktdata)")
    ap.add_argument("--tf", default="4h")
    ap.add_argument("--coins", default="")
    ap.add_argument("--no-scale", action="store_true", help="sadece OB-mid (tek limit)")
    args = ap.parse_args()

    files = []
    if args.coins:
        coins = args.coins.split(",")
    else:
        coins = sorted([f.split("_")[0] for f in os.listdir(args.data) if f.endswith(f"_{args.tf}.csv")])
    print("=" * 84)
    print(f"  DÜRÜST EDGE ÖLÇÜMÜ — {args.data}/ TF={args.tf}  scale_in={not args.no_scale}")
    print(f"  Maliyet: komisyon RT %{ROUND_TRIP*100:.2f} + limit kayma %{SLIP_LIMIT*100:.2f} + market kayma %{SLIP_MARKET*100:.2f}")
    print("=" * 84)
    print(f"  {'COIN':6}{'bars':>6}{'sig':>6}{'fill%':>7}{'N':>5}{'WR%':>7}{'avgR':>8}{'sumR':>8}{'PF':>6}{'lstreak':>8}")
    pool = []
    for c in coins:
        path = f"{args.data}/{c}_USDT_{args.tf}.csv"
        if not os.path.exists(path):
            continue
        df = load_df(path)
        trades, st = honest_backtest(df, scale_in=not args.no_scale)
        m = edge_metrics(trades)
        for t in trades: t["coin"] = c
        pool += trades
        if m["n"]:
            print(f"  {c:6}{len(df):>6}{st['signals']:>6}{st['fill_rate']:>7.1f}{m['n']:>5}"
                  f"{m['wr']:>7.1f}{m['avg_r']:>+8.3f}{m['sum_r']:>+8.1f}{m['pf']:>6.2f}{m['max_loss_streak']:>8}")
        else:
            print(f"  {c:6}{len(df):>6}{st['signals']:>6}{st['fill_rate']:>7.1f}{0:>5}   (trade yok)")
    print("  " + "-" * 82)
    pm = edge_metrics(pool)
    if pm["n"]:
        print(f"  {'POOL':6}{'':>6}{'':>6}{'':>7}{pm['n']:>5}{pm['wr']:>7.1f}{pm['avg_r']:>+8.3f}"
              f"{pm['sum_r']:>+8.1f}{pm['pf']:>6.2f}{pm['max_loss_streak']:>8}")
        print(f"\n  Beklenti (expectancy): {pm['expectancy']:+.4f}R/işlem | avg_win {pm['avg_win']:+.2f}R | avg_loss {pm['avg_loss']:+.2f}R")
        # zaman-dışı stabilite: havuzu exit_ts'e göre sıralayıp ilk/son yarı
        pool.sort(key=lambda x: x["exit_ts"])
        half = len(pool) // 2
        for lab, seg in [("ilk %50 ", pool[:half]), ("son %50 ", pool[half:])]:
            sm = edge_metrics(seg)
            print(f"  {lab}: N={sm['n']:>3}  WR={sm['wr']:.1f}%  avgR={sm['avg_r']:+.3f}  PF={sm['pf']:.2f}")
        print(f"\n  >>> EDGE KARARI: WR={pm['wr']:.1f}%  beklenti={pm['expectancy']:+.3f}R  "
              f"→ {'POZİTİF EDGE ✓' if pm['expectancy']>0 else 'EDGE YOK ✗'}"
              f"  | %60 WR hedefi: {'TUTTU' if pm['wr']>=60 else 'TUTMADI'}")
    import json
    json.dump(pool, open(f"/tmp/honest_trades_{args.tf}.json", "w"), default=str)
    print(f"\n  ✅ {len(pool)} dürüst trade → /tmp/honest_trades_{args.tf}.json")


if __name__ == "__main__":
    main()
