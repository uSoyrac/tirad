"""Risk ve kaldıraç hesabı (stdlib).

Kural: stop_yüzdesi × kaldıraç < 90 (90 ve üzeri reddedilir).
max kaldıraç = kuralı sağlayan en yüksek standart kademe; öneri için bir
kademe düşülür (tampon).

Pozisyon büyüklüğü: işlem başına risk portföyün %1-2'si; notional stop
mesafesine göre ölçeklenir.
"""

from __future__ import annotations

from dataclasses import dataclass

LEVERAGE_LADDER = [1, 2, 3, 5, 10, 15, 20, 25, 30, 40, 50, 75, 100, 125]
MAX_RATIO = 90.0  # stop% × kaldıraç bunun ALTINDA olmalı


@dataclass(frozen=True)
class LeveragePlan:
    stop_pct: float
    max_leverage: int
    recommended: int
    feasible: bool

    def describe(self) -> str:
        if not self.feasible:
            return (f"Stop %{self.stop_pct:.2f} çok geniş; "
                    f"1x bile kuralı (stop%×kald<90) sağlamıyor.")
        return (f"max {self.max_leverage}x, önerilen {self.recommended}x "
                f"(stop %{self.stop_pct:.2f} × kaldıraç < {MAX_RATIO:.0f})")


def leverage_plan(stop_pct: float) -> LeveragePlan:
    if stop_pct <= 0:
        raise ValueError("stop_pct pozitif olmalı")
    feasible = [l for l in LEVERAGE_LADDER if l * stop_pct < MAX_RATIO]
    if not feasible:
        return LeveragePlan(stop_pct, 0, 0, False)
    max_lev = max(feasible)
    idx = LEVERAGE_LADDER.index(max_lev)
    recommended = LEVERAGE_LADDER[idx - 1] if idx > 0 else max_lev
    return LeveragePlan(stop_pct, max_lev, recommended, True)


@dataclass(frozen=True)
class PositionSize:
    risk_amount: float
    notional: float
    margin: float


def position_size(portfolio: float, stop_pct: float, leverage: int,
                  risk_pct: float = 1.0) -> PositionSize:
    if not 0 < risk_pct <= 100:
        raise ValueError("risk_pct 0-100 aralığında olmalı")
    if stop_pct <= 0:
        raise ValueError("stop_pct pozitif olmalı")
    risk_amount = portfolio * risk_pct / 100.0
    notional = risk_amount / (stop_pct / 100.0)
    margin = notional / leverage if leverage else float("inf")
    return PositionSize(risk_amount, notional, margin)
