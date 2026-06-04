"""Position sizing — a SEPARATE module from signal generation.

Default and only policy: fixed-fractional risk. Risk a fixed fraction of CURRENT
equity per trade, sized off the stop distance, capped by max leverage.

There is deliberately NO martingale / loss-recovery logic here. Sizing depends only
on (equity, stop distance, price) — never on the prior trade's outcome. A test
asserts this independence so the property can't silently regress.
"""

from __future__ import annotations

from ..config import RiskConfig


def fixed_fractional_units(
    equity: float,
    entry_price: float,
    stop_distance: float,
    cfg: RiskConfig,
) -> float:
    """Units to trade so that a stop-out loses ~risk_per_trade * equity.

    units = (risk_fraction * equity) / stop_distance, then capped so that
    notional <= max_leverage * equity. Returns 0.0 if inputs are degenerate.
    """
    if equity <= 0 or entry_price <= 0 or stop_distance <= 0:
        return 0.0
    risk_amount = cfg.risk_per_trade * equity
    units = risk_amount / stop_distance
    max_units_by_leverage = cfg.max_leverage * equity / entry_price
    return min(units, max_units_by_leverage)
