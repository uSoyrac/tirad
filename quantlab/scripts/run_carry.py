"""Funding-carry backtest runner — the orthogonal-edge hunt.

Loads 20 coins' 4h OHLCV + 8h funding, runs the market-neutral cross-sectional carry
strategy, and reports: IS vs OOS metrics, the price/funding/cost DECOMPOSITION (so we
know if any edge is real funding harvest or price luck), a parameter sweep, and an
exchange comparison (binance/bybit/okx funding). Costs included.

Usage: python scripts/run_carry.py [config.yaml] [exchange]   exchange in {binance,bybit,okx}
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from quantlab.config import load_config  # noqa: E402
from quantlab.data import cache, funding as fundmod  # noqa: E402
from quantlab.backtest import metrics  # noqa: E402
from quantlab.backtest.carry import run_carry  # noqa: E402

MKTDATA = Path("../uyg/src/mktdata")
FUND_BINANCE = Path("../uyg/src/funddata")
FUND_X = Path("../uyg/src/xfunddata")
UNIVERSE = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LTC", "ATOM", "DOT",
            "LINK", "DOGE", "ETC", "FIL", "INJ", "NEAR", "UNI", "APT", "ARB", "OP"]


def _funding_path(root, exch, sym):
    if exch == "binance":
        return (root / FUND_BINANCE / f"{sym}_funding.csv").resolve()
    return (root / FUND_X / f"{exch}_{sym}_funding.csv").resolve()


def _load(cfg, root, exch):
    frames, fundings = {}, {}
    for sym in UNIVERSE:
        csv = (root / MKTDATA / f"{sym}_USDT_4h.csv").resolve()
        fpath = _funding_path(root, exch, sym)
        if not csv.exists() or not fpath.exists():
            continue
        frames[sym] = cache.load_ohlcv(f"{sym}/USDT", "4h", cache_dir=root / cfg.data.cache_dir,
                                       start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
        fundings[sym] = fundmod.load_funding(fpath)
    return frames, fundings


def _m(res, cut, win):
    eq = res.equity[res.equity.index < cut] if win == "is" else res.equity[res.equity.index >= cut]
    if len(eq) < 5:
        return None
    return metrics.compute_metrics(eq, [], timeframe="1d")


def main(config_path: str, exch: str) -> None:
    cfg = load_config(config_path)
    root = Path(config_path).resolve().parent.parent
    cut = pd.Timestamp(cfg.splits.train_end) + pd.Timedelta(days=1)
    frames, fundings = _load(cfg, root, exch)
    print(f"Loaded {len(frames)} coins with {exch} funding.")

    base = run_carry(frames, fundings, cfg, lookback_days=7, n_side=3, rebalance_days=1)
    is_m, oos_m = _m(base, cut, "is"), _m(base, cut, "oos")

    lines = [f"# Funding-carry (market-neutral X-sectional) — {exch}, {len(frames)} coins", "",
             "Base config: lookback 7d, n_side 3 (3 long / 3 short), daily rebalance, "
             f"costs taker {cfg.costs.taker_fee*1e4:.0f}bps + slip {cfg.costs.slippage_bps:.0f}bps.", ""]

    lines += ["## In-sample vs OOS (base config)", "",
              "| Metric | In-sample | Out-of-sample |", "|---|---|---|"]
    for key, label, pct in [("total_return", "Total return", True), ("cagr", "CAGR", True),
                            ("sharpe", "Sharpe", False), ("sortino", "Sortino", False),
                            ("max_drawdown", "Max drawdown", True)]:
        iv = is_m[key] if is_m else float("nan")
        ov = oos_m[key] if oos_m else float("nan")
        fmt = (lambda x: f"{x*100:.1f}%") if pct else (lambda x: f"{x:.2f}")
        lines.append(f"| {label} | {fmt(iv)} | {fmt(ov)} |")

    # decomposition over full history
    lines += ["", "## P&L decomposition (full history, fraction of equity, cumulative)", "",
              f"- Funding harvest: {base.funding_pnl.iloc[-1]*100:+.1f}%",
              f"- Price P&L:       {base.price_pnl.iloc[-1]*100:+.1f}%",
              f"- Cost drag:       {base.cost_pnl.iloc[-1]*100:+.1f}%",
              "(If the edge is real carry, funding harvest should be the positive driver; "
              "if price P&L dominates, it's directional luck, not carry.)"]

    # parameter sweep (OOS Sharpe)
    lines += ["", "## Parameter sweep — OOS Sharpe / OOS total return", "",
              "| lookback\\n_side | n=3 | n=5 |", "|---|---|---|"]
    for lb in (3, 7, 14, 30):
        row = [f"| {lb}d"]
        for n in (3, 5):
            r = run_carry(frames, fundings, cfg, lookback_days=lb, n_side=n, rebalance_days=1)
            m = _m(r, cut, "oos")
            row.append(f"{m['sharpe']:.2f} / {m['total_return']*100:.0f}%" if m else "n/a")
        lines.append(" | ".join(row) + " |")

    report = "\n".join(lines)
    print("\n" + report)
    out_dir = root / "reports_out"
    out_dir.mkdir(exist_ok=True)
    (out_dir / f"carry_{exch}.md").write_text(report)
    print(f"\nSaved report -> {out_dir / f'carry_{exch}.md'}")


if __name__ == "__main__":
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).resolve().parents[1] / "config" / "default.yaml")
    exchange = sys.argv[2] if len(sys.argv) > 2 else "binance"
    main(cfg_path, exchange)
