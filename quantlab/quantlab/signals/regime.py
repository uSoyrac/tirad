"""Regime agent — the core idea: only trade when a real trend is present.

Classifies each bar as trending vs choppy from ADX, Kaufman efficiency ratio and
(optionally) the Hurst exponent. The gate is the AND of the enabled conditions, so
the system stays flat in chop instead of feeding fake trends to the sizer.

All features are causal; `regime_features` also returns the raw values so Phase 3's
ML quality filter can consume them without recomputation.
"""

from __future__ import annotations

import pandas as pd

from ..config import BacktestConfig
from ..indicators import adx, efficiency_ratio, hurst_exponent


def regime_features(df: pd.DataFrame, cfg: BacktestConfig) -> pd.DataFrame:
    rc = cfg.regime
    cols = {
        "adx": adx(df, rc.adx_period),
        "er": efficiency_ratio(df, rc.er_period),
    }
    if rc.use_hurst:
        cols["hurst"] = hurst_exponent(df, rc.hurst_period)
    return pd.DataFrame(cols, index=df.index)


def is_trending(df: pd.DataFrame, cfg: BacktestConfig) -> pd.Series:
    """Boolean gate per bar: True = trending regime, trading allowed."""
    rc = cfg.regime
    feats = regime_features(df, cfg)
    gate = pd.Series(True, index=df.index)
    if rc.use_adx:
        gate &= feats["adx"].fillna(0.0) >= rc.adx_threshold
    if rc.use_efficiency_ratio:
        gate &= feats["er"].fillna(0.0) >= rc.er_threshold
    if rc.use_hurst:
        gate &= feats["hurst"].fillna(0.0) >= rc.hurst_threshold
    return gate.rename("trending")
