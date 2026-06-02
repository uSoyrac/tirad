"""Triple-barrier labelling for the signal-quality model.

For a candidate LONG entry at bar i (decision made on bar i's close), look forward
up to `horizon` bars and ask: did price reach the +TP barrier BEFORE the -stop
barrier? Barriers are ATR-based, matching the harness's stop/TP geometry.

  label = 1  -> TP touched first (a "good" signal)
  label = 0  -> stop touched first, OR neither within the horizon (not a clean win)

The label deliberately uses FUTURE bars — that is correct: it is the training
target, known only on historical data. Features (features.py) stay strictly causal.
Samples whose horizon runs past the end of the data are returned as NaN and dropped.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import BacktestConfig
from ..indicators import atr


def triple_barrier_labels(df: pd.DataFrame, cfg: BacktestConfig) -> pd.Series:
    """Per-bar long-entry label in {0,1}, NaN where unresolved (insufficient future)."""
    r = cfg.risk
    ml = cfg.ml
    a = atr(df, r.atr_period).to_numpy()
    close = df["close"].to_numpy()
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    n = len(df)
    horizon = ml.horizon_bars
    out = np.full(n, np.nan)

    for i in range(n):
        atr_i = a[i]
        if not (atr_i > 0) or i + horizon >= n:
            continue  # warm-up or not enough future bars to resolve the barriers
        up = close[i] + r.tp_atr_mult * atr_i
        down = close[i] - r.stop_atr_mult * atr_i
        label = 0  # default: stop-first or timeout
        for j in range(i + 1, min(i + horizon + 1, n)):
            hit_down = low[j] <= down
            hit_up = high[j] >= up
            if hit_down and hit_up:
                label = 0  # same bar touches both -> assume the stop (conservative)
                break
            if hit_up:
                label = 1
                break
            if hit_down:
                label = 0
                break
        out[i] = label
    return pd.Series(out, index=df.index, name="label")
