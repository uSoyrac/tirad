"""Fair Value Gap (FVG) / imbalance (stdlib).

3 mumlu yapı (i-1, i, i+1):
- Bullish FVG: low[i+1] > high[i-1]  → boşluk [high[i-1], low[i+1]]
- Bearish FVG: high[i+1] < low[i-1]  → boşluk [high[i+1], low[i-1]]

Orta (i) agresif mum. Fiyat sonradan boşluğa dönerse filled=True.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from .types import FVG, Bias, Candle


def find_fvgs(candles: Sequence[Candle], min_size_pct: float = 0.0) -> List[FVG]:
    n = len(candles)
    out: List[FVG] = []
    for i in range(1, n - 1):
        prev, mid, nxt = candles[i - 1], candles[i], candles[i + 1]
        if nxt.low > prev.high:  # bullish
            bottom, top = prev.high, nxt.low
            if _passes(top, bottom, mid.close, min_size_pct):
                filled = any(x.low <= bottom for x in candles[i + 2:])
                out.append(FVG(i, Bias.BULLISH, top, bottom, filled))
        elif nxt.high < prev.low:  # bearish
            bottom, top = nxt.high, prev.low
            if _passes(top, bottom, mid.close, min_size_pct):
                filled = any(x.high >= top for x in candles[i + 2:])
                out.append(FVG(i, Bias.BEARISH, top, bottom, filled))
    return out


def _passes(top: float, bottom: float, ref: float, min_size_pct: float) -> bool:
    if min_size_pct <= 0 or ref == 0:
        return True
    return (top - bottom) / ref * 100.0 >= min_size_pct


def open_fvgs(fvgs: Sequence[FVG], bias: Optional[Bias] = None) -> List[FVG]:
    res = [f for f in fvgs if not f.filled]
    if bias is not None:
        res = [f for f in res if f.bias == bias]
    return res
