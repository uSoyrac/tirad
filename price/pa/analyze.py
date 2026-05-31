"""Çok zaman dilimli analiz + confluence filtresi (stdlib).

- Üst TF yönü ana filtredir; alt TF giriş zamanlamasıdır.
- TF'ler zıt yön gösterirse "işlem yok".
- Geçen setup için risk/kaldıraç planı eklenir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from .types import Bias, Candle, Setup, Side
from .structure import detect_structure
from .setup import build_setup
from .risk import LeveragePlan, leverage_plan

# (giriş, orta, filtre) zaman dilimleri
PROFILE_TFS = {
    "scalp": ("15m", "1h", "4h"),
    "intraday": ("1h", "4h", "1d"),
    "swing": ("4h", "1d", "1w"),
}


def htf_bias(candles: Sequence[Candle], k: int = 2) -> Bias:
    _, trend = detect_structure(candles, k=k)
    return trend


@dataclass
class AnalysisResult:
    setup: Setup
    plan: Optional[LeveragePlan] = None
    notes: List[str] = field(default_factory=list)


def analyze(
    entry_candles: Sequence[Candle],
    htf_candles: Optional[Sequence[Candle]] = None,
    *, entry_tf: str = "", htf_tf: str = "", symbol: str = "", k: int = 2,
) -> AnalysisResult:
    notes: List[str] = []

    if htf_candles is not None:
        h_bias = htf_bias(htf_candles, k=k)
        notes.append(f"Üst TF ({htf_tf or 'HTF'}) yönü: {h_bias.value}")
        if h_bias == Bias.NEUTRAL:
            notes.append("Üst TF nötr — confluence zayıf.")
    else:
        h_bias = None

    setup = build_setup(entry_candles, k=k, timeframe=entry_tf, symbol=symbol)

    if setup.valid and h_bias is not None and h_bias != Bias.NEUTRAL:
        want = Bias.BULLISH if setup.side == Side.LONG else Bias.BEARISH
        if h_bias != want:
            setup.rejected = (f"TF çelişkisi: giriş {setup.side.value} "
                              f"ama üst TF {h_bias.value}")

    plan: Optional[LeveragePlan] = None
    if setup.valid:
        plan = leverage_plan(setup.stop_pct)
        if not plan.feasible:
            setup.rejected = "stop çok geniş — kaldıraç kuralı sağlanamıyor"
            plan = None

    return AnalysisResult(setup=setup, plan=plan, notes=notes)
