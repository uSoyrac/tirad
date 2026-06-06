"""Causal technical indicators.

Every function here returns a series aligned to the input index where value at bar
t uses ONLY bars <= t. This is the first line of defence against look-ahead bias;
test_no_lookahead.py asserts the causality property holds.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder's ATR. Causal: uses an EWM over past true ranges only."""
    tr = true_range(df)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder's ADX (trend strength, not direction). Causal — EWM over past bars.

    High ADX => trending; low ADX => choppy/ranging.
    """
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = ((up > down) & (up > 0)) * up
    minus_dm = ((down > up) & (down > 0)) * down
    tr = true_range(df)
    alpha = 1.0 / period
    atr_ = tr.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    plus_di = 100 * plus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean() / atr_
    minus_di = 100 * minus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean() / atr_
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    return dx.ewm(alpha=alpha, adjust=False, min_periods=period).mean().rename("adx")


def efficiency_ratio(df: pd.DataFrame, period: int = 10) -> pd.Series:
    """Kaufman Efficiency Ratio in [0,1]: net move / sum of absolute moves.

    ~1 = clean directional trend; ~0 = choppy noise. Causal (trailing window).
    """
    change = df["close"].diff(period).abs()
    volatility = df["close"].diff().abs().rolling(period).sum()
    return (change / volatility.replace(0.0, np.nan)).fillna(0.0).clip(0.0, 1.0).rename("er")


def hurst_exponent(df: pd.DataFrame, period: int = 100, max_lag: int = 20) -> pd.Series:
    """Rolling Hurst via the lagged-variance (generalised) method. Causal.

    H>0.5 trending/persistent, H<0.5 mean-reverting, H~0.5 random walk. Optional
    (off by default) — it is the slowest feature here.
    """
    logp = np.log(df["close"].to_numpy())
    n = len(logp)
    out = np.full(n, np.nan)
    lags = np.arange(2, max_lag + 1)
    log_lags = np.log(lags)
    for i in range(period, n):
        window = logp[i - period + 1 : i + 1]
        tau = []
        for lag in lags:
            diff = window[lag:] - window[:-lag]
            tau.append(np.sqrt(np.std(diff)) if diff.size else np.nan)
        tau = np.asarray(tau)
        if np.all(np.isfinite(tau)) and np.all(tau > 0):
            out[i] = np.polyfit(log_lags, np.log(tau), 1)[0] * 2.0
    return pd.Series(out, index=df.index, name="hurst")


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD line, signal line, histogram. Causal (EWM over past closes)."""
    macd_line = ema(df["close"], fast) - ema(df["close"], slow)
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    hist = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "hist": hist}, index=df.index)


def donchian(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """Donchian channel using ONLY prior bars (shifted), so a breakout at bar t
    compares the current close against the high/low of the *preceding* `period` bars.
    """
    upper = df["high"].rolling(period).max().shift(1)
    lower = df["low"].rolling(period).min().shift(1)
    return pd.DataFrame({"upper": upper, "lower": lower}, index=df.index)


def supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    """Supertrend. Returns columns: line, dir (+1 uptrend / -1 downtrend).

    Computed bar-by-bar so the band 'memory' only ever depends on prior bars.
    """
    hl2 = (df["high"] + df["low"]) / 2.0
    _atr = atr(df, period)
    upper = hl2 + multiplier * _atr
    lower = hl2 - multiplier * _atr

    close = df["close"].to_numpy()
    upper = upper.to_numpy()
    lower = lower.to_numpy()
    n = len(df)

    final_upper = np.full(n, np.nan)
    final_lower = np.full(n, np.nan)
    direction = np.ones(n, dtype=float)  # +1 up, -1 down
    line = np.full(n, np.nan)

    for i in range(n):
        if np.isnan(upper[i]):
            # ATR warm-up: no bands yet. Leave final_upper/lower NaN (do NOT let them
            # feed the recursion) and mark direction/line as undefined.
            direction[i] = 1.0
            line[i] = np.nan
            continue
        if i == 0 or np.isnan(final_upper[i - 1]):
            # First bar with a valid ATR: seed the bands from this bar.
            final_upper[i] = upper[i]
            final_lower[i] = lower[i]
            direction[i] = 1.0 if close[i] >= (upper[i] + lower[i]) / 2.0 else -1.0
            line[i] = final_lower[i] if direction[i] > 0 else final_upper[i]
            continue
        final_upper[i] = (
            upper[i]
            if (upper[i] < final_upper[i - 1] or close[i - 1] > final_upper[i - 1])
            else final_upper[i - 1]
        )
        final_lower[i] = (
            lower[i]
            if (lower[i] > final_lower[i - 1] or close[i - 1] < final_lower[i - 1])
            else final_lower[i - 1]
        )
        if close[i] > final_upper[i - 1]:
            direction[i] = 1.0
        elif close[i] < final_lower[i - 1]:
            direction[i] = -1.0
        else:
            direction[i] = direction[i - 1]
        line[i] = final_lower[i] if direction[i] > 0 else final_upper[i]

    return pd.DataFrame({"line": line, "dir": direction}, index=df.index)
