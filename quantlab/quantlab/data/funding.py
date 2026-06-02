"""Historical funding-rate loader for perp backtests.

Funding is a real, sometimes-dominant cost/credit for perpetual positions: when the
rate is positive, longs pay shorts (and vice versa). Backtesting perp shorts with a
flat assumed rate would be a fantasy, so we load the actual 8-hourly series.

Canonical shape: a float Series of per-interval rates indexed by a tz-naive UTC
DatetimeIndex named 'ts', sorted ascending.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_funding(path: str | Path) -> pd.Series:
    """Read a funding CSV (schema: ts,funding) into a sorted rate Series."""
    df = pd.read_csv(path)
    df["ts"] = pd.to_datetime(df["ts"], utc=False)
    s = df.set_index("ts")["funding"].astype("float64").sort_index()
    s = s[~s.index.duplicated(keep="last")]
    s.index.name = "ts"
    s.name = "funding"
    return s
