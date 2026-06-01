"""Order Block tespiti (stdlib).

Bullish OB: güçlü yükselişten önceki SON düşüş mumu (talep).
Bearish OB: güçlü düşüşten önceki SON yükseliş mumu (arz).

"Güçlü hareket" (displacement): OB sonrası `impulse` mum içindeki yer
değiştirme, OB gövdesinin `mult` katından büyük ve OB'yi terk etmeli.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from .types import Bias, Candle, OrderBlock


def find_order_blocks(
    candles: Sequence[Candle], impulse: int = 3, mult: float = 1.0
) -> List[OrderBlock]:
    n = len(candles)
    out: List[OrderBlock] = []
    for i in range(n - impulse):
        c = candles[i]
        body = abs(c.close - c.open)
        after = candles[i + 1:i + 1 + impulse]
        hi_after = max(x.high for x in after)
        lo_after = min(x.low for x in after)

        if c.close < c.open:  # bullish OB
            disp = hi_after - c.close
            if disp >= mult * max(body, 1e-9) and hi_after > c.high:
                out.append(OrderBlock(i, Bias.BULLISH, c.high, c.low))
        elif c.close > c.open:  # bearish OB
            disp = c.close - lo_after
            if disp >= mult * max(body, 1e-9) and lo_after < c.low:
                out.append(OrderBlock(i, Bias.BEARISH, c.high, c.low))
    return out


def nearest_unmitigated(
    obs: Sequence[OrderBlock], price: float, bias: Bias,
    candles: Sequence[Candle],
) -> Optional[OrderBlock]:
    """Bias'ta, fiyata en yakın, henüz tekrar test edilmemiş OB; yoksa en
    yakını."""
    cand = [ob for ob in obs if ob.bias == bias]
    if not cand:
        return None

    def mitigated(ob: OrderBlock) -> bool:
        after = candles[ob.index + 1:]
        if bias == Bias.BULLISH:
            return any(x.low <= ob.top for x in after)
        return any(x.high >= ob.bottom for x in after)

    fresh = [ob for ob in cand if not mitigated(ob)]
    pool = fresh or cand
    return min(pool, key=lambda ob: abs(ob.mid - price))
