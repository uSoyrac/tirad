"""Ortak veri tipleri (stdlib only)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Sequence, Tuple


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "İŞLEM YOK"


class Bias(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class SwingType(str, Enum):
    HIGH = "high"
    LOW = "low"


@dataclass(frozen=True)
class Candle:
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


# OHLCV serisi = sıralı Candle listesi (eskiden -> yeniye)
Series = List[Candle]


@dataclass(frozen=True)
class Swing:
    index: int
    price: float
    kind: SwingType


@dataclass(frozen=True)
class StructureEvent:
    index: int          # olayın onaylandığı mum
    kind: str           # "BOS" | "CHoCH"
    bias: Bias          # kırılımın yönü
    level: float        # kırılan swing seviyesi
    swing_index: int    # kırılan swing'in mum indeksi


@dataclass(frozen=True)
class FVG:
    index: int          # ortadaki (agresif) mum
    bias: Bias
    top: float
    bottom: float
    filled: bool = False

    @property
    def mid(self) -> float:
        return (self.top + self.bottom) / 2.0

    @property
    def size(self) -> float:
        return self.top - self.bottom


@dataclass(frozen=True)
class OrderBlock:
    index: int
    bias: Bias          # bullish (talep) / bearish (arz)
    top: float
    bottom: float

    @property
    def mid(self) -> float:
        return (self.top + self.bottom) / 2.0


@dataclass(frozen=True)
class LiquidityPool:
    price: float
    kind: str           # "BSL" (üstte) | "SSL" (altta)
    indices: Tuple[int, ...]


@dataclass(frozen=True)
class Sweep:
    index: int
    kind: str           # "BSL" | "SSL"
    level: float


@dataclass(frozen=True)
class PDArray:
    range_high: float
    range_low: float

    @property
    def equilibrium(self) -> float:
        return (self.range_high + self.range_low) / 2.0

    def zone(self, price: float) -> str:
        if price > self.equilibrium:
            return "premium"
        if price < self.equilibrium:
            return "discount"
        return "equilibrium"


@dataclass
class Setup:
    side: Side
    entry: float
    stop: float
    target: float
    timeframe: str = ""
    symbol: str = ""
    reasons: List[str] = field(default_factory=list)
    rejected: Optional[str] = None

    @property
    def valid(self) -> bool:
        return self.rejected is None and self.side in (Side.LONG, Side.SHORT)

    @property
    def stop_pct(self) -> float:
        if self.entry == 0:
            return 0.0
        return abs(self.entry - self.stop) / self.entry * 100.0

    @property
    def rr(self) -> float:
        risk = abs(self.entry - self.stop)
        reward = abs(self.target - self.entry)
        if risk == 0:
            return 0.0
        return reward / risk


# --- küçük yardımcılar (pandas yerine) ---

def highs(c: Sequence[Candle]) -> List[float]:
    return [x.high for x in c]


def lows(c: Sequence[Candle]) -> List[float]:
    return [x.low for x in c]


def closes(c: Sequence[Candle]) -> List[float]:
    return [x.close for x in c]


def opens(c: Sequence[Candle]) -> List[float]:
    return [x.open for x in c]
