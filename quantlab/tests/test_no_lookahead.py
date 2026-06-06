"""The non-negotiable: nothing at bar t may use information from after t."""

import numpy as np
import pandas as pd

from quantlab.indicators import atr, supertrend


def _trending_df(n=120, seed=1):
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.2, 1.0, n)
    close = 100 + np.cumsum(steps)
    high = close + np.abs(rng.normal(0, 0.5, n)) + 0.5
    low = close - np.abs(rng.normal(0, 0.5, n)) - 0.5
    openp = np.concatenate([[close[0]], close[:-1]])
    idx = pd.date_range("2021-01-01", periods=n, freq="4h")
    return pd.DataFrame({"open": openp, "high": high, "low": low, "close": close,
                         "volume": 1.0}, index=idx)


def test_atr_is_causal():
    df = _trending_df()
    full = atr(df, period=14)
    for k in (40, 80, 119):
        prefix = atr(df.iloc[: k + 1], period=14)
        assert abs(prefix.iloc[-1] - full.iloc[k]) < 1e-9, f"ATR leaks future at k={k}"


def test_supertrend_is_causal():
    df = _trending_df()
    full = supertrend(df, period=10, multiplier=3.0)
    for k in (30, 60, 119):
        prefix = supertrend(df.iloc[: k + 1], period=10, multiplier=3.0)
        assert prefix["dir"].iloc[-1] == full["dir"].iloc[k], f"Supertrend leaks future at k={k}"


def test_harness_executes_at_next_bar_open():
    """A signal decided on bar t must fill at bar t+1's open, not bar t."""
    from quantlab.config import BacktestConfig, CostConfig, RiskConfig
    from quantlab.backtest.harness import run_backtest

    idx = pd.date_range("2021-01-01", periods=6, freq="4h")
    close = np.array([100, 101, 102, 103, 104, 105], dtype=float)
    openp = np.array([100, 100, 101, 102, 103, 104], dtype=float)
    df = pd.DataFrame({"open": openp, "high": close + 0.5, "low": openp - 0.5,
                       "close": close, "volume": 1.0}, index=idx)
    # Decided-on-close signal: go long at bar 2, flat at bar 4.
    signal = pd.Series([0, 0, 1, 1, 0, 0], index=idx, dtype=float)

    cfg = BacktestConfig(
        costs=CostConfig(taker_fee=0.0, slippage_bps=0.0),
        risk=RiskConfig(atr_period=2, stop_atr_mult=50.0, tp_atr_mult=None, max_leverage=100),
    )
    res = run_backtest(df, signal, cfg)
    assert len(res.trades) == 1
    t = res.trades[0]
    assert t.entry_ts == idx[3], "entry must be at t+1 (bar 3), not bar 2"
    assert t.exit_ts == idx[5], "exit must be at t+1 (bar 5)"
    assert abs(t.entry_price - openp[3]) < 1e-9  # filled at bar-3 OPEN
