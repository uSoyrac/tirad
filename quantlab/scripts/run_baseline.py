"""Phase 0 end-to-end entrypoint.

Loads config -> loads cached OHLCV -> splits into in-sample / OOS -> runs the
buy-and-hold benchmark and the Supertrend single-indicator baseline through the
honest harness on BOTH windows -> prints and saves a side-by-side report.

Usage:
    python scripts/run_baseline.py [path/to/config.yaml]
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the package importable when run as a plain script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quantlab.config import load_config  # noqa: E402
from quantlab.data import cache  # noqa: E402
from quantlab.backtest import metrics, splits  # noqa: E402
from quantlab.backtest.harness import run_backtest  # noqa: E402
from quantlab.baselines import buy_and_hold, single_indicator  # noqa: E402
from quantlab.reports.report import render_report  # noqa: E402


def _metrics_for(equity, trades, tf, cfg):
    return metrics.compute_metrics(
        equity, trades, timeframe=tf,
        ruin_drawdown=cfg.risk.total_dd_killswitch, seed=cfg.seed,
    )


def main(config_path: str) -> None:
    cfg = load_config(config_path)
    root = Path(config_path).resolve().parent.parent  # quantlab/
    cache_dir = root / cfg.data.cache_dir
    # seed_csv in the config is relative to the package root (quantlab/).
    seed_csv = (root / cfg.data.seed_csv).resolve() if cfg.data.seed_csv else None

    tf = cfg.data.primary_tf
    df = cache.load_ohlcv(
        cfg.data.symbol, tf,
        cache_dir=cache_dir, start=cfg.data.start, end=cfg.data.end, seed_csv=seed_csv,
    )
    print(f"Loaded {len(df)} {tf} bars: {df.index[0]} -> {df.index[-1]}")

    train, oos = splits.train_oos_split(df, cfg.splits.train_end)
    print(f"In-sample: {len(train)} bars (<= {cfg.splits.train_end}) | "
          f"OOS: {len(oos)} bars (> {cfg.splits.train_end})")

    sections = []
    for win_name, wdf in [("In-sample", train), ("Out-of-sample", oos)]:
        bh = buy_and_hold.run(wdf, cfg)
        sig = single_indicator.signal(wdf, cfg)
        st = run_backtest(wdf, sig, cfg)
        cols = {
            "Buy & Hold": _metrics_for(bh.equity, bh.trades, tf, cfg),
            "Supertrend": _metrics_for(st.equity, st.trades, tf, cfg),
        }
        sections.append((f"{win_name}  ({wdf.index[0].date()} → {wdf.index[-1].date()})", cols))

    report = render_report(
        f"Phase 0 baseline — {cfg.data.symbol} {tf} ({cfg.data.market_type})", sections
    )
    print("\n" + report)

    out_dir = root / "reports_out"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "phase0_baseline.md"
    out_path.write_text(report)
    print(f"\nSaved report -> {out_path}")


if __name__ == "__main__":
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).resolve().parents[1] / "config" / "default.yaml"
    )
    main(cfg_path)
