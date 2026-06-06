"""Orchestrator — combine the ensemble signal with the regime and MTF filters.

Final decision per bar:
  * start from the ensemble target (spot: long/flat, perp: long/short/flat)
  * if regime filter on: require a TRENDING regime, else flat
  * if MTF filter on: require the higher timeframe to AGREE with the direction

This is where the ML quality filter (Phase 3) and threshold tuning (Phase 4) will
also plug in. Returns the final target series for the harness, plus (optionally) the
decision breakdown for inspection / future ML features.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import BacktestConfig
from .signals import ensemble, mean_reversion, mtf, regime


def build_target(
    df: pd.DataFrame,
    cfg: BacktestConfig,
    higher_df: pd.DataFrame | None = None,
    *,
    ml_proba: pd.Series | None = None,
    ml_threshold: float | None = None,
    return_breakdown: bool = False,
):
    """Combine ensemble + filters (+ optional ML quality gate) into a final target.

    If `ml_proba` is given, a long entry additionally requires
    P(profitable) >= ml_threshold at that bar. Bars without a probability (NaN /
    uncovered by walk-forward) are NOT vetoed by the ML gate — the rule filters still
    apply. Passing ml_proba lets the caller control exactly which (leak-free)
    predictions gate the entries.
    """
    oc = cfg.orchestrator
    base = ensemble.signal(df, cfg)  # ensemble target (already spot/perp aware)
    cols = {"ensemble_target": base}

    if ml_proba is not None:
        thr = cfg.ml.threshold if ml_threshold is None else ml_threshold
        proba_np = ml_proba.reindex(df.index).to_numpy()
        cols["ml_proba"] = ml_proba.reindex(df.index)
    else:
        proba_np = None
        thr = 0.0

    # Per-bar regime gate (direction-independent) and MTF direction.
    trending = regime.is_trending(df, cfg) if oc.use_regime else pd.Series(True, index=df.index)
    if oc.use_regime:
        cols["trending"] = trending.astype(float)
    if oc.use_mtf:
        if higher_df is None:
            raise ValueError("use_mtf=True requires higher_df")
        hdir = mtf.higher_tf_direction(df, higher_df, cfg)
        cols["mtf_dir"] = hdir
    else:
        hdir = pd.Series(0.0, index=df.index)

    # entry_ok[t]: is a NEW position in the base direction permitted at bar t?
    base_np = base.to_numpy()
    trend_np = trending.to_numpy()
    hdir_np = hdir.to_numpy()
    mtf_on = oc.use_mtf

    def entry_ok(i: int) -> bool:
        if not trend_np[i]:
            return False
        if mtf_on and np.sign(base_np[i]) != np.sign(hdir_np[i]):
            return False
        if proba_np is not None:
            p = proba_np[i]
            # only the ML-covered bars get vetoed; NaN (uncovered) passes the gate
            if p == p and base_np[i] > 0 and p < thr:
                return False
        return True

    if oc.gate_mode == "continuous":
        ok = np.array([entry_ok(i) for i in range(len(df))])
        final_np = np.where(ok, base_np, 0.0)
    else:  # entry_only: filters block entries; hold/exit follow the ensemble
        final_np = np.zeros(len(df))
        p = 0.0
        for i in range(len(df)):
            b = base_np[i]
            if b == 0.0:
                p = 0.0
            elif b == p:
                pass  # hold through regime dips — don't chop the trend
            else:  # entering (from flat or reversing): require the gate
                p = b if entry_ok(i) else 0.0
            final_np[i] = p

    # ---- mean-reversion sleeve: fill CHOP bars (where trend sleeve is flat) ----
    if oc.use_mr_sleeve and oc.use_regime:
        mr_np = mean_reversion.signal(df, cfg).to_numpy()
        cols["mr_target"] = pd.Series(mr_np, index=df.index)
        for i in range(len(df)):
            if final_np[i] == 0.0 and not trend_np[i]:  # flat & in chop
                final_np[i] = mr_np[i]

    final = pd.Series(final_np, index=df.index, name="signal")
    if return_breakdown:
        cols["final_target"] = final
        return final, pd.DataFrame(cols, index=df.index)
    return final
