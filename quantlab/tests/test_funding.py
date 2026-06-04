import pandas as pd

from quantlab.config import BacktestConfig, CostConfig, DataConfig, RiskConfig
from quantlab.backtest.harness import run_backtest


def _flat_df(price=100.0, n=12):
    # perfectly flat price so P&L comes ONLY from funding (isolates the effect)
    idx = pd.date_range("2021-01-01", periods=n, freq="4h")
    return pd.DataFrame({"open": price, "high": price + 0.5, "low": price - 0.5,
                         "close": price, "volume": 1.0}, index=idx)


def _cfg(market="perp"):
    return BacktestConfig(
        data=DataConfig(market_type=market),
        costs=CostConfig(taker_fee=0.0, slippage_bps=0.0, funding_enabled=True,
                         funding_mode="historical", funding_interval_hours=8),
        risk=RiskConfig(atr_period=2, stop_atr_mult=100.0, tp_atr_mult=None, max_leverage=50),
    )


def test_short_receives_positive_funding_long_pays():
    df = _flat_df()
    # constant positive funding rate at every 8h boundary
    fr = pd.Series(0.001, index=pd.date_range("2021-01-01", periods=4, freq="8h"))

    long_sig = pd.Series(1.0, index=df.index)
    short_sig = pd.Series(-1.0, index=df.index)
    long_end = run_backtest(df, long_sig, _cfg(), funding_rates=fr).equity.iloc[-1]
    short_end = run_backtest(df, short_sig, _cfg(), funding_rates=fr).equity.iloc[-1]

    # price is flat, no fees: longs should LOSE to funding, shorts should GAIN.
    assert long_end < 10_000.0
    assert short_end > 10_000.0


def test_historical_rate_used_over_flat():
    df = _flat_df()
    long_sig = pd.Series(1.0, index=df.index)
    big = pd.Series(0.01, index=pd.date_range("2021-01-01", periods=4, freq="8h"))  # 1% per 8h

    cfg_hist = _cfg()  # funding_mode='historical' -> uses the passed series
    e_hist = run_backtest(df, long_sig, cfg_hist, funding_rates=big).equity.iloc[-1]

    cfg_flat = _cfg()
    cfg_flat.costs.funding_mode = "flat"
    cfg_flat.costs.flat_funding_rate = 0.00001  # tiny flat rate, no series passed
    e_flat = run_backtest(df, long_sig, cfg_flat).equity.iloc[-1]

    # the big historical rate must bite the long meaningfully more than the tiny flat one
    assert e_hist < e_flat - 1.0


def test_no_funding_when_disabled():
    df = _flat_df()
    cfg = _cfg()
    cfg.costs.funding_enabled = False
    fr = pd.Series(0.01, index=pd.date_range("2021-01-01", periods=4, freq="8h"))
    e = run_backtest(df, pd.Series(1.0, index=df.index), cfg, funding_rates=fr).equity.iloc[-1]
    assert abs(e - 10_000.0) < 1e-6  # flat price, no fees, no funding => unchanged
