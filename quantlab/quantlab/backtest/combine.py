"""Combine two return streams into a diversified book.

The only 'free lunch' in finance: blending two edges with low correlation lifts the
risk-adjusted return above either alone. We size by INVERSE VOLATILITY estimated on
the TRAINING window only (equal risk budget if uncorrelated), then apply those fixed
weights out-of-sample — no OOS fitting, so the diversification benefit can't be faked.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def equity_to_daily_returns(equity: pd.Series) -> pd.Series:
    """Daily simple returns from an equity curve (any intraday grid)."""
    daily = equity.resample("1D", label="left", closed="left").last()
    return daily.pct_change().dropna()


def align(a: pd.Series, b: pd.Series) -> tuple[pd.Series, pd.Series]:
    idx = a.index.intersection(b.index)
    return a.reindex(idx), b.reindex(idx)


def inverse_vol_weights(ret_a: pd.Series, ret_b: pd.Series) -> tuple[float, float]:
    """Weights ∝ 1/vol, normalised to sum 1. Robust, no return-forecasting."""
    va, vb = ret_a.std(), ret_b.std()
    if not (va > 0) or not (vb > 0):
        return 0.5, 0.5
    ia, ib = 1.0 / va, 1.0 / vb
    return ia / (ia + ib), ib / (ia + ib)


def blend(ret_a: pd.Series, ret_b: pd.Series, w_a: float, w_b: float) -> pd.Series:
    a, b = align(ret_a, ret_b)
    return (w_a * a + w_b * b).rename("combined")


def equity_from_returns(returns: pd.Series, bankroll: float) -> pd.Series:
    return (bankroll * (1.0 + returns).cumprod()).rename("equity")


def correlation(ret_a: pd.Series, ret_b: pd.Series) -> float:
    a, b = align(ret_a, ret_b)
    if len(a) < 3:
        return float("nan")
    return float(np.corrcoef(a.fillna(0.0), b.fillna(0.0))[0, 1])
