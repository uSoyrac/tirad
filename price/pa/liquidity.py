"""Likidite — eşit high/low havuzları ve liquidity sweep / stop hunt (stdlib).

- Equal highs (BSL): birbirine tol% yakın swing high kümesi → üstte stop.
- Equal lows (SSL): yakın swing low kümesi → altta stop.
- Sweep: fiyatın bir swing seviyesini fitille delip kapanışta geri dönmesi.
"""

from __future__ import annotations

from typing import List, Sequence

from .types import Candle, LiquidityPool, Sweep, Swing, SwingType
from .structure import find_swings


def find_liquidity_pools(
    candles: Sequence[Candle], k: int = 2, tol_pct: float = 0.1
) -> List[LiquidityPool]:
    swings = find_swings(candles, k=k)
    highs = [s for s in swings if s.kind == SwingType.HIGH]
    lows = [s for s in swings if s.kind == SwingType.LOW]
    pools: List[LiquidityPool] = []
    pools += _cluster(highs, "BSL", tol_pct)
    pools += _cluster(lows, "SSL", tol_pct)
    return pools


def _cluster(swings: List[Swing], kind: str, tol_pct: float) -> List[LiquidityPool]:
    out: List[LiquidityPool] = []
    used = [False] * len(swings)
    for i in range(len(swings)):
        if used[i]:
            continue
        group = [swings[i]]
        used[i] = True
        ref = swings[i].price
        for j in range(i + 1, len(swings)):
            if used[j]:
                continue
            if ref != 0 and abs(swings[j].price - ref) / ref * 100.0 <= tol_pct:
                group.append(swings[j])
                used[j] = True
        if len(group) >= 2:
            price = sum(s.price for s in group) / len(group)
            out.append(LiquidityPool(
                price=price, kind=kind,
                indices=tuple(s.index for s in group)))
    return out


def find_sweeps(candles: Sequence[Candle], k: int = 2) -> List[Sweep]:
    swings = find_swings(candles, k=k)
    sh = [s for s in swings if s.kind == SwingType.HIGH]
    sl = [s for s in swings if s.kind == SwingType.LOW]
    out: List[Sweep] = []
    for i, c in enumerate(candles):
        for s in sh:  # BSL sweep
            if s.index + k < i and c.high > s.price and c.close < s.price:
                out.append(Sweep(index=i, kind="BSL", level=s.price))
                break
        for s in sl:  # SSL sweep
            if s.index + k < i and c.low < s.price and c.close > s.price:
                out.append(Sweep(index=i, kind="SSL", level=s.price))
                break
    return out
