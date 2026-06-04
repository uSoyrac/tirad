"""Orthogonal ALT-DATA features for the signal-quality model.

Price-derived features gave a coin-flip AUC (Phase 3). Funding and open-interest carry
DIFFERENT information — crowd positioning, leverage, cross-exchange dislocation — that
price alone cannot see. These are the features that *might* lift the correct-decision
rate. All causal: a value at bar t uses only funding/OI known at or before t (funding
is stamped at its settlement time and merged backward; OI is shifted).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _funding_on_grid(funding: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    """Most-recent funding rate known at each bar (backward as-of, no look-ahead)."""
    f = funding.sort_index()
    merged = pd.merge_asof(pd.DataFrame({"ts": index}), f.rename("f").reset_index().rename(
        columns={f.index.name or "index": "ts", "ts": "ts"}), on="ts", direction="backward")
    return pd.Series(merged["f"].to_numpy(), index=index)


def funding_features(df: pd.DataFrame, fundings_by_exch: dict[str, pd.Series]) -> pd.DataFrame:
    """Funding level / trend / extreme / cross-exchange-spread features (causal)."""
    idx = df.index
    out = {}
    # primary exchange (binance) funding on the bar grid
    base = fundings_by_exch.get("binance")
    if base is not None:
        f = _funding_on_grid(base, idx)
        out["fund_now"] = f
        out["fund_mean_7d"] = f.rolling(42, min_periods=10).mean()      # 7d of 4h bars
        out["fund_mean_1d"] = f.rolling(6, min_periods=3).mean()
        sd = f.rolling(42, min_periods=10).std()
        out["fund_z"] = (f - out["fund_mean_7d"]) / sd.replace(0.0, np.nan)
        out["fund_mom"] = out["fund_mean_1d"] - out["fund_mean_7d"]     # positioning building
    # cross-exchange dislocation: binance vs mean(bybit, okx)
    others = [fundings_by_exch[e] for e in ("bybit", "okx") if e in fundings_by_exch]
    if base is not None and others:
        oth = pd.concat([_funding_on_grid(o, idx) for o in others], axis=1).mean(axis=1)
        out["fund_xexch_spread"] = _funding_on_grid(base, idx) - oth
    return pd.DataFrame(out, index=idx).replace([np.inf, -np.inf], np.nan)


def oi_features(df: pd.DataFrame, oi_df: pd.DataFrame | None) -> pd.DataFrame:
    """Open-interest / long-short-ratio features (causal; NaN before data starts)."""
    idx = df.index
    out = {}
    if oi_df is not None and len(oi_df):
        oi = oi_df.reindex(idx).ffill()
        if "oi" in oi:
            out["oi_chg_1d"] = oi["oi"].pct_change(6)
            out["oi_chg_3d"] = oi["oi"].pct_change(18)
        if "toptrader_ls_ratio" in oi:
            out["toptrader_ls"] = oi["toptrader_ls_ratio"]
            out["toptrader_ls_chg"] = oi["toptrader_ls_ratio"].diff(6)
        if "ls_ratio" in oi:
            out["ls_ratio"] = oi["ls_ratio"]
        if "taker_buy_sell_ratio" in oi:
            out["taker_bs"] = oi["taker_buy_sell_ratio"]
    # all features shifted one bar so the metric for bar t is known by t's decision
    feats = pd.DataFrame(out, index=idx)
    return feats.shift(1).replace([np.inf, -np.inf], np.nan) if len(out) else feats
