"""Causal feature matrix for the signal-quality model.

Every column at bar t uses ONLY data <= t. Features reuse the SAME agent/regime/MTF
code paths the live system uses, so there is no train/serve skew. A dedicated test
asserts the whole matrix is causal by the truncation property.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import BacktestConfig
from ..indicators import atr
from ..signals import ensemble, mtf, regime

# Lookback windows for the price-action / volume features.
_RET_WINDOWS = (1, 3, 6, 12)
_VOL_WINDOW = 20


def build_features(df: pd.DataFrame, cfg: BacktestConfig, higher_df: pd.DataFrame | None = None) -> pd.DataFrame:
    feats = {}

    # 1) Signal-agent scores + ensemble net (agents 2 in the architecture).
    scores = ensemble.ensemble_scores(df, cfg)
    for col in scores.columns:
        feats[f"agent_{col}"] = scores[col]

    # 2) Regime features (agent 3).
    reg = regime.regime_features(df, cfg)
    for col in reg.columns:
        feats[f"regime_{col}"] = reg[col]

    # 3) Multi-timeframe agreement (agent 5).
    if cfg.orchestrator.use_mtf and higher_df is not None:
        feats["mtf_dir"] = mtf.higher_tf_direction(df, higher_df, cfg)

    # 4) Price-action / volume features (agent 4 + price action).
    a = atr(df, cfg.risk.atr_period)
    feats["atr_pct"] = a / df["close"]  # volatility regime, scale-free
    for w in _RET_WINDOWS:
        feats[f"ret_{w}"] = df["close"].pct_change(w)
    # distance from trailing extremes, in ATR units (causal: includes current bar)
    feats["dist_high_atr"] = (df["close"] - df["high"].rolling(_VOL_WINDOW).max()) / a
    feats["dist_low_atr"] = (df["close"] - df["low"].rolling(_VOL_WINDOW).min()) / a
    # volume thrust: current volume vs its trailing average
    vol_ma = df["volume"].rolling(_VOL_WINDOW).mean()
    feats["vol_ratio"] = df["volume"] / vol_ma.replace(0.0, np.nan)

    out = pd.DataFrame(feats, index=df.index)
    return out.replace([np.inf, -np.inf], np.nan)


def feature_columns(df: pd.DataFrame, cfg: BacktestConfig, higher_df=None) -> list[str]:
    return list(build_features(df, cfg, higher_df).columns)
