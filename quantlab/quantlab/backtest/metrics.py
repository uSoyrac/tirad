"""Honest metrics. Report the bad numbers too.

Every backtest result is summarised by the same block so in-sample and
out-of-sample runs are directly comparable. Risk-of-ruin is a Monte-Carlo
bootstrap of the realised per-trade return distribution — labelled as such,
not a closed-form fantasy.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .harness import Trade

_PERIODS_PER_YEAR = {"1h": 24 * 365, "4h": 6 * 365, "1d": 365, "1w": 52}


def periods_per_year(timeframe: str) -> int:
    return _PERIODS_PER_YEAR.get(timeframe, 365)


def max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    return float((equity / peak - 1.0).min())


def _longest_losing_streak(trades: list[Trade]) -> int:
    longest = cur = 0
    for t in trades:
        if t.pnl < 0:
            cur += 1
            longest = max(longest, cur)
        else:
            cur = 0
    return longest


def risk_of_ruin(
    trades: list[Trade],
    *,
    ruin_drawdown: float,
    seed: int = 42,
    n_paths: int = 5000,
) -> float:
    """P(equity falls by >= ruin_drawdown from its running peak) via bootstrap.

    Resamples the realised per-trade returns (with replacement) into many paths of
    the same length, compounds them, and measures how often the path breaches the
    ruin drawdown. Needs a meaningful trade count to be trustworthy.
    """
    rets = np.array([t.return_pct for t in trades], dtype=float)
    if len(rets) < 5:
        return float("nan")
    rng = np.random.default_rng(seed)
    n = len(rets)
    ruined = 0
    for _ in range(n_paths):
        sample = rng.choice(rets, size=n, replace=True)
        eq = np.cumprod(1.0 + sample)
        peak = np.maximum.accumulate(eq)
        if (eq / peak - 1.0).min() <= -ruin_drawdown:
            ruined += 1
    return ruined / n_paths


def compute_metrics(
    equity: pd.Series,
    trades: list[Trade],
    *,
    timeframe: str,
    ruin_drawdown: float = 0.25,
    seed: int = 42,
) -> dict:
    out: dict = {}
    if len(equity) < 2:
        return {"error": "equity series too short"}

    start_eq, end_eq = float(equity.iloc[0]), float(equity.iloc[-1])
    out["start_equity"] = start_eq
    out["end_equity"] = end_eq
    out["total_return"] = end_eq / start_eq - 1.0

    days = max((equity.index[-1] - equity.index[0]).days, 1)
    years = days / 365.25
    out["cagr"] = (end_eq / start_eq) ** (1.0 / years) - 1.0 if start_eq > 0 else float("nan")

    bar_ret = equity.pct_change().dropna()
    ppy = periods_per_year(timeframe)
    if bar_ret.std(ddof=1) > 0:
        out["sharpe"] = float(bar_ret.mean() / bar_ret.std(ddof=1) * math.sqrt(ppy))
    else:
        out["sharpe"] = float("nan")
    downside = bar_ret[bar_ret < 0]
    if len(downside) > 1 and downside.std(ddof=1) > 0:
        out["sortino"] = float(bar_ret.mean() / downside.std(ddof=1) * math.sqrt(ppy))
    else:
        out["sortino"] = float("nan")

    out["max_drawdown"] = max_drawdown(equity)

    pnls = np.array([t.pnl for t in trades], dtype=float)
    out["n_trades"] = len(trades)
    if len(trades):
        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]
        out["win_rate"] = len(wins) / len(trades)
        out["avg_win"] = float(wins.mean()) if len(wins) else 0.0
        out["avg_loss"] = float(losses.mean()) if len(losses) else 0.0
        out["expectancy"] = float(pnls.mean())  # avg net P&L per trade, in currency
        out["expectancy_pct"] = float(np.mean([t.return_pct for t in trades]))
        out["payoff_ratio"] = (
            abs(out["avg_win"] / out["avg_loss"]) if out["avg_loss"] != 0 else float("inf")
        )
        out["longest_losing_streak"] = _longest_losing_streak(trades)
    else:
        for k in ("win_rate", "avg_win", "avg_loss", "expectancy", "expectancy_pct",
                  "payoff_ratio", "longest_losing_streak"):
            out[k] = 0.0

    out["risk_of_ruin"] = risk_of_ruin(trades, ruin_drawdown=ruin_drawdown, seed=seed)
    return out
