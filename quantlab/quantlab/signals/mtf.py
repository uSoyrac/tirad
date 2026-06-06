"""Multi-timeframe agreement agent.

Computes the higher-timeframe trend direction and aligns it onto the primary-TF
index WITHOUT look-ahead: a higher-TF bar is only usable once it has CLOSED, so its
value is stamped at its completion time and merged backward onto the primary bars.
A 4h bar at 12:00 on day D therefore sees the daily trend through day D-1's close,
never the still-forming day-D bar.
"""

from __future__ import annotations

import pandas as pd

from ..config import BacktestConfig
from ..indicators import supertrend

_TF_OFFSET = {"1d": pd.Timedelta(days=1), "1w": pd.Timedelta(weeks=1), "4h": pd.Timedelta(hours=4)}


def higher_tf_direction(base_df: pd.DataFrame, higher_df: pd.DataFrame, cfg: BacktestConfig) -> pd.Series:
    """+1/-1 higher-TF trend per primary bar, aligned causally; 0 before warm-up."""
    mc = cfg.mtf
    st = supertrend(higher_df, period=mc.period, multiplier=mc.multiplier)
    direction = st["dir"]

    offset = _TF_OFFSET.get(mc.higher_tf, pd.Timedelta(days=1))
    # Coerce both keys to ns resolution — data from different sources (ccxt 'ms',
    # yfinance 's', resample 'us') otherwise trips pandas 3 merge_asof dtype check.
    avail = pd.DataFrame({
        "ts": (pd.DatetimeIndex(higher_df.index).as_unit("ns") + offset),  # bar completion time
        "dir": direction.to_numpy(),
    })
    left = pd.DataFrame({"ts": pd.DatetimeIndex(base_df.index).as_unit("ns")})
    merged = pd.merge_asof(left, avail, on="ts", direction="backward")
    out = pd.Series(merged["dir"].to_numpy(), index=base_df.index, name="mtf_dir")
    return out.fillna(0.0)
