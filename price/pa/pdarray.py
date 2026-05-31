"""Premium / Discount (PD array) — stdlib.

Referans range'in (son lookback mumun en yüksek/en düşüğü) %50 üstü premium
(satış), altı discount (alış), tam %50 equilibrium.
"""

from __future__ import annotations

from typing import Optional, Sequence

from .types import Candle, PDArray


def build_pd_array(candles: Sequence[Candle],
                   lookback: Optional[int] = None) -> PDArray:
    window = candles if lookback is None else candles[-lookback:]
    return PDArray(
        range_high=max(c.high for c in window),
        range_low=min(c.low for c in window),
    )
