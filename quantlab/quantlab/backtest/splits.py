"""Train / out-of-sample splitting and walk-forward windows.

The OOS window is never touched during optimisation. Walk-forward yields a series
of (train, test) windows that roll forward in time — test always strictly follows
its train, with no overlap.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..config import SplitConfig


@dataclass
class Window:
    train: pd.DataFrame
    test: pd.DataFrame
    label: str


def train_oos_split(df: pd.DataFrame, train_end) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Single split: bars on/before train_end are in-sample, the rest are OOS."""
    cut = pd.Timestamp(train_end) + pd.Timedelta(days=1)
    train = df[df.index < cut]
    oos = df[df.index >= cut]
    return train, oos


def walk_forward(df: pd.DataFrame, cfg: SplitConfig) -> list[Window]:
    """Rolling train/test windows. Each test window strictly follows its train."""
    windows: list[Window] = []
    start = df.index[0]
    end = df.index[-1]
    train_span = pd.DateOffset(months=cfg.train_months)
    test_span = pd.DateOffset(months=cfg.test_months)
    step = pd.DateOffset(months=cfg.step_months)

    train_start = start
    k = 0
    while True:
        train_end = train_start + train_span
        test_end = train_end + test_span
        if train_end > end:
            break
        train = df[(df.index >= train_start) & (df.index < train_end)]
        test = df[(df.index >= train_end) & (df.index < min(test_end, end + pd.Timedelta(days=1)))]
        if len(test) == 0:
            break
        windows.append(Window(train=train, test=test, label=f"wf{k}"))
        train_start = train_start + step
        k += 1
    return windows
