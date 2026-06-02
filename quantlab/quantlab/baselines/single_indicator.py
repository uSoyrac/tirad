"""Single-indicator trend baseline: Supertrend.

Emits a target-direction series for the harness. On spot we trade long/flat (no
shorting); on perp we allow long/short. The signal at bar t uses only data <= t
(Supertrend is causal); the harness then executes it at t+1's open.
"""

from __future__ import annotations

import pandas as pd

from ..config import BacktestConfig
from ..indicators import supertrend


def signal(df: pd.DataFrame, cfg: BacktestConfig, period: int = 10, multiplier: float = 3.0) -> pd.Series:
    st = supertrend(df, period=period, multiplier=multiplier)
    direction = st["dir"]  # +1 up, -1 down
    if cfg.data.market_type == "spot":
        target = (direction > 0).astype(float)  # long / flat
    else:
        target = direction.astype(float)  # long / short
    target.name = "signal"
    return target
