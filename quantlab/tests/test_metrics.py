import numpy as np
import pandas as pd

from quantlab.backtest import metrics
from quantlab.backtest.harness import Trade


def test_total_return_and_drawdown_known_curve():
    # Equity doubles then halves back: total return ~ +50% peak, then drawdown 50%.
    idx = pd.date_range("2021-01-01", periods=5, freq="1D")
    eq = pd.Series([100, 150, 200, 150, 120], index=idx, dtype=float)
    assert abs(metrics.max_drawdown(eq) - (-0.40)) < 1e-9  # 200 -> 120
    m = metrics.compute_metrics(eq, [], timeframe="1d")
    assert abs(m["total_return"] - 0.20) < 1e-9


def _mk(pnl, return_pct, reason):
    return Trade(entry_ts=None, exit_ts=None, side=1, entry_price=100, exit_price=110,
                 units=1.0, pnl=pnl, return_pct=return_pct, exit_reason=reason,
                 fees=0.0, funding=0.0)


def test_trade_stats():
    trades = [_mk(10.0, 0.10, "tp"), _mk(-5.0, -0.05, "stop"), _mk(20.0, 0.20, "tp")]
    idx = pd.date_range("2021-01-01", periods=3, freq="1D")
    eq = pd.Series([100, 110, 130], index=idx, dtype=float)
    m = metrics.compute_metrics(eq, trades, timeframe="1d")
    assert m["n_trades"] == 3
    assert abs(m["win_rate"] - 2 / 3) < 1e-9
    assert abs(m["expectancy"] - (10 - 5 + 20) / 3) < 1e-9
    assert m["longest_losing_streak"] == 1


def test_risk_of_ruin_few_trades_is_nan():
    trades = [_mk(10.0, 0.1, "tp")]
    assert np.isnan(metrics.risk_of_ruin(trades, ruin_drawdown=0.25))


def test_risk_of_ruin_all_losers_is_one():
    trades = [_mk(-30.0, -0.30, "stop") for _ in range(10)]
    ror = metrics.risk_of_ruin(trades, ruin_drawdown=0.25, n_paths=500)
    assert ror == 1.0  # every bootstrap path breaches a 25% drawdown immediately
