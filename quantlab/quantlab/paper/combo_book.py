"""Paper-trading book for the diversified combo (trend Top-3 + funding-positioning).

NO live orders. Builds the combo's realized daily-return series (same construction as
the validated backtest: inverse-vol weights fit on TRAIN, applied forward), tracks a
NAV ledger from the OOS start to the latest bar, and reports the CURRENT target
holdings (what to hold next) for both sleeves. Re-run as new bars arrive: the NAV
extends and the holdings refresh — accumulating a forward, survivorship-free record.

Faithfulness: the ledger NAV over OOS equals the combo backtest equity (a test asserts
the endpoints match), so the paper book is the same edge, tracked live.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ..config import BacktestConfig
from ..backtest import combine
from ..backtest.portfolio import run_portfolio
from ..backtest.carry import run_carry
from .engine import live_targets


def build_book(frames: dict, fundings: dict, cfg: BacktestConfig,
               top_k: int = 3, lookback_days: int = 7, n_side: int = 3) -> dict:
    """Compute the combo NAV series + current target holdings. Pure (no I/O)."""
    cut = pd.Timestamp(cfg.splits.train_end) + pd.Timedelta(days=1)
    trend = run_portfolio(frames, targets_from(frames, cfg), {s: frames[s]["close"].pct_change(60)
                                                              for s in frames}, cfg, top_k=top_k)
    carry = run_carry(frames, fundings, cfg, lookback_days=lookback_days, n_side=n_side,
                      rebalance_days=1)
    rt = combine.equity_to_daily_returns(trend.equity)
    rc = carry.daily_returns
    rt, rc = combine.align(rt, rc)
    wt, wc = combine.inverse_vol_weights(rt[rt.index < cut], rc[rc.index < cut])
    combo = combine.blend(rt, rc, wt, wc)

    oos = combo[combo.index >= cut]
    nav = cfg.risk.bankroll * (1.0 + oos).cumprod()

    # current target holdings (decided on the latest closed bar)
    trend_longs = live_targets(frames, cfg, top_k=top_k, mom_window=60)
    score = {s: fundings[s].tail(3 * lookback_days).mean() for s in fundings}
    ranked = sorted(score, key=score.get)
    as_of = max(f.index[-1] for f in frames.values())

    from ..backtest import metrics
    m = metrics.compute_metrics(nav, [], timeframe="1d") if len(nav) > 2 else {}
    return {
        "as_of": str(as_of),
        "weights": {"trend": round(wt, 3), "funding": round(wc, 3)},
        "holdings": {
            "trend_long": trend_longs,
            "funding_long": list(ranked[:n_side]),
            "funding_short": list(ranked[-n_side:]),
        },
        "nav_start": float(nav.iloc[0]) if len(nav) else cfg.risk.bankroll,
        "nav_now": float(nav.iloc[-1]) if len(nav) else cfg.risk.bankroll,
        "oos_sharpe_to_date": round(float(m.get("sharpe", float("nan"))), 2),
        "oos_maxdd_to_date": round(float(m.get("max_drawdown", float("nan"))), 3),
        "nav_series": {str(k.date()): round(float(v), 2) for k, v in nav.items()},
    }


def targets_from(frames: dict, cfg: BacktestConfig) -> dict:
    """Build per-coin trend targets (ensemble + regime/MTF) for the trend sleeve."""
    from .. import orchestrator
    out = {}
    for s, df in frames.items():
        hd = df.resample("1D", label="left", closed="left").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
        ).dropna()
        out[s] = orchestrator.build_target(df, cfg, hd)
    return out


def save_ledger(book: dict, path: str | Path) -> None:
    Path(path).write_text(json.dumps(book, indent=2))
