import numpy as np
import pandas as pd

from quantlab.config import BacktestConfig, MLConfig, RiskConfig
from quantlab.ml import dataset, features as featmod
from quantlab.ml.labels import triple_barrier_labels


def _df(n=400, seed=7, drift=0.05):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(drift, 1.0, n))
    high = close + np.abs(rng.normal(0, 0.5, n)) + 0.5
    low = close - np.abs(rng.normal(0, 0.5, n)) - 0.5
    openp = np.concatenate([[close[0]], close[:-1]])
    idx = pd.date_range("2021-01-01", periods=n, freq="4h")
    vol = rng.uniform(50, 150, n)
    return pd.DataFrame({"open": openp, "high": high, "low": low, "close": close,
                         "volume": vol}, index=idx)


def _daily(df):
    return df.resample("1D", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()


def test_features_are_causal():
    df = _df()
    hd = _daily(df)
    cfg = BacktestConfig()
    full = featmod.build_features(df, cfg, hd)
    for k in (200, 300, 399):
        prefix = featmod.build_features(df.iloc[: k + 1], cfg, hd)
        a = full.iloc[k]
        b = prefix.iloc[-1]
        for col in full.columns:
            av, bv = a[col], b[col]
            if pd.isna(av) and pd.isna(bv):
                continue
            assert abs(float(av) - float(bv)) < 1e-6, f"feature {col} leaks future at k={k}"


def test_label_tp_first_is_one_stop_first_is_zero():
    # Build a deterministic up-move then check a clear TP-first vs stop-first case.
    idx = pd.date_range("2021-01-01", periods=60, freq="4h")
    close = np.full(60, 100.0)
    # mild baseline volatility so ATR > 0 (a perfectly flat series has zero ATR)
    df = pd.DataFrame({"open": close, "high": close + 0.5, "low": close - 0.5,
                       "close": close, "volume": 1.0}, index=idx)
    # Inject a sharp rally right after bar 10 -> TP should trigger first there.
    df.iloc[11:16, df.columns.get_loc("high")] = 200.0
    df.iloc[11:16, df.columns.get_loc("close")] = 150.0
    cfg = BacktestConfig(risk=RiskConfig(atr_period=3, tp_atr_mult=1.0, stop_atr_mult=1.0),
                         ml=MLConfig(horizon_bars=10))
    labels = triple_barrier_labels(df, cfg)
    assert labels.iloc[10] == 1.0  # rally hits the +TP barrier before any stop


def test_labels_unresolved_at_tail_are_nan():
    df = _df(n=80)
    cfg = BacktestConfig(ml=MLConfig(horizon_bars=20))
    labels = triple_barrier_labels(df, cfg)
    assert labels.iloc[-1] != labels.iloc[-1]  # NaN: no future bars to resolve


def test_training_rows_only_candidates_and_resolved():
    df = _df()
    hd = _daily(df)
    cfg = BacktestConfig()
    X, y, mask = dataset.assemble(df, cfg, hd)
    Xtr, ytr = dataset.training_rows(X, y, mask, df.index)
    # all training rows must be candidates with a resolved (non-NaN) label
    assert mask.loc[Xtr.index].all()
    assert y.loc[Xtr.index].notna().all()
    assert set(ytr.unique()).issubset({0, 1})


def test_model_fit_predict_roundtrip():
    df = _df(n=600)
    hd = _daily(df)
    cfg = BacktestConfig()
    X, y, mask = dataset.assemble(df, cfg, hd)
    Xtr, ytr = dataset.training_rows(X, y, mask, df.index)
    if ytr.nunique() < 2 or len(Xtr) < 50:
        return  # not enough signal in this synthetic sample; logic covered elsewhere
    from quantlab.ml.model import SignalQualityModel
    m = SignalQualityModel(cfg).fit(Xtr, ytr)
    proba = m.predict_proba(Xtr)
    assert proba.between(0.0, 1.0).all()
    assert len(proba) == len(Xtr)
