"""Explicit, configurable trading frictions: slippage, fees, funding.

Kept tiny and pure so each piece is independently testable and there is no place
for a cost to be silently dropped. The harness calls these on every fill.
"""

from __future__ import annotations

from ..config import CostConfig


def fill_price(mid: float, side: int, slippage_bps: float) -> float:
    """Adverse slippage: buys fill higher, sells fill lower.

    side: +1 to buy (open long / close short), -1 to sell (open short / close long).
    """
    return mid * (1.0 + side * slippage_bps / 10_000.0)


def fee(notional: float, cfg: CostConfig, *, maker: bool = False) -> float:
    """Absolute fee for a fill of the given notional (always positive)."""
    rate = cfg.maker_fee if maker else cfg.taker_fee
    return abs(notional) * rate


def funding_payment(notional_signed: float, cfg: CostConfig, rate: float | None = None) -> float:
    """Funding for one interval. Positive return = cash LEAVES the account.

    Convention: when the funding rate is positive, longs pay shorts. A long
    (notional_signed > 0) therefore pays; a short receives.
    """
    if not cfg.funding_enabled:
        return 0.0
    r = cfg.flat_funding_rate if rate is None else rate
    return notional_signed * r
