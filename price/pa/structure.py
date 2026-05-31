"""Market structure — swing tespiti ve BOS/CHoCH (stdlib).

- Swing: fractal. i mumu, sol/sağ k mum içinde TEK katı tepe/dipse swing'dir.
  Swing ancak k mum sonra ONAYLANIR (look-ahead yok: olaylar onay mumunda
  damgalanır).
- Yapı: referans, EN SON onaylanmış swing high/low'dur (en yüksek/en düşük
  değil — SMC'de yapı en güncel ilgili swing üzerinden okunur). Kapanış son
  swing high üstüne geçerse yukarı, son swing low altına geçerse aşağı kırılım.
  Mevcut trend yönündeyse BOS, ters yöndeyse CHoCH (ve trend döner). Kırılan
  referans tüketilir; yeni swing onaylanınca yeni referans olur.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from .types import Bias, Candle, StructureEvent, Swing, SwingType


def find_swings(candles: Sequence[Candle], k: int = 2) -> List[Swing]:
    n = len(candles)
    swings: List[Swing] = []
    for i in range(k, n - k):
        hi = candles[i].high
        lo = candles[i].low
        win = candles[i - k:i + k + 1]
        win_h = [x.high for x in win]
        win_l = [x.low for x in win]
        if hi == max(win_h) and win_h.count(hi) == 1:
            swings.append(Swing(index=i, price=hi, kind=SwingType.HIGH))
        elif lo == min(win_l) and win_l.count(lo) == 1:
            swings.append(Swing(index=i, price=lo, kind=SwingType.LOW))
    return swings


def detect_structure(
    candles: Sequence[Candle], k: int = 2
) -> Tuple[List[StructureEvent], Bias]:
    """BOS/CHoCH olaylarını ve güncel bias'ı döndür."""
    swings = find_swings(candles, k=k)
    n = len(candles)

    by_confirm: Dict[int, List[Swing]] = {}
    for s in swings:
        c = s.index + k
        if c < n:
            by_confirm.setdefault(c, []).append(s)

    events: List[StructureEvent] = []
    active_high: Optional[Swing] = None
    active_low: Optional[Swing] = None
    trend = Bias.NEUTRAL

    for i in range(n):
        close = candles[i].close

        if active_high is not None and close > active_high.price:
            kind = "CHoCH" if trend == Bias.BEARISH else "BOS"
            events.append(StructureEvent(
                index=i, kind=kind, bias=Bias.BULLISH,
                level=active_high.price, swing_index=active_high.index))
            trend = Bias.BULLISH
            active_high = None

        elif active_low is not None and close < active_low.price:
            kind = "CHoCH" if trend == Bias.BULLISH else "BOS"
            events.append(StructureEvent(
                index=i, kind=kind, bias=Bias.BEARISH,
                level=active_low.price, swing_index=active_low.index))
            trend = Bias.BEARISH
            active_low = None

        # bu mumda onaylanan swing'ler EN SON referans olur
        for s in by_confirm.get(i, []):
            if s.kind == SwingType.HIGH:
                active_high = s
            else:
                active_low = s

    return events, trend
