"""Phase 2 end-to-end: regime + multi-timeframe filters vs the Phase 1 ensemble.

The only difference between the 'Ensemble' and 'Ensemble + Filters' columns is the
regime/MTF gating, so the side-by-side shows exactly what the filters bought us.
Signals are computed on full history then sliced per window (consistent warm-up).

Usage: python scripts/run_phase2.py [path/to/config.yaml]
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
from quantlab import orchestrator  # noqa: E402
from quantlab.reports.report import render_report  # noqa: E402


def _m(equity, trades, tf, cfg):
    return metrics.compute_metrics(equity, trades, timeframe=tf,
                                   ruin_drawdown=cfg.risk.total_dd_killswitch, seed=cfg.seed)


def _verdict(prev: dict, new: dict, prev_name: str) -> str:
    lines = [f"## Did the filters earn their keep? (OOS, vs {prev_name})", ""]
    for key, label in [("expectancy_pct", "Expectancy/trade"), ("total_return", "Total return"),
                       ("sharpe", "Sharpe"), ("max_drawdown", "Max drawdown"),
                       ("risk_of_ruin", "Risk of ruin"), ("n_trades", "Trades")]:
        pv, nv = prev.get(key), new.get(key)
        if pv is None or nv is None or pv != pv or nv != nv:
            lines.append(f"- {label}: n/a")
            continue
        d = nv - pv
        arrow = "↑" if d > 0 else ("↓" if d < 0 else "→")
        lines.append(f"- {label}: {pv:.4f} → {nv:.4f}  ({arrow} {d:+.4f})")
    better = new.get("expectancy_pct", -9) > prev.get("expectancy_pct", -9)
    pos = new.get("expectancy_pct", -1) > 0
    lines.append("")
    if pos and better:
        lines.append("**Verdict:** filters produce POSITIVE OOS expectancy and beat the unfiltered ensemble — complexity justified.")
    elif better:
        lines.append("**Verdict:** filters improve OOS expectancy but it is still NOT positive — progress, not yet an edge.")
    else:
        lines.append("**Verdict:** filters do NOT improve OOS expectancy — they did not earn their keep here.")
    return "\n".join(lines)


def main(config_path: str) -> None:
    cfg = load_config(config_path)
    root = Path(config_path).resolve().parent.parent
    cache_dir = root / cfg.data.cache_dir
    seed_csv = (root / cfg.data.seed_csv).resolve() if cfg.data.seed_csv else None

    tf = cfg.data.primary_tf
    df = cache.load_ohlcv(cfg.data.symbol, tf, cache_dir=cache_dir,
                          start=cfg.data.start, end=cfg.data.end, seed_csv=seed_csv)
    higher_df = cache.load_ohlcv(cfg.data.symbol, cfg.mtf.higher_tf, cache_dir=cache_dir,
                                 start=cfg.data.start, end=cfg.data.end, seed_csv=seed_csv)
    print(f"Loaded {len(df)} {tf} bars and {len(higher_df)} {cfg.mtf.higher_tf} bars")

    # Full-history signals (causal) -> slice per window so warm-up is consistent.
    sig_floor = single_indicator.signal(df, cfg)
    sig_ens = ensemble.signal(df, cfg)
    sig_filt = orchestrator.build_target(df, cfg, higher_df)

    train, oos = splits.train_oos_split(df, cfg.splits.train_end)
    sections, oos_cols = [], {}
    for win_name, wdf in [("In-sample", train), ("Out-of-sample", oos)]:
        idx = wdf.index
        bh = buy_and_hold.run(wdf, cfg)
        floor = run_backtest(wdf, sig_floor.reindex(idx), cfg)
        ens = run_backtest(wdf, sig_ens.reindex(idx), cfg)
        filt = run_backtest(wdf, sig_filt.reindex(idx), cfg)
        cols = {
            "Buy & Hold": _m(bh.equity, bh.trades, tf, cfg),
            "Supertrend floor": _m(floor.equity, floor.trades, tf, cfg),
            "Ensemble": _m(ens.equity, ens.trades, tf, cfg),
            "Ensemble + Filters": _m(filt.equity, filt.trades, tf, cfg),
        }
        sections.append((f"{win_name}  ({idx[0].date()} → {idx[-1].date()})", cols))
        if win_name == "Out-of-sample":
            oos_cols = cols

    report = render_report(
        f"Phase 2 regime + MTF filters — {cfg.data.symbol} {tf} ({cfg.data.market_type})", sections)
    report += "\n\n" + _verdict(oos_cols["Ensemble"], oos_cols["Ensemble + Filters"], "Ensemble") + "\n"
    print("\n" + report)

    out_dir = root / "reports_out"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "phase2_filters.md"
    out_path.write_text(report)
    print(f"\nSaved report -> {out_path}")


if __name__ == "__main__":
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).resolve().parents[1] / "config" / "default.yaml")
    main(cfg_path)
