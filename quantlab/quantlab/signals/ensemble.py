"""Combine signal agents into a single target-direction series for the harness.

net = sum(w_i * score_i) / sum(|w_i|)  -> in [-1, 1]
Target: a position is taken only when |net| clears `entry_threshold`.
  spot: long (1) / flat (0)        perp: long (1) / short (-1) / flat (0)

Returns BOTH the target series AND the per-agent score frame, so Phase 3's ML
quality filter can reuse the agent scores as features without recomputation.
"""

from __future__ import annotations

import pandas as pd

from ..config import BacktestConfig
from .agents import REGISTRY


def ensemble_scores(df: pd.DataFrame, cfg: BacktestConfig) -> pd.DataFrame:
    """Per-agent scores plus the weighted 'net' column, aligned to df.index."""
    cols = {}
    total_w = 0.0
    net = pd.Series(0.0, index=df.index)
    for spec in cfg.ensemble.agents:
        fn = REGISTRY[spec.name]
        s = fn(df, **spec.params).reindex(df.index).fillna(0.0)
        cols[spec.name] = s
        net = net + spec.weight * s
        total_w += abs(spec.weight)
    net = net / total_w if total_w > 0 else net
    out = pd.DataFrame(cols)
    out["net"] = net
    return out


def target_from_net(net: pd.Series, cfg: BacktestConfig) -> pd.Series:
    thr = cfg.ensemble.entry_threshold
    if cfg.data.market_type == "spot":
        target = (net >= thr).astype(float)  # long / flat
    else:
        target = pd.Series(0.0, index=net.index)
        target[net >= thr] = 1.0
        target[net <= -thr] = -1.0
    return target.rename("signal")


def signal(df: pd.DataFrame, cfg: BacktestConfig) -> pd.Series:
    """Convenience: ensemble target-direction series for the harness."""
    scores = ensemble_scores(df, cfg)
    return target_from_net(scores["net"], cfg)
