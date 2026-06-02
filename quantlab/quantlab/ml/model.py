"""LightGBM signal-quality model wrapper.

Thin, deterministic wrapper: fit on a training matrix, predict P(profitable). Trees
need no feature scaling and handle NaN natively, so there is no fitted preprocessing
state that could leak across the train/OOS boundary. The model is intentionally
small (see MLConfig) — we want generalisation, not in-sample memorisation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import BacktestConfig


class SignalQualityModel:
    def __init__(self, cfg: BacktestConfig):
        self.cfg = cfg
        self.model = None
        self.columns: list[str] | None = None

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "SignalQualityModel":
        from lightgbm import LGBMClassifier

        ml = self.cfg.ml
        self.columns = list(X.columns)
        self.model = LGBMClassifier(
            n_estimators=ml.n_estimators,
            num_leaves=ml.num_leaves,
            max_depth=ml.max_depth,
            learning_rate=ml.learning_rate,
            min_child_samples=ml.min_child_samples,
            subsample=ml.subsample,
            colsample_bytree=ml.colsample_bytree,
            reg_lambda=ml.reg_lambda,
            random_state=self.cfg.seed,
            n_jobs=1,
            verbose=-1,
        )
        self.model.fit(X.to_numpy(), y.to_numpy())
        return self

    def predict_proba(self, X: pd.DataFrame) -> pd.Series:
        if self.model is None:
            raise RuntimeError("model not fitted")
        cols = X[self.columns] if self.columns else X
        proba = self.model.predict_proba(cols.to_numpy())[:, 1]
        return pd.Series(proba, index=X.index, name="proba")

    def feature_importance(self) -> pd.Series:
        if self.model is None:
            raise RuntimeError("model not fitted")
        return pd.Series(self.model.feature_importances_, index=self.columns).sort_values(
            ascending=False
        )


def single_class_proba(X: pd.DataFrame, value: float) -> pd.Series:
    """Fallback when a training set is degenerate (one class): constant probability."""
    return pd.Series(np.full(len(X), value), index=X.index, name="proba")
