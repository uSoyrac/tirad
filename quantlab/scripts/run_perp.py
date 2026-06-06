"""Perp track: does allowing shorts (with real funding) beat long-only in the OOS
downtrend? Runs Ensemble+Filters on a perp config with historical funding and a
liquidation-aware harness, IS vs OOS, and breaks down long- vs short-trade P&L.

Usage: python scripts/run_perp.py [path/to/perp.yaml]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from quantlab.config import load_config  # noqa: E402
from quantlab.data import cache, funding as fundmod  # noqa: E402
from quantlab.backtest import metrics, splits  # noqa: E402
from quantlab.backtest.harness import run_backtest  # noqa: E402
from quantlab.baselines import buy_and_hold  # noqa: E402
from quantlab import orchestrator  # noqa: E402
from quantlab.reports.report import render_report  # noqa: E402


def _m(equity, trades, tf, cfg):
    return metrics.compute_metrics(equity, trades, timeframe=tf,
                                   ruin_drawdown=cfg.risk.total_dd_killswitch, seed=cfg.seed)


def _side_breakdown(trades) -> str:
    longs = [t for t in trades if t.side > 0]
    shorts = [t for t in trades if t.side < 0]

    def line(name, ts):
        if not ts:
            return f"  - {name}: 0 trades"
        pnl = np.array([t.pnl for t in ts])
        wr = float((pnl > 0).mean())
        return (f"  - {name}: {len(ts)} trades, win {wr*100:.1f}%, "
                f"expectancy {pnl.mean():+.2f}$/trade, total {pnl.sum():+.0f}$")
    return "\n".join([line("Longs", longs), line("Shorts", shorts)])


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
    funding = fundmod.load_funding((root / ".." / "uyg/src/funddata/BTC_funding.csv").resolve())
    print(f"Loaded {len(df)} {tf} bars, {len(higher_df)} {cfg.mtf.higher_tf} bars, "
          f"{len(funding)} funding points ({funding.index[0].date()}→{funding.index[-1].date()})")

    target = orchestrator.build_target(df, cfg, higher_df)  # perp => long + short

    train, oos = splits.train_oos_split(df, cfg.splits.train_end)
    sections, breakdowns = [], {}
    for win_name, wdf in [("In-sample", train), ("Out-of-sample", oos)]:
        idx = wdf.index
        bh = buy_and_hold.run(wdf, cfg)
        res = run_backtest(wdf, target.reindex(idx), cfg, funding_rates=funding)
        cols = {
            "Buy & Hold": _m(bh.equity, bh.trades, tf, cfg),
            "Ens+Filters (perp L/S)": _m(res.equity, res.trades, tf, cfg),
        }
        sections.append((f"{win_name}  ({idx[0].date()} → {idx[-1].date()})", cols))
        breakdowns[win_name] = (cols["Ens+Filters (perp L/S)"], res.trades)

    report = render_report(
        f"Perp track — {cfg.data.symbol} {tf} (perp, long+short, historical funding)", sections)

    report += "\n\n## Long vs short breakdown (the hypothesis test)\n"
    for win_name in ("In-sample", "Out-of-sample"):
        report += f"\n**{win_name}:**\n{_side_breakdown(breakdowns[win_name][1])}\n"

    oos_m = breakdowns["Out-of-sample"][0]
    oos_exp = oos_m.get("expectancy_pct", float("nan"))
    report += "\n## Verdict (OOS)\n\n"
    if oos_exp > 0:
        report += (f"**Shorting flips the system positive OOS** (expectancy {oos_exp:+.4f}/trade). "
                   "The downtrend that sank long-only spot is now tradable. Validate further "
                   "(funding sensitivity, other symbols, paper) before trusting.")
    else:
        report += (f"**Still negative OOS** (expectancy {oos_exp:+.4f}/trade). Shorting did not "
                   "rescue it — see the long/short breakdown for where the bleed is.")
    report += "\n"
    print("\n" + report)

    out_dir = root / "reports_out"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "perp_track.md").write_text(report)
    print(f"\nSaved report -> {out_dir / 'perp_track.md'}")


if __name__ == "__main__":
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).resolve().parents[1] / "config" / "perp.yaml")
    main(cfg_path)
