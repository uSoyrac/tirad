"""Pooled meta-label QUALITY GATE for the trend sleeve.

Trains ONE LightGBM quality model on the pooled cross-sectional candidates in the
TRAIN window (≤ train_end), then vetoes long entries whose predicted P(win) is below
a train-chosen coverage threshold. This is the productionised form of the
run_metalabel finding (pooling lifts price-feature AUC to ~0.56; gating the top-X%
raises win rate and flips expectancy positive OOS).

Causality: the model is fit only on ≤train_end data, so its verdicts on the OOS
window are leak-free. (On the in-sample window the gate is, by construction,
in-sample — judge the gate on OOS.)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import BacktestConfig
from . import dataset, features as featmod
from .labels import triple_barrier_labels
from .model import SignalQualityModel


def _features(df, higher, cfg, use_regression: bool):
    """Base meta-label features, optionally enriched with the regression family
    (rolling-OLS slope + R² trend-cleanliness — the one family with OOS AUC lift)."""
    X = featmod.build_features(df, cfg, higher)
    if use_regression:
        from ..research.orderflow import build_orderflow_features
        of, fam = build_orderflow_features(df, None, None)
        X = pd.concat([X, of[fam["regression"]]], axis=1)
    return X


def train_gate(frames: dict, higher: dict, cfg: BacktestConfig, *, keep_top: float = 0.5,
               use_regression: bool = False):
    """Train the pooled quality model on TRAIN candidates; return (model, threshold).

    keep_top = fraction of candidates to KEEP (0.5 ⇒ veto the bottom-half by P(win)).
    """
    cut = pd.Timestamp(cfg.splits.train_end) + pd.Timedelta(days=1)
    Xs, ys = [], []
    for s, df in frames.items():
        X = _features(df, higher.get(s), cfg, use_regression)
        y = triple_barrier_labels(df, cfg)
        mask = dataset.candidate_long_mask(df, cfg, higher.get(s))
        sel = mask & y.notna() & (df.index < cut)
        if sel.any():
            Xs.append(X[sel])
            ys.append(y[sel].astype(int))
    Xtr = pd.concat(Xs)
    ytr = pd.concat(ys)
    model = SignalQualityModel(cfg).fit(Xtr, ytr)
    proba_tr = model.predict_proba(Xtr)
    threshold = float(np.quantile(proba_tr, 1.0 - keep_top))
    return model, threshold


def gate_targets(frames: dict, higher: dict, targets: dict, model, threshold: float,
                 cfg: BacktestConfig, *, use_regression: bool = False) -> dict:
    """Zero out long entries whose predicted quality is below threshold."""
    gated = {}
    for s, df in frames.items():
        X = _features(df, higher.get(s), cfg, use_regression)
        proba = model.predict_proba(X).reindex(df.index)
        keep = (proba >= threshold).fillna(False)
        t = targets[s].copy()
        # only veto long entries; never create or flip a position
        gated[s] = t.where(~((t > 0) & ~keep), 0.0)
    return gated
