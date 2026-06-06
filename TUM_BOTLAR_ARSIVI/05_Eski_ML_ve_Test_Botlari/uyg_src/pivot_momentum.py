#!/usr/bin/env python3
"""
pivot_momentum.py — CROSS-SECTIONAL & TIME-SERIES MOMENTUM (S3 pivotu)
═══════════════════════════════════════════════════════════════════════
S3 ölü (edge yok). Bu motor kriptonun en sağlam edge'ini test eder:
göreceli güç (cross-sectional momentum) + trend takibi (time-series mom).

Look-ahead YOK: rebalance t'de yalnız t'ye kadarki getiri kullanılır,
pozisyon t→t+HOLD tutulur. Maliyet: her rebalance'da round-trip fee+slippage.

Çıktı: her (lookback, hold, top_k) için — rebalance WR, ort getiri, Sharpe,
yıllık getiri, MDD, compound x; long-only vs long-short (market-nötr alfa).
Overfit kontrolü: zaman-yarısı + parametre robustluğu.
"""
import os, sys, json, argparse, warnings, itertools
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

FEE = 0.0004
SLIP = 0.0003
RT_COST = (FEE + SLIP) * 2  # round-trip per pozisyon per rebalance


def load_matrix(data_dir, tf):
    closes = {}
    for f in sorted(os.listdir(data_dir)):
        if not f.endswith(f"_{tf}.csv"):
            continue
        c = f.split("_")[0]
        df = pd.read_csv(f"{data_dir}/{f}"); df["ts"] = pd.to_datetime(df["ts"])
        closes[c] = df.set_index("ts")["close"]
    M = pd.DataFrame(closes).sort_index()
    return M


def backtest_xs(M, lookback, hold, top_k, mode="longshort"):
    """Cross-sectional momentum. M: price matrix (ts × coin)."""
    rets = []  # her rebalance periyodunun net getirisi (compound adımı)
    ts_list = []
    idx = M.index
    t = lookback
    while t + hold < len(M):
        past = M.iloc[t] / M.iloc[t - lookback] - 1.0  # t'ye kadar momentum
        valid = past.dropna()
        if len(valid) < top_k * 2:
            t += hold; continue
        ranked = valid.sort_values(ascending=False)
        longs = ranked.index[:top_k]
        fwd = M.iloc[t + hold] / M.iloc[t] - 1.0  # tutma getirisi
        long_ret = fwd[longs].mean()
        if mode == "longshort":
            shorts = ranked.index[-top_k:]
            short_ret = -fwd[shorts].mean()
            gross = (long_ret + short_ret) / 2.0
            cost = RT_COST * 2  # iki bacak
        else:  # long-only
            gross = long_ret
            cost = RT_COST
        rets.append(gross - cost)
        ts_list.append(idx[t + hold])
        t += hold
    return np.array(rets), ts_list


def stats(rets, ts_list, bars_per_year, hold):
    if len(rets) < 5:
        return None
    eq = np.cumprod(1 + rets)
    total_x = eq[-1]
    wr = (rets > 0).mean() * 100
    avg = rets.mean()
    sharpe = avg / (rets.std() + 1e-9) * np.sqrt(bars_per_year / hold)  # yıllıklaştır
    peak = np.maximum.accumulate(eq); mdd = float(((peak - eq) / peak).max() * 100)
    n_per_year = bars_per_year / hold
    cagr = (total_x ** (n_per_year / len(rets)) - 1) * 100 if total_x > 0 else -100
    # zaman-yarısı
    h = len(rets) // 2
    h1 = np.cumprod(1 + rets[:h])[-1]; h2 = np.cumprod(1 + rets[h:])[-1]
    return {"n": len(rets), "wr": wr, "avg": avg*100, "sharpe": sharpe, "total_x": total_x,
            "cagr": cagr, "mdd": mdd, "h1_x": h1, "h2_x": h2}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="mktdata"); ap.add_argument("--tf", default="4h")
    args = ap.parse_args()
    M = load_matrix(args.data, args.tf)
    bpy = {"4h": 6*365, "1h": 24*365, "1d": 365}.get(args.tf, 6*365)
    print("=" * 92)
    print(f"  MOMENTUM PİVOT — {args.data}/ TF={args.tf}  ({M.shape[1]} coin, {M.shape[0]} bar, "
          f"{M.index[0].date()}→{M.index[-1].date()})")
    print(f"  Maliyet: round-trip %{RT_COST*100:.2f}/pozisyon")
    print("=" * 92)

    # bar cinsinden: lookback ~ {30,60,90 gün}, hold ~ {7,14,30 gün}
    d = 6  # 4H bar/gün
    grids = list(itertools.product([30*d, 60*d, 90*d], [7*d, 14*d, 30*d], [3, 5]))
    for mode in ["longshort", "longonly"]:
        print(f"\n  ── {mode.upper()} ──")
        print(f"  {'LB(g)':>6}{'Hold(g)':>8}{'topK':>5}{'N':>5}{'WR%':>7}{'avgR%':>7}{'Sharpe':>8}{'CAGR%':>8}{'MDD%':>7}{'totX':>9}{'ilk½':>7}{'son½':>7}")
        rows = []
        for lb, hold, k in grids:
            rets, tsl = backtest_xs(M, lb, hold, k, mode=mode)
            st = stats(rets, tsl, bpy, hold)
            if not st:
                continue
            stable = st["h1_x"] > 1 and st["h2_x"] > 1
            mark = " ✓" if st["sharpe"] > 0.8 and stable else (" +" if st["avg"] > 0 else "")
            print(f"  {lb//d:>6}{hold//d:>8}{k:>5}{st['n']:>5}{st['wr']:>7.1f}{st['avg']:>7.2f}"
                  f"{st['sharpe']:>8.2f}{st['cagr']:>8.1f}{st['mdd']:>7.1f}{st['total_x']:>9.2f}"
                  f"{st['h1_x']:>7.2f}{st['h2_x']:>7.2f}{mark}")
            rows.append((lb, hold, k, st, stable, rets, tsl))
        # en iyi sharpe (stabil)
        good = [r for r in rows if r[3]["sharpe"] > 0 and r[4]]
        good.sort(key=lambda x: -x[3]["sharpe"])
        if good:
            lb, hold, k, st, stable, rets, tsl = good[0]
            print(f"  >>> EN İYİ {mode}: LB={lb//d}g hold={hold//d}g topK={k} → "
                  f"Sharpe={st['sharpe']:.2f} CAGR={st['cagr']:.1f}% MDD={st['mdd']:.1f}% "
                  f"{'ZAMAN-STABİL ✓' if stable else ''}")
            if mode == "longshort":
                json.dump({"rets": rets.tolist(), "ts": [str(x) for x in tsl],
                           "params": {"lookback": lb, "hold": hold, "top_k": k}},
                          open(f"/tmp/momentum_best.json", "w"))


if __name__ == "__main__":
    main()
