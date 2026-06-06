import numpy as np
import pandas as pd

from quantlab.config import BacktestConfig, DataConfig, MeanReversionConfig, OrchestratorConfig
from quantlab.signals import mean_reversion
from quantlab import orchestrator


def _df(n=300, seed=11):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1.0, n))
    high = close + 0.5
    low = close - 0.5
    openp = np.concatenate([[close[0]], close[:-1]])
    idx = pd.date_range("2021-01-01", periods=n, freq="4h")
    return pd.DataFrame({"open": openp, "high": high, "low": low, "close": close,
                         "volume": 1.0}, index=idx)


def test_zscore_causal():
    df = _df()
    full = mean_reversion.zscore(df["close"], 20)
    for k in (100, 200, 299):
        prefix = mean_reversion.zscore(df["close"].iloc[: k + 1], 20)
        a, b = full.iloc[k], prefix.iloc[-1]
        if pd.isna(a) and pd.isna(b):
            continue
        assert abs(float(a) - float(b)) < 1e-9


def test_mr_fades_extremes():
    # Construct a clean V: drop then recover. MR should go long at the trough.
    down = np.linspace(100, 80, 40)
    up = np.linspace(80, 100, 40)
    close = np.concatenate([np.full(20, 100.0), down, up])
    idx = pd.date_range("2021-01-01", periods=len(close), freq="4h")
    df = pd.DataFrame({"open": close, "high": close + 0.3, "low": close - 0.3,
                       "close": close, "volume": 1.0}, index=idx)
    cfg = BacktestConfig(mean_reversion=MeanReversionConfig(sma_period=10, entry_z=1.0, exit_z=0.2))
    sig = mean_reversion.signal(df, cfg)
    assert (sig > 0).any()  # took at least one long on the down-stretch


def test_mr_sleeve_only_fills_chop_and_keeps_trend():
    df = _df(n=400)
    daily = df.resample("1D", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    from quantlab.signals import regime
    base_cfg = BacktestConfig()
    trend_only = orchestrator.build_target(df, base_cfg, daily)
    with_mr = orchestrator.build_target(
        df, BacktestConfig(orchestrator=OrchestratorConfig(use_mr_sleeve=True)), daily)
    trending = regime.is_trending(df, base_cfg)

    # Wherever the trend sleeve already has a position, the MR sleeve must not change it.
    nz = trend_only != 0.0
    assert (with_mr[nz] == trend_only[nz]).all()
    # Any extra activity introduced by MR must be in CHOP bars only.
    extra = (with_mr != 0.0) & (trend_only == 0.0)
    assert (~trending[extra]).all()


def test_spot_mr_never_shorts():
    df = _df()
    cfg = BacktestConfig(data=DataConfig(market_type="spot"),
                         mean_reversion=MeanReversionConfig(entry_z=1.0))
    assert mean_reversion.signal(df, cfg).min() >= 0.0
