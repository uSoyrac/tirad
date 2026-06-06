import numpy as np
import pandas as pd

from quantlab.backtest import combine


def _ret(seed, n=300, mu=0.001, sd=0.01):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2021-01-01", periods=n, freq="1D")
    return pd.Series(rng.normal(mu, sd, n), index=idx)


def test_inverse_vol_gives_more_weight_to_calmer_stream():
    calm = _ret(0, sd=0.005)
    wild = _ret(1, sd=0.05)
    w_calm, w_wild = combine.inverse_vol_weights(calm, wild)
    assert w_calm > w_wild
    assert abs(w_calm + w_wild - 1.0) < 1e-9


def test_blend_reduces_vol_when_uncorrelated():
    a = _ret(2, mu=0.001, sd=0.01)
    b = _ret(3, mu=0.001, sd=0.01)  # independent stream, same vol
    wa, wb = 0.5, 0.5
    c = combine.blend(a, b, wa, wb)
    # diversification: blended vol < average of the two component vols
    assert c.std() < 0.5 * (a.std() + b.std())


def test_diversification_lifts_sharpe_for_orthogonal_positive_streams():
    a = _ret(4, mu=0.0008, sd=0.012)
    b = _ret(5, mu=0.0008, sd=0.012)
    wa, wb = combine.inverse_vol_weights(a, b)
    c = combine.blend(a, b, wa, wb)

    def sharpe(s):
        return s.mean() / s.std()

    assert sharpe(c) > min(sharpe(a), sharpe(b))  # combo beats the weaker leg


def test_correlation_and_equity():
    a = _ret(6)
    eq = combine.equity_from_returns(a, 10_000.0)
    assert abs(eq.iloc[0] - 10_000.0 * (1 + a.iloc[0])) < 1e-6
    assert combine.correlation(a, a) > 0.99  # self-correlation ~1
