import numpy as np
import pandas as pd

from quantlab.config import BacktestConfig, OrchestratorConfig, RegimeConfig, MTFConfig
from quantlab.indicators import adx, efficiency_ratio, hurst_exponent
from quantlab.signals import regime, mtf
from quantlab import orchestrator


def _df(n=200, seed=5, drift=0.1):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(drift, 1.0, n))
    high = close + np.abs(rng.normal(0, 0.5, n)) + 0.5
    low = close - np.abs(rng.normal(0, 0.5, n)) - 0.5
    openp = np.concatenate([[close[0]], close[:-1]])
    idx = pd.date_range("2021-01-01", periods=n, freq="4h")
    return pd.DataFrame({"open": openp, "high": high, "low": low, "close": close,
                         "volume": 1.0}, index=idx)


def test_regime_indicators_causal():
    df = _df()
    for fn in (lambda d: adx(d, 14), lambda d: efficiency_ratio(d, 10)):
        full = fn(df)
        for k in (80, 140, 199):
            prefix = fn(df.iloc[: k + 1])
            a, b = float(prefix.iloc[-1]), float(full.iloc[k])
            assert (np.isnan(a) and np.isnan(b)) or abs(a - b) < 1e-8, f"leak at k={k}"


def test_efficiency_ratio_bounds():
    df = _df()
    er = efficiency_ratio(df, 10)
    assert er.between(0.0, 1.0).all()


def test_hurst_trending_vs_meanreverting():
    # Strong trend => H clearly above a random walk's ~0.5; mean-reverting => below.
    idx = pd.date_range("2021-01-01", periods=400, freq="4h")
    trend = pd.Series(np.linspace(100, 300, 400), index=idx)
    rng = np.random.default_rng(0)
    mr = pd.Series(150 + rng.normal(0, 5, 400), index=idx)  # noise around a level
    tdf = pd.DataFrame({"open": trend, "high": trend, "low": trend, "close": trend, "volume": 1.0})
    mdf = pd.DataFrame({"open": mr, "high": mr, "low": mr, "close": mr, "volume": 1.0})
    h_trend = hurst_exponent(tdf, period=100).dropna().mean()
    h_mr = hurst_exponent(mdf, period=100).dropna().mean()
    assert h_trend > h_mr


def test_regime_gate_reduces_trading_time():
    df = _df()
    cfg = BacktestConfig(regime=RegimeConfig(adx_threshold=25.0, er_threshold=0.4))
    gate = regime.is_trending(df, cfg)
    # the gate should block at least some bars (not always-on)
    assert 0 < gate.sum() < len(gate)


def test_mtf_alignment_has_no_lookahead():
    # The daily direction used at a 4h bar must come from an ALREADY-CLOSED daily bar.
    base = _df(n=240)  # 240 * 4h = 40 days
    daily = base.resample("1D", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    cfg = BacktestConfig(mtf=MTFConfig(higher_tf="1d", period=3, multiplier=2.0))
    from quantlab.indicators import supertrend
    daily_dir = supertrend(daily, period=3, multiplier=2.0)["dir"]
    aligned = mtf.higher_tf_direction(base, daily, cfg)

    # For a 4h bar at time t, aligned value must equal the daily dir of a bar that
    # closed at or before t — i.e. some daily bar whose (start + 1 day) <= t.
    for t in base.index[::13]:
        val = aligned.loc[t]
        if val == 0.0:
            continue
        eligible = daily_dir[daily.index + pd.Timedelta(days=1) <= t]
        assert len(eligible) > 0
        assert val == eligible.iloc[-1], f"mtf used a not-yet-closed daily bar at {t}"


def test_orchestrator_filters_only_subtract():
    # Filtered target must be a subset: never opens a position the ensemble didn't,
    # and never flips its sign.
    df = _df(n=300)
    daily = df.resample("1D", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    cfg = BacktestConfig(orchestrator=OrchestratorConfig(use_regime=True, use_mtf=True))
    from quantlab.signals import ensemble
    base = ensemble.signal(df, cfg)
    final = orchestrator.build_target(df, cfg, daily)
    # wherever final is non-zero, it must match the ensemble's sign there
    nz = final != 0.0
    assert (np.sign(final[nz]) == np.sign(base[nz])).all()
    # filtering can only reduce (or keep) the number of active bars
    assert (final != 0.0).sum() <= (base != 0.0).sum()


def test_entry_only_holds_through_dips_continuous_does_not():
    df = _df(n=400)
    daily = df.resample("1D", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    from quantlab.signals import ensemble
    base_cfg = BacktestConfig()
    base = ensemble.signal(df, base_cfg)

    cont = orchestrator.build_target(
        df, BacktestConfig(orchestrator=OrchestratorConfig(gate_mode="continuous")), daily)
    entry = orchestrator.build_target(
        df, BacktestConfig(orchestrator=OrchestratorConfig(gate_mode="entry_only")), daily)

    base_active = int((base != 0).sum())
    # entry_only holds positions through regime dips => >= continuous active bars,
    # but still never trades where the ensemble is flat.
    assert (entry != 0).sum() >= (cont != 0).sum()
    assert (entry != 0).sum() <= base_active


def test_orchestrator_requires_higher_df_when_mtf_on():
    df = _df(n=60)
    cfg = BacktestConfig(orchestrator=OrchestratorConfig(use_mtf=True))
    try:
        orchestrator.build_target(df, cfg, None)
        assert False, "expected ValueError"
    except ValueError:
        pass
