"""Test için sentetik OHLCV üreticileri (stdlib)."""

from __future__ import annotations

import os
import sys
from typing import List, Sequence

# price/ kökünü import yoluna ekle
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pa.types import Candle  # noqa: E402


def c(o: float, h: float, l: float, cl: float, v: float = 1.0) -> tuple:
    return (o, h, l, cl, v)


def make(rows: Sequence[tuple]) -> List[Candle]:
    out: List[Candle] = []
    for i, r in enumerate(rows):
        o, h, l, cl, v = r
        out.append(Candle(ts=i * 3600_000, open=o, high=h, low=l, close=cl, volume=v))
    return out
