"""Walk-forward out-of-fold prediction.

For each rolling window, train the signal-quality model on the window's TRAIN slice
and predict on its TEST slice. Concatenating the test predictions yields one
out-of-fold probability per covered bar — every prediction comes from a model that
saw only strictly-earlier data, so there is no leakage anywhere in the curve.

This is the honest substrate for both the AUC in/out gap and the gated backtest.
"""

from __future__ import annotations

import pandas as pd

from ..config import BacktestConfig
from ..backtest.splits import walk_forward
from . import dataset
from .model import SignalQualityModel


def wf_oof_proba(df: pd.DataFrame, cfg: BacktestConfig, higher_df=None):
    """Return (proba, info).

    proba: out-of-fold P(profitable) Series indexed by covered TEST bars.
    info: dict with per-window diagnostics (train size, class balance, skipped).
    """
    X, y, mask = dataset.assemble(df, cfg, higher_df)
    windows = walk_forward(df, cfg.splits)

    pieces = []
    info = {"windows": [], "skipped": 0}
    for w in windows:
        Xtr, ytr = dataset.training_rows(X, y, mask, w.train.index)
        if len(Xtr) < cfg.ml.min_train_samples or ytr.nunique() < 2:
            info["skipped"] += 1
            info["windows"].append({"label": w.label, "n_train": int(len(Xtr)), "trained": False})
            continue
        model = SignalQualityModel(cfg).fit(Xtr, ytr)
        Xte = X.loc[w.test.index]
        proba = model.predict_proba(Xte)
        pieces.append(proba)
        info["windows"].append({
            "label": w.label, "n_train": int(len(Xtr)),
            "pos_rate": float(ytr.mean()), "trained": True,
        })

    if not pieces:
        return pd.Series(dtype=float, name="proba"), info
    # later windows overwrite earlier on any index overlap (step <= test => possible)
    proba = pd.concat(pieces)
    proba = proba[~proba.index.duplicated(keep="last")].sort_index()
    return proba, info
