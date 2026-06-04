import numpy as np
import pandas as pd

from quantlab.config import BacktestConfig, OrchestratorConfig
from quantlab.paper import engine as paper


def _df(seed, drift):
    rng = np.random.default_rng(seed)
    n = 300
    close = 100 + np.cumsum(rng.normal(drift, 1.0, n))
    close = np.maximum(close, 1.0)
    idx = pd.date_range("2021-01-01", periods=n, freq="4h")
    openp = np.concatenate([[close[0]], close[:-1]])
    return pd.DataFrame({"open": openp, "high": close + 1, "low": close - 1,
                         "close": close, "volume": 1.0}, index=idx)


def _frames():
    return {s: _df(i, 0.1 + 0.02 * i) for i, s in enumerate(["A", "B", "C", "D", "E"])}


def test_live_targets_respects_top_k_and_no_mtf():
    frames = _frames()
    # disable MTF so the tiny synthetic daily series doesn't gate everything out
    cfg = BacktestConfig(orchestrator=OrchestratorConfig(use_regime=False, use_mtf=False))
    sel = paper.live_targets(frames, cfg, top_k=2, mom_window=20)
    assert len(sel) <= 2
    assert set(sel).issubset(set(frames.keys()))


def test_rebalance_orders():
    o = paper.rebalance_orders(["A", "B", "C"], ["B", "C", "D"])
    assert o["exit"] == ["A"]
    assert o["enter"] == ["D"]
    assert o["hold"] == ["B", "C"]


def test_ledger_roundtrip(tmp_path):
    p = tmp_path / "led.json"
    led = paper.PaperLedger(as_of="2026-01-01", holdings=["A"], equity=10000.0)
    led.record("2026-01-02", ["A", "B"], 10100.0)
    led.save(p)
    back = paper.PaperLedger.load(p)
    assert back.as_of == "2026-01-02"
    assert back.holdings == ["A", "B"]
    assert len(back.history) == 1  # the previous state was archived


def test_live_targets_only_picks_signalling_longs():
    # One clearly-rising symbol + one falling: with regime/mtf off, the riser should be
    # picked (long-signalling, high momentum), the faller should not dominate.
    idx = pd.date_range("2021-01-01", periods=200, freq="4h")
    up = pd.Series(np.linspace(100, 300, 200), index=idx)
    down = pd.Series(np.linspace(300, 100, 200), index=idx)
    frames = {s: pd.DataFrame({"open": v, "high": v + 1, "low": v - 1, "close": v,
                               "volume": 1.0}, index=idx) for s, v in [("UP", up), ("DOWN", down)]}
    cfg = BacktestConfig(orchestrator=OrchestratorConfig(use_regime=False, use_mtf=False))
    sel = paper.live_targets(frames, cfg, top_k=1, mom_window=20)
    assert sel == ["UP"]
