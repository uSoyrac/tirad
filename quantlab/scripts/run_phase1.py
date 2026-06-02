"""Phase 1 end-to-end: signal ensemble vs the Phase 0 floors.

Loads config -> data -> train/OOS split -> runs Buy&Hold, the Supertrend floor, and
the weighted Ensemble through the SAME honest harness on both windows -> prints a
side-by-side report AND an explicit "did the added complexity earn its keep?" verdict
based on OOS numbers (never in-sample).

Usage: python scripts/run_phase1.py [path/to/config.yaml]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quantlab.config import load_config  # noqa: E402
from quantlab.data import cache  # noqa: E402
from quantlab.backtest import metrics, splits  # noqa: E402
from quantlab.backtest.harness import run_backtest  # noqa: E402
from quantlab.baselines import buy_and_hold, single_indicator  # noqa: E402
from quantlab.signals import ensemble  # noqa: E402
from quantlab.reports.report import render_report  # noqa: E402


def _m(equity, trades, tf, cfg):
    return metrics.compute_metrics(
        equity, trades, timeframe=tf,
        ruin_drawdown=cfg.risk.total_dd_killswitch, seed=cfg.seed,
    )


def _verdict(floor: dict, ens: dict) -> str:
    """Honest read on OOS lift vs the Supertrend floor."""
    lines = ["## Did the ensemble earn its keep? (OOS, vs Supertrend floor)", ""]
    for key, label in [("expectancy_pct", "Expectancy/trade"),
                       ("total_return", "Total return"),
                       ("sharpe", "Sharpe"),
                       ("max_drawdown", "Max drawdown")]:
        fv, ev = floor.get(key), ens.get(key)
        if fv is None or ev is None or fv != fv or ev != ev:
            lines.append(f"- {label}: floor=n/a ens=n/a")
            continue
        delta = ev - fv
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
        lines.append(f"- {label}: floor={fv:.4f} → ensemble={ev:.4f}  ({arrow} {delta:+.4f})")
    better_exp = ens.get("expectancy_pct", float("-inf")) > floor.get("expectancy_pct", float("-inf"))
    pos_exp = ens.get("expectancy_pct", -1) > 0
    lines.append("")
    if pos_exp and better_exp:
        lines.append("**Verdict:** ensemble has POSITIVE OOS expectancy and beats the floor — complexity justified so far.")
    elif better_exp:
        lines.append("**Verdict:** ensemble beats the floor on OOS expectancy but is still NOT positive — improvement, not yet an edge.")
    else:
        lines.append("**Verdict:** ensemble does NOT beat the floor on OOS expectancy — added complexity did not earn its keep.")
    return "\n".join(lines)


def main(config_path: str) -> None:
    cfg = load_config(config_path)
    root = Path(config_path).resolve().parent.parent
    cache_dir = root / cfg.data.cache_dir
    seed_csv = (root / cfg.data.seed_csv).resolve() if cfg.data.seed_csv else None

    tf = cfg.data.primary_tf
    df = cache.load_ohlcv(cfg.data.symbol, tf, cache_dir=cache_dir,
                          start=cfg.data.start, end=cfg.data.end, seed_csv=seed_csv)
    print(f"Loaded {len(df)} {tf} bars: {df.index[0]} -> {df.index[-1]}")

    train, oos = splits.train_oos_split(df, cfg.splits.train_end)
    print(f"In-sample: {len(train)} bars | OOS: {len(oos)} bars")

    sections = []
    oos_cols = {}
    for win_name, wdf in [("In-sample", train), ("Out-of-sample", oos)]:
        bh = buy_and_hold.run(wdf, cfg)
        floor = run_backtest(wdf, single_indicator.signal(wdf, cfg), cfg)
        ens = run_backtest(wdf, ensemble.signal(wdf, cfg), cfg)
        cols = {
            "Buy & Hold": _m(bh.equity, bh.trades, tf, cfg),
            "Supertrend floor": _m(floor.equity, floor.trades, tf, cfg),
            "Ensemble": _m(ens.equity, ens.trades, tf, cfg),
        }
        sections.append((f"{win_name}  ({wdf.index[0].date()} → {wdf.index[-1].date()})", cols))
        if win_name == "Out-of-sample":
            oos_cols = cols

    report = render_report(f"Phase 1 ensemble — {cfg.data.symbol} {tf} ({cfg.data.market_type})",
                           sections)
    report += "\n\n" + _verdict(oos_cols["Supertrend floor"], oos_cols["Ensemble"]) + "\n"
    print("\n" + report)

    out_dir = root / "reports_out"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "phase1_ensemble.md"
    out_path.write_text(report)
    print(f"\nSaved report -> {out_path}")


if __name__ == "__main__":
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).resolve().parents[1] / "config" / "default.yaml")
    main(cfg_path)
