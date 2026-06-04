import numpy as np
import pandas as pd

from quantlab.config import load_config
from quantlab.paper import combo_book


def _universe(ncoins=8, n=400, seed=0):
    rng = np.random.default_rng(seed)
    frames, fundings = {}, {}
    idx = pd.date_range("2024-01-01", periods=n, freq="4h")
    fidx = pd.date_range("2024-01-01", periods=n // 2, freq="8h")
    for i in range(ncoins):
        close = 100 + np.cumsum(rng.normal(0.05, 1.0, n))
        close = np.maximum(close, 1.0)
        openp = np.concatenate([[close[0]], close[:-1]])
        frames[f"C{i}"] = pd.DataFrame(
            {"open": openp, "high": close + 1, "low": close - 1, "close": close,
             "volume": rng.uniform(50, 150, n)}, index=idx)
        fundings[f"C{i}"] = pd.Series(rng.normal(0.0001, 0.0004, len(fidx)), index=fidx)
    return frames, fundings


def test_build_book_structure_and_faithfulness(tmp_path):
    cfg = load_config(str(__import__("pathlib").Path(__file__).resolve().parents[1]
                          / "config" / "default.yaml"))
    # shrink the train cut so the synthetic 2024 data has an OOS slice
    cfg.splits.train_end = pd.Timestamp("2024-01-20").date()
    frames, fundings = _universe()
    book = combo_book.build_book(frames, fundings, cfg)

    for k in ("as_of", "weights", "holdings", "nav_now", "oos_sharpe_to_date", "nav_series"):
        assert k in book
    assert set(book["holdings"]) == {"trend_long", "funding_long", "funding_short"}
    # weights sum ~1 (inverse-vol blend)
    assert abs(book["weights"]["trend"] + book["weights"]["funding"] - 1.0) < 0.05
    # holdings are valid coins
    for leg in book["holdings"].values():
        assert set(leg).issubset(set(frames))
    # nav series present and positive
    assert len(book["nav_series"]) > 0
    assert all(v > 0 for v in book["nav_series"].values())

    # ledger round-trip
    p = tmp_path / "book.json"
    combo_book.save_ledger(book, p)
    import json
    back = json.loads(p.read_text())
    assert back["as_of"] == book["as_of"]
