"""Mean-reversion sleeve — the counter-trend complement for chop regimes.

z = (close - SMA) / rolling_std  (causal). Fade extremes: when z falls below
-entry_z the price is stretched DOWN → go long expecting reversion; hold until z
recovers above -exit_z. On perp, symmetrically short stretched-UP extremes. The
signal is a stateful target (enter on extreme, hold until reverted), the same shape
the harness consumes for the trend sleeve.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import BacktestConfig


def zscore(close: pd.Series, period: int) -> pd.Series:
    ma = close.rolling(period).mean()
    sd = close.rolling(period).std(ddof=0)
    return ((close - ma) / sd.replace(0.0, np.nan)).rename("zscore")


def signal(df: pd.DataFrame, cfg: BacktestConfig) -> pd.Series:
    """Stateful mean-reversion target. Long on stretched-down, (perp) short on
    stretched-up; exit toward the mean."""
    mc = cfg.mean_reversion
    z = zscore(df["close"], mc.sma_period).to_numpy()
    allow_short = cfg.data.market_type != "spot"
    n = len(df)
    out = np.zeros(n)
    p = 0.0
    for i in range(n):
        zi = z[i]
        if np.isnan(zi):
            out[i] = 0.0
            continue
        if p == 0.0:
            if zi <= -mc.entry_z:
                p = 1.0  # fade the down-stretch
            elif allow_short and zi >= mc.entry_z:
                p = -1.0  # fade the up-stretch
        elif p > 0 and zi >= -mc.exit_z:
            p = 0.0  # reverted up -> close long
        elif p < 0 and zi <= mc.exit_z:
            p = 0.0  # reverted down -> close short
        out[i] = p
    return pd.Series(out, index=df.index, name="signal")
