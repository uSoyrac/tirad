import numpy as np
import pandas as pd

from quantlab.ml.altfeatures import funding_features, oi_features


def _df(n=200):
    idx = pd.date_range("2021-01-01", periods=n, freq="4h")
    close = 100 + np.cumsum(np.full(n, 0.1))
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": 1.0}, index=idx)


def _funding(n=70):
    idx = pd.date_range("2021-01-01", periods=n, freq="8h")
    rng = np.random.default_rng(0)
    return pd.Series(rng.normal(0.0001, 0.0003, n), index=idx)


def test_funding_features_causal():
    df = _df()
    fundings = {"binance": _funding(), "bybit": _funding(), "okx": _funding()}
    full = funding_features(df, fundings)
    for k in (120, 160, 199):
        prefix = funding_features(df.iloc[: k + 1], fundings)
        for col in full.columns:
            a, b = full[col].iloc[k], prefix[col].iloc[-1]
            if pd.isna(a) and pd.isna(b):
                continue
            assert abs(float(a) - float(b)) < 1e-9, f"{col} leaks future at k={k}"


def test_funding_features_have_expected_columns():
    df = _df()
    feats = funding_features(df, {"binance": _funding(), "bybit": _funding(), "okx": _funding()})
    for c in ("fund_now", "fund_mean_7d", "fund_z", "fund_mom", "fund_xexch_spread"):
        assert c in feats.columns


def test_oi_features_shifted_causal():
    df = _df()
    idx = df.index
    oi = pd.DataFrame({"oi": np.linspace(100, 200, len(idx)),
                       "toptrader_ls_ratio": np.linspace(1.0, 2.0, len(idx)),
                       "ls_ratio": 1.5, "taker_buy_sell_ratio": 1.0}, index=idx)
    feats = oi_features(df, oi)
    # shifted by one bar => value at t equals raw at t-1 (no same-bar leak)
    assert pd.isna(feats["toptrader_ls"].iloc[0])
    assert abs(feats["toptrader_ls"].iloc[5] - oi["toptrader_ls_ratio"].iloc[4]) < 1e-9


def test_oi_features_empty_when_no_data():
    df = _df()
    feats = oi_features(df, None)
    assert feats.shape[1] == 0
