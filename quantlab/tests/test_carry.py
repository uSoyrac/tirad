import numpy as np
import pandas as pd

from quantlab.config import BacktestConfig, CostConfig
from quantlab.backtest.carry import run_carry


def _coin(seed, drift, n=120):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(drift, 1.0, n))
    close = np.maximum(close, 1.0)
    idx = pd.date_range("2021-01-01", periods=n, freq="4h")
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": 1.0}, index=idx)


def test_short_high_funding_harvests_positive_funding():
    # Two coins, flat-ish price; HIGH-funding coin should be shorted and EARN funding.
    n = 120
    idx = pd.date_range("2021-01-01", periods=n, freq="4h")
    flat = pd.DataFrame({"open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0,
                         "volume": 1.0}, index=idx)
    frames = {"HI": flat.copy(), "LO": flat.copy(), "MID1": flat.copy(), "MID2": flat.copy()}
    fidx = pd.date_range("2021-01-01", periods=n // 2, freq="8h")
    fundings = {
        "HI": pd.Series(0.002, index=fidx),    # very high funding -> should be SHORTED
        "LO": pd.Series(-0.002, index=fidx),   # very negative -> should be LONGED
        "MID1": pd.Series(0.0, index=fidx),
        "MID2": pd.Series(0.0, index=fidx),
    }
    cfg = BacktestConfig(costs=CostConfig(taker_fee=0.0, slippage_bps=0.0))
    res = run_carry(frames, fundings, cfg, lookback_days=2, n_side=1, rebalance_days=1)
    # flat prices => price P&L ~0; funding harvest should be POSITIVE and drive equity up
    assert res.funding_pnl.iloc[-1] > 0
    assert res.equity.iloc[-1] > cfg.risk.bankroll


def test_dollar_neutral_cancels_common_move():
    # All coins move identically; a dollar-neutral book should net ~0 price P&L.
    n = 120
    base = _coin(0, 0.3, n)
    frames = {s: base.copy() for s in ["A", "B", "C", "D"]}
    fidx = pd.date_range("2021-01-01", periods=n // 2, freq="8h")
    fundings = {"A": pd.Series(0.001, index=fidx), "B": pd.Series(0.0005, index=fidx),
                "C": pd.Series(-0.0005, index=fidx), "D": pd.Series(-0.001, index=fidx)}
    cfg = BacktestConfig(costs=CostConfig(taker_fee=0.0, slippage_bps=0.0))
    res = run_carry(frames, fundings, cfg, lookback_days=2, n_side=2, rebalance_days=1)
    # identical price paths => long and short legs cancel => |price P&L| tiny
    assert abs(res.price_pnl.iloc[-1]) < 1e-6


def test_costs_create_drag():
    n = 120
    frames = {s: _coin(i, 0.2, n) for i, s in enumerate(["A", "B", "C", "D", "E", "F"])}
    fidx = pd.date_range("2021-01-01", periods=n // 2, freq="8h")
    rng = np.random.default_rng(1)
    fundings = {s: pd.Series(rng.normal(0, 0.001, len(fidx)), index=fidx) for s in frames}
    free = run_carry(frames, fundings, BacktestConfig(costs=CostConfig(taker_fee=0, slippage_bps=0)),
                     lookback_days=2, n_side=2, rebalance_days=1)
    paid = run_carry(frames, fundings, BacktestConfig(costs=CostConfig(taker_fee=0.001, slippage_bps=10)),
                     lookback_days=2, n_side=2, rebalance_days=1)
    assert paid.cost_pnl.iloc[-1] < 0
    assert paid.equity.iloc[-1] < free.equity.iloc[-1]
