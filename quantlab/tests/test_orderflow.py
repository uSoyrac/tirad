import numpy as np
import pandas as pd

from quantlab.research.orderflow import _rolling_ols, build_orderflow_features


def _df(n=300, seed=3):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0.1, 1.0, n))
    close = np.maximum(close, 1.0)
    idx = pd.date_range("2021-01-01", periods=n, freq="4h")
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": rng.uniform(50, 150, n)}, index=idx)


def test_rolling_ols_perfect_line():
    # y = 2*t + 5 over a clean ramp => slope 2, R^2 = 1
    y = pd.Series(2.0 * np.arange(100) + 5.0)
    slope, r2 = _rolling_ols(y, 20)
    assert abs(slope.iloc[-1] - 2.0) < 1e-6
    assert abs(r2.iloc[-1] - 1.0) < 1e-6
    assert np.isnan(slope.iloc[0])  # warm-up


def test_rolling_ols_noise_low_r2():
    rng = np.random.default_rng(0)
    y = pd.Series(rng.normal(0, 1, 200))  # pure noise around a level
    _, r2 = _rolling_ols(y, 20)
    assert r2.dropna().mean() < 0.5  # chop => low trend-cleanliness


def test_rolling_ols_is_causal():
    rng = np.random.default_rng(1)
    y = pd.Series(np.cumsum(rng.normal(0, 1, 200)))
    full_s, full_r = _rolling_ols(y, 24)
    for k in (60, 120, 199):
        ps, pr = _rolling_ols(y.iloc[: k + 1], 24)
        assert abs(float(ps.iloc[-1]) - float(full_s.iloc[k])) < 1e-9
        assert abs(float(pr.iloc[-1]) - float(full_r.iloc[k])) < 1e-9


def test_orderflow_has_regression_and_jerk_families():
    df = _df()
    feats, fam = build_orderflow_features(df, fundings=None, oi_df=None)
    assert "regression" in fam and "jerk" in fam
    assert "reg_r2_24" in feats.columns and "vol_jerk" in feats.columns
    assert feats["reg_r2_24"].dropna().between(-0.01, 1.01).all()
