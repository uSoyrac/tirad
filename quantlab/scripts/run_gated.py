"""Wire the pooled meta-label quality gate into the trend sleeve and re-measure.

Compares OOS: trend portfolio ungated vs gated, and the diversified combo (trend +
funding) ungated vs gated. Answers the open question: does the label-level
decision-quality lift translate into a real portfolio Sharpe lift OOS?

Usage: python scripts/run_gated.py [config.yaml] [keep_top]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from quantlab.config import load_config  # noqa: E402
from quantlab.data import cache, funding as fundmod  # noqa: E402
from quantlab.backtest import metrics, combine  # noqa: E402
from quantlab.backtest.portfolio import run_portfolio  # noqa: E402
from quantlab.backtest.carry import run_carry  # noqa: E402
from quantlab import orchestrator  # noqa: E402
from quantlab.ml import quality_gate  # noqa: E402

MKTDATA = Path("../uyg/src/mktdata")
FUND = Path("../uyg/src/funddata")
UNIVERSE = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LTC", "ATOM", "DOT",
            "LINK", "DOGE", "ETC", "FIL", "INJ", "NEAR", "UNI", "APT", "ARB", "OP"]
MOM_WINDOW = 60


def _oos(equity_or_ret, cut, cfg, is_ret=False):
    if is_ret:
        r = equity_or_ret[equity_or_ret.index >= cut]
        eq = combine.equity_from_returns(r, cfg.risk.bankroll)
    else:
        eq = equity_or_ret[equity_or_ret.index >= cut]
    return metrics.compute_metrics(eq, [], timeframe="1d" if is_ret else "4h")


def main(config_path: str, keep_top: float) -> None:
    cfg = load_config(config_path)
    root = Path(config_path).resolve().parent.parent
    cut = pd.Timestamp(cfg.splits.train_end) + pd.Timedelta(days=1)

    frames, higher, targets, momentum, fundings = {}, {}, {}, {}, {}
    for sym in UNIVERSE:
        csv = (root / MKTDATA / f"{sym}_USDT_4h.csv").resolve()
        fp = (root / FUND / f"{sym}_funding.csv").resolve()
        if not (csv.exists() and fp.exists()):
            continue
        df = cache.load_ohlcv(f"{sym}/USDT", "4h", cache_dir=root / cfg.data.cache_dir,
                              start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
        hd = cache.load_ohlcv(f"{sym}/USDT", "1d", cache_dir=root / cfg.data.cache_dir,
                              start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
        frames[sym], higher[sym] = df, hd
        targets[sym] = orchestrator.build_target(df, cfg, hd)
        momentum[sym] = df["close"].pct_change(MOM_WINDOW)
        fundings[sym] = fundmod.load_funding(fp)
    print(f"Loaded {len(frames)} coins. Training quality gate (keep top {keep_top:.0%})...")

    model, thr = quality_gate.train_gate(frames, higher, cfg, keep_top=keep_top)
    gated = quality_gate.gate_targets(frames, higher, targets, model, thr, cfg)

    # trend sleeve: ungated vs gated
    tr_un = run_portfolio(frames, targets, momentum, cfg, top_k=3)
    tr_ga = run_portfolio(frames, gated, momentum, cfg, top_k=3)
    m_un, m_ga = _oos(tr_un.equity, cut, cfg), _oos(tr_ga.equity, cut, cfg)

    # combo: blend each trend variant with the funding sleeve (train-fit inverse-vol)
    carry = run_carry(frames, fundings, cfg, lookback_days=7, n_side=3, rebalance_days=1)
    rc = carry.daily_returns

    def combo_oos(trend_equity):
        rt = combine.equity_to_daily_returns(trend_equity)
        rt, rcc = combine.align(rt, rc)
        wt, wc = combine.inverse_vol_weights(rt[rt.index < cut], rcc[rcc.index < cut])
        cb = combine.blend(rt[rt.index >= cut], rcc[rcc.index >= cut], wt, wc)
        return metrics.compute_metrics(combine.equity_from_returns(cb, cfg.risk.bankroll),
                                       [], timeframe="1d")

    cm_un, cm_ga = combo_oos(tr_un.equity), combo_oos(tr_ga.equity)

    lines = ["# Quality-gated trend sleeve — OOS re-measurement", "",
             f"Gate: pooled meta-label, keep top {keep_top:.0%} by P(win), threshold {thr:.3f}. "
             f"Trained ≤{cfg.splits.train_end}, OOS after.", "",
             "## Trend sleeve (Top-3 cross-sectional), OOS", "",
             "| Metric | Ungated | Gated |", "|---|---|---|",
             f"| Sharpe | {m_un['sharpe']:.2f} | {m_ga['sharpe']:.2f} |",
             f"| CAGR | {m_un['cagr']*100:.1f}% | {m_ga['cagr']*100:.1f}% |",
             f"| Max drawdown | {m_un['max_drawdown']*100:.1f}% | {m_ga['max_drawdown']*100:.1f}% |",
             f"| Total return | {m_un['total_return']*100:.1f}% | {m_ga['total_return']*100:.1f}% |",
             "", "## Diversified combo (trend + funding), OOS", "",
             "| Metric | Ungated trend | Gated trend |", "|---|---|---|",
             f"| Sharpe | {cm_un['sharpe']:.2f} | {cm_ga['sharpe']:.2f} |",
             f"| CAGR | {cm_un['cagr']*100:.1f}% | {cm_ga['cagr']*100:.1f}% |",
             f"| Max drawdown | {cm_un['max_drawdown']*100:.1f}% | {cm_ga['max_drawdown']*100:.1f}% |", ""]
    lift = cm_ga["sharpe"] - cm_un["sharpe"]
    lines += ["## Verdict", ""]
    if lift > 0.05:
        lines.append(f"**Gate earns its keep:** combined OOS Sharpe {cm_un['sharpe']:.2f}→"
                     f"{cm_ga['sharpe']:.2f} ({lift:+.2f}); label-level decision-quality lift "
                     "DOES translate to the portfolio. Lower drawdown too if shown above.")
    elif lift > -0.05:
        lines.append(f"**Neutral:** combined OOS Sharpe {cm_un['sharpe']:.2f}→{cm_ga['sharpe']:.2f} "
                     f"({lift:+.2f}); the gate raises per-trade quality but trades less, so the "
                     "portfolio Sharpe is ~unchanged. Useful for capital efficiency, not raw Sharpe.")
    else:
        lines.append(f"**Gate hurts the portfolio:** OOS Sharpe {cm_un['sharpe']:.2f}→"
                     f"{cm_ga['sharpe']:.2f} ({lift:+.2f}) — fewer trades cut winners too; "
                     "the label-level lift did not survive portfolio construction.")

    report = "\n".join(lines)
    print("\n" + report)
    out_dir = root / "reports_out"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "gated.md").write_text(report)
    print(f"\nSaved report -> {out_dir / 'gated.md'}")


if __name__ == "__main__":
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).resolve().parents[1] / "config" / "default.yaml")
    kt = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
    main(cfg_path, kt)
