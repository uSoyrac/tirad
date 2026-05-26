"""
Pozisyon büyüklüğü ve kaldıraç hesaplama.
Sabit %2 risk kuralı, max 5x kaldıraç.
"""
from dataclasses import dataclass

from analysis.composite_scorer import CompositeScore
from signals.trade_setup import TradeSetup


@dataclass
class PositionSize:
    balance: float
    risk_amount: float
    position_size: float
    leverage: int
    risk_pct: float = 0.02


def calculate_position(
    setup: TradeSetup,
    score: CompositeScore,
    balance: float,
    risk_pct: float = 0.02,
    max_leverage: int = 5,
) -> PositionSize:
    """
    risk_tutarı = bakiye × risk_pct
    pozisyon_büyüklüğü = risk_tutarı / sl_mesafesi
    kaldıraç = min(max_leverage, pozisyon / spot_pozisyon)
    """
    risk_amount = balance * risk_pct

    if setup.sl_pct <= 0:
        return PositionSize(balance, risk_amount, balance * 0.1, 1)

    position_size = risk_amount / setup.sl_pct

    # Kaldıraç: skor bazlı
    composite = score.composite
    if composite >= 8.0:
        base_leverage = max_leverage  # 5x
    elif composite >= 7.0:
        base_leverage = min(max_leverage, 3)  # 3x
    elif composite >= 6.0:
        base_leverage = min(max_leverage, 2)  # 2x
    else:
        base_leverage = 1  # 1x

    # Gerçek kaldıraç: pozisyon / bakiye
    required_leverage = position_size / balance
    leverage = min(int(required_leverage) + 1, base_leverage, max_leverage)
    leverage = max(leverage, 1)

    return PositionSize(
        balance=balance,
        risk_amount=round(risk_amount, 2),
        position_size=round(position_size, 2),
        leverage=leverage,
        risk_pct=risk_pct,
    )
