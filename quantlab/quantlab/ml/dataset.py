"""Assemble the training dataset: candidate long bars -> (features, label).

A 'candidate' is a bar where the rule-based system would consider a LONG entry:
ensemble says long AND the regime/MTF filters permit it. The ML filter's job is to
predict which of those candidates actually pay off, so we train and predict on
exactly that population.
"""

from __future__ import annotations

import pandas as pd

from ..config import BacktestConfig
from ..signals import ensemble, mtf, regime
from . import features as featmod
from .labels import triple_barrier_labels


def candidate_long_mask(df: pd.DataFrame, cfg: BacktestConfig, higher_df=None) -> pd.Series:
    """Bars where the rule system would permit a long entry (pre-ML)."""
    scores = ensemble.ensemble_scores(df, cfg)
    mask = scores["net"] >= cfg.ensemble.entry_threshold
    if cfg.orchestrator.use_regime:
        mask &= regime.is_trending(df, cfg)
    if cfg.orchestrator.use_mtf and higher_df is not None:
        mask &= mtf.higher_tf_direction(df, higher_df, cfg) > 0
    return mask.rename("candidate")


def assemble(df: pd.DataFrame, cfg: BacktestConfig, higher_df=None):
    """Return (X, y, candidate_mask) aligned to df.index.

    X = full causal feature matrix; y = triple-barrier labels (NaN where unresolved);
    candidate_mask = where a long entry is permitted by the rules.
    """
    X = featmod.build_features(df, cfg, higher_df)
    y = triple_barrier_labels(df, cfg)
    mask = candidate_long_mask(df, cfg, higher_df)
    return X, y, mask


def training_rows(X: pd.DataFrame, y: pd.Series, mask: pd.Series, index_subset: pd.Index):
    """Rows usable for training: candidate, resolved label, within the given window."""
    sel = mask & y.notna() & X.index.isin(index_subset)
    # require features present (LightGBM tolerates NaN, but drop all-NaN rows)
    sel &= X.notna().any(axis=1)
    return X.loc[sel], y.loc[sel].astype(int)
