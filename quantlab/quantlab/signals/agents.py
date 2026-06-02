"""Signal agents. Each emits a causal score in [-1, 1] = direction * strength.

Score at bar t uses ONLY data <= t. The harness later shifts the combined target
by one bar, so execution still happens at t+1's open — agents themselves stay
purely causal and are tested for it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..indicators import atr, donchian, macd, supertrend


def supertrend_score(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.Series:
    """+1 in an uptrend, -1 in a downtrend (full strength)."""
    st = supertrend(df, period=int(period), multiplier=float(multiplier))
    return st["dir"].rename("supertrend")


def macd_score(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.Series:
    """Graded momentum: tanh of the histogram normalised by ATR (scale-free)."""
    m = macd(df, fast=int(fast), slow=int(slow), signal=int(signal))
    a = atr(df, max(int(slow), 14)).replace(0.0, np.nan)
    score = np.tanh(m["hist"] / a)
    return score.fillna(0.0).clip(-1.0, 1.0).rename("macd")


def donchian_score(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Breakout regime: go +1 on a close above the prior `period`-bar high, -1 on a
    close below the prior low, and HOLD the regime in between (stop-and-reverse).
    """
    ch = donchian(df, period=int(period))
    close = df["close"].to_numpy()
    upper = ch["upper"].to_numpy()
    lower = ch["lower"].to_numpy()
    n = len(df)
    state = np.zeros(n, dtype=float)
    cur = 0.0
    for i in range(n):
        if not np.isnan(upper[i]) and close[i] > upper[i]:
            cur = 1.0
        elif not np.isnan(lower[i]) and close[i] < lower[i]:
            cur = -1.0
        state[i] = cur
    return pd.Series(state, index=df.index, name="donchian")


REGISTRY = {
    "supertrend": supertrend_score,
    "macd": macd_score,
    "donchian": donchian_score,
}
