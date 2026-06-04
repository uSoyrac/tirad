import numpy as np
import pandas as pd

from quantlab.config import BacktestConfig, CostConfig, RiskConfig, DataConfig
from quantlab.backtest.harness import run_backtest


def _df(open_, high, low, close):
    n = len(close)
    idx = pd.date_range("2021-01-01", periods=n, freq="4h")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": 1.0}, index=idx
    )


def test_equity_curve_aligned_and_finite():
    rng = np.random.default_rng(3)
    close = 100 + np.cumsum(rng.normal(0, 1, 200))
    df = _df(close, close + 1, close - 1, close)
    sig = pd.Series((close > pd.Series(close).rolling(5).mean().to_numpy()).astype(float),
                    index=df.index)
    res = run_backtest(df, sig, BacktestConfig())
    assert len(res.equity) == len(df)
    assert np.isfinite(res.equity.to_numpy()).all()


def test_costs_reduce_pnl():
    # Same path, frictionless vs costly: costly must end with less equity.
    close = np.linspace(100, 130, 60)
    df = _df(np.concatenate([[100], close[:-1]]), close + 0.3, close - 0.3, close)
    sig = pd.Series(1.0, index=df.index)  # always long

    free = BacktestConfig(costs=CostConfig(taker_fee=0.0, slippage_bps=0.0),
                          risk=RiskConfig(atr_period=5, tp_atr_mult=None, max_leverage=100))
    paid = BacktestConfig(costs=CostConfig(taker_fee=0.001, slippage_bps=10.0),
                          risk=RiskConfig(atr_period=5, tp_atr_mult=None, max_leverage=100))
    e_free = run_backtest(df, sig, free).equity.iloc[-1]
    e_paid = run_backtest(df, sig, paid).equity.iloc[-1]
    assert e_paid < e_free


def test_liquidation_is_booked_as_loss():
    # Leveraged perp long that gaps below its liquidation price must exit 'liquidation'.
    close = np.array([100, 100, 100, 100, 80, 80], dtype=float)
    openp = np.array([100, 100, 100, 100, 100, 80], dtype=float)
    high = np.array([101, 101, 101, 101, 101, 81], dtype=float)
    low = np.array([99, 99, 99, 99, 84, 79], dtype=float)  # bar 4 dips to 84 (< liq=90 for 10x)
    df = _df(openp, high, low, close)
    sig = pd.Series([0, 1, 1, 1, 1, 1], index=df.index, dtype=float)

    cfg = BacktestConfig(
        data=DataConfig(market_type="perp"),
        costs=CostConfig(taker_fee=0.0, slippage_bps=0.0, funding_enabled=False),
        # huge stop so the STOP can't fire before liquidation; 10x => liq at 90
        risk=RiskConfig(atr_period=2, stop_atr_mult=100.0, tp_atr_mult=None, max_leverage=10),
    )
    res = run_backtest(df, sig, cfg)
    assert any(t.exit_reason == "liquidation" for t in res.trades)
    liq = next(t for t in res.trades if t.exit_reason == "liquidation")
    assert liq.pnl < 0
