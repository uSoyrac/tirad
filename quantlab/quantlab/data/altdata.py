"""Loaders for orthogonal alt-data: open-interest / long-short-ratio metrics."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_oi_metrics(path: str | Path) -> pd.DataFrame:
    """Read a metrics CSV (ts,oi,oi_value,toptrader_ls_ratio,ls_ratio,taker_buy_sell_ratio)."""
    df = pd.read_csv(path)
    df["ts"] = pd.to_datetime(df["ts"], utc=False)
    df = df.set_index("ts").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df.astype("float64")
