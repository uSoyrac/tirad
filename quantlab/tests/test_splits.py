import numpy as np
import pandas as pd

from quantlab.config import SplitConfig
from quantlab.backtest import splits


def _make_df(start="2021-01-01", periods=400, freq="1D"):
    idx = pd.date_range(start, periods=periods, freq=freq)
    rng = np.random.default_rng(0)
    price = 100 + np.cumsum(rng.normal(0, 1, periods))
    return pd.DataFrame(
        {"open": price, "high": price + 1, "low": price - 1, "close": price, "volume": 1.0},
        index=idx,
    )


def test_train_oos_no_overlap_and_covers():
    df = _make_df()
    train, oos = splits.train_oos_split(df, "2021-06-30")
    assert train.index.max() < oos.index.min()
    assert len(train) + len(oos) == len(df)


def test_walk_forward_windows_monotonic_no_overlap():
    df = _make_df(periods=1200)
    cfg = SplitConfig(train_months=12, test_months=3, step_months=3)
    wins = splits.walk_forward(df, cfg)
    assert len(wins) > 0
    for w in wins:
        # test strictly follows train, no overlap
        assert w.train.index.max() < w.test.index.min()
    # successive windows roll forward in time
    for a, b in zip(wins, wins[1:]):
        assert b.train.index[0] > a.train.index[0]
