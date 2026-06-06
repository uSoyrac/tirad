import numpy as np
import pandas as pd

from quantlab.config import BacktestConfig, DataConfig, EnsembleConfig
from quantlab.signals import agents, ensemble


def _df(n=160, seed=2):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0.1, 1.0, n))
    high = close + np.abs(rng.normal(0, 0.5, n)) + 0.5
    low = close - np.abs(rng.normal(0, 0.5, n)) - 0.5
    openp = np.concatenate([[close[0]], close[:-1]])
    idx = pd.date_range("2021-01-01", periods=n, freq="4h")
    return pd.DataFrame({"open": openp, "high": high, "low": low, "close": close,
                         "volume": 1.0}, index=idx)


def test_agent_scores_in_range():
    df = _df()
    for fn in (agents.supertrend_score, agents.macd_score, agents.donchian_score):
        s = fn(df)
        assert s.between(-1.0, 1.0).all(), f"{fn.__name__} out of [-1,1]"


def test_agents_are_causal():
    df = _df()
    for fn in (agents.supertrend_score, agents.macd_score, agents.donchian_score):
        full = fn(df)
        for k in (60, 100, 159):
            prefix = fn(df.iloc[: k + 1])
            assert abs(float(prefix.iloc[-1]) - float(full.iloc[k])) < 1e-9, \
                f"{fn.__name__} leaks future at k={k}"


def test_ensemble_net_is_weighted_average():
    df = _df()
    cfg = BacktestConfig()
    scores = ensemble.ensemble_scores(df, cfg)
    # equal weights => net == mean of the three agent columns
    agent_cols = [a.name for a in cfg.ensemble.agents]
    recomputed = scores[agent_cols].mean(axis=1)
    assert np.allclose(scores["net"].to_numpy(), recomputed.to_numpy(), atol=1e-9)
    assert scores["net"].between(-1.0, 1.0).all()


def test_threshold_controls_entries():
    df = _df()
    loose = BacktestConfig(ensemble=EnsembleConfig(entry_threshold=0.0))
    strict = BacktestConfig(ensemble=EnsembleConfig(entry_threshold=0.99))
    n_loose = ensemble.signal(df, loose).sum()
    n_strict = ensemble.signal(df, strict).sum()
    assert n_loose >= n_strict  # a higher bar => fewer (or equal) long bars


def test_spot_never_shorts():
    df = _df()
    cfg = BacktestConfig(data=DataConfig(market_type="spot"))
    target = ensemble.signal(df, cfg)
    assert target.min() >= 0.0  # spot is long/flat only


def test_perp_shorts_on_negative_net_spot_does_not():
    idx = pd.date_range("2021-01-01", periods=3, freq="4h")
    net = pd.Series([0.8, -0.8, 0.1], index=idx)  # strong long, strong short, weak
    perp = BacktestConfig(data=DataConfig(market_type="perp"),
                          ensemble=EnsembleConfig(entry_threshold=0.5))
    spot = BacktestConfig(data=DataConfig(market_type="spot"),
                          ensemble=EnsembleConfig(entry_threshold=0.5))
    t_perp = ensemble.target_from_net(net, perp)
    t_spot = ensemble.target_from_net(net, spot)
    assert list(t_perp) == [1.0, -1.0, 0.0]  # perp shorts the -0.8 bar
    assert list(t_spot) == [1.0, 0.0, 0.0]   # spot never shorts
