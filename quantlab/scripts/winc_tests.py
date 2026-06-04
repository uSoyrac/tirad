"""Honest tests of the TESTABLE Winning Circle concepts as entry filters on the
cross-sectional momentum book. We can only test what our 4h/1d data supports:
  A) Session / killzone: allow long entries only in specific UTC hours (time-of-day).
  B) Mayer Multiple: price / 200d-SMA valuation regime — gate longs when overheated.
Each is applied as a gate on the Top-3 momentum targets; we measure OOS Sharpe vs
ungated. (Liquidity heatmaps / order blocks / footprint need L2/tick data we lack.)

Usage: python scripts/winc_tests.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from quantlab.config import load_config  # noqa: E402
from quantlab.data import cache  # noqa: E402
from quantlab.backtest import metrics  # noqa: E402
from quantlab.backtest.portfolio import run_portfolio  # noqa: E402
from quantlab import orchestrator  # noqa: E402

MKTDATA = Path("../uyg/src/mktdata")
FUND = Path("../uyg/src/funddata")
UNIVERSE = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LTC", "ATOM", "DOT",
            "LINK", "DOGE", "ETC", "FIL", "INJ", "NEAR", "UNI", "APT", "ARB", "OP"]
CUT = pd.Timestamp("2025-01-01")


def _mayer(df: pd.DataFrame) -> pd.Series:
    """price / 200-day SMA, computed on daily then mapped causally to 4h bars."""
    daily = df["close"].resample("1D", label="left", closed="left").last()
    mm = daily / daily.rolling(200, min_periods=50).mean()
    # usable only after the day closes -> shift one day, then ffill onto 4h grid
    return mm.shift(1).reindex(df.index, method="ffill")


def _oos_sharpe(frames, targets, momentum, cfg):
    res = run_portfolio(frames, targets, momentum, cfg, top_k=3)
    eq = res.equity[res.equity.index >= CUT]
    m = metrics.compute_metrics(eq, [t for t in res.trades if pd.Timestamp(t.entry_ts) >= CUT],
                                timeframe="4h", ruin_drawdown=0.25, seed=42)
    return m


def main():
    cfg = load_config(str(Path(__file__).resolve().parents[1] / "config" / "default.yaml"))
    root = Path(__file__).resolve().parents[1]
    frames, targets, momentum = {}, {}, {}
    for sym in UNIVERSE:
        csv = (root / MKTDATA / f"{sym}_USDT_4h.csv").resolve()
        if not csv.exists():
            continue
        df = cache.load_ohlcv(f"{sym}/USDT", "4h", cache_dir=root / cfg.data.cache_dir,
                              start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
        hd = cache.load_ohlcv(f"{sym}/USDT", "1d", cache_dir=root / cfg.data.cache_dir,
                              start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
        frames[sym] = df
        targets[sym] = orchestrator.build_target(df, cfg, hd)
        momentum[sym] = df["close"].pct_change(60)

    base = _oos_sharpe(frames, targets, momentum, cfg)
    lines = ["# Winning Circle — testable-concept filters on the momentum book (OOS 2025-26)", "",
             f"Baseline (ungated Top-3): Sharpe {base['sharpe']:.2f}, win {base['win_rate']*100:.1f}%, "
             f"CAGR {base['cagr']*100:.1f}%, MaxDD {base['max_drawdown']*100:.1f}%", ""]

    # --- A) session / killzone hour filter ---
    lines += ["## A) Session / killzone (allow long entries only in given UTC hours)", "",
              "| Allowed 4h-bar hours (UTC) | OOS Sharpe | Win% | CAGR |", "|---|---|---|---|"]
    sessions = {
        "all (baseline)": {0, 4, 8, 12, 16, 20},
        "NY killzone (12,16)": {12, 16},
        "London (8)": {8},
        "London+NY (8,12,16)": {8, 12, 16},
        "Asia (0,4)": {0, 4},
    }
    for name, hours in sessions.items():
        gt = {s: t.where([(ts.hour in hours) or (v <= 0) for ts, v in zip(t.index, t)], 0.0)
              for s, t in targets.items()}
        m = _oos_sharpe(frames, gt, momentum, cfg)
        lines.append(f"| {name} | {m['sharpe']:.2f} | {m['win_rate']*100:.1f}% | {m['cagr']*100:.1f}% |")

    # --- B) Mayer Multiple valuation regime ---
    mayer = {s: _mayer(frames[s]) for s in frames}
    lines += ["", "## B) Mayer Multiple gate (long only if price/200d-SMA below threshold)", "",
              "| Max Mayer to allow long | OOS Sharpe | Win% | CAGR |", "|---|---|---|---|"]
    for thr in (1.0, 1.2, 1.5, 2.0, 99.0):
        gt = {}
        for s, t in targets.items():
            mm = mayer[s].reindex(t.index)
            ok = (mm < thr).fillna(False).to_numpy()
            gt[s] = t.where([(ok[i]) or (t.iloc[i] <= 0) for i in range(len(t))], 0.0)
        m = _oos_sharpe(frames, gt, momentum, cfg)
        lbl = "no gate" if thr == 99.0 else f"Mayer < {thr}"
        lines.append(f"| {lbl} | {m['sharpe']:.2f} | {m['win_rate']*100:.1f}% | {m['cagr']*100:.1f}% |")

    # --- C) SMT divergence (BTC/ETH breadth): block longs on bearish leader divergence ---
    lines += ["", "## C) SMT BTC/ETH agreement (long only when BTC & ETH N-bar momentum agree up)", "",
              "| Rule | OOS Sharpe | Win% | CAGR |", "|---|---|---|---|"]
    btc_c, eth_c = frames["BTC"]["close"], frames["ETH"]["close"]
    for n in (6, 12, 24):
        btc_up = (btc_c.pct_change(n) > 0).shift(1)   # causal
        eth_up = (eth_c.pct_change(n) > 0).shift(1)
        agree_up = (btc_up & eth_up)
        gt = {}
        for s, t in targets.items():
            ok = agree_up.reindex(t.index).fillna(False).to_numpy()
            gt[s] = t.where([(ok[i]) or (t.iloc[i] <= 0) for i in range(len(t))], 0.0)
        m = _oos_sharpe(frames, gt, momentum, cfg)
        lines.append(f"| BTC&ETH both up over {n} bars | {m['sharpe']:.2f} | {m['win_rate']*100:.1f}% | "
                     f"{m['cagr']*100:.1f}% |")

    lines += ["", "## Read", "",
              "Compare each filtered row to baseline. A filter only 'earns its keep' if OOS "
              "Sharpe rises meaningfully without just collapsing trade count. (Session/valuation "
              "are regime-level filters, unlike the per-trade ML gate that hurt the book.)"]
    report = "\n".join(lines)
    print("\n" + report)
    out = root / "reports_out" / "winc_tests.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(report)
    print(f"\nSaved -> {out}")


if __name__ == "__main__":
    main()
