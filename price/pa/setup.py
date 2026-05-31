"""Setup zinciri (stdlib) — yapısal sinyalleri tek işlem fikrine birleştirir.

Zincir (ICT): likidite süpürülür → CHoCH/BOS → fiyat OB/FVG'ye çeker →
giriş orada, invalidasyon süpürülen seviyenin ötesinde, hedef bir sonraki
likidite havuzu. Zincir tamamlanmaz veya R/R yetersizse Setup.rejected dolar.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from .types import Bias, Candle, LiquidityPool, Setup, Side
from .structure import detect_structure
from .imbalance import find_fvgs, open_fvgs
from .orderblock import find_order_blocks, nearest_unmitigated
from .liquidity import find_sweeps, find_liquidity_pools

MIN_RR = 2.0
RECENT_WINDOW = 10


def build_setup(
    candles: Sequence[Candle], *, k: int = 2, timeframe: str = "",
    symbol: str = "", min_rr: float = MIN_RR, recent: int = RECENT_WINDOW,
) -> Setup:
    n = len(candles)
    if n < 4 * k + 5:
        return _reject(timeframe, symbol, "yetersiz mum sayısı")

    price = candles[-1].close
    events, trend = detect_structure(candles, k=k)
    sweeps = find_sweeps(candles, k=k)
    pools = find_liquidity_pools(candles, k=k)
    obs = find_order_blocks(candles)
    fvgs = find_fvgs(candles)
    last_idx = n - 1
    reasons: List[str] = []

    # 1) güncel yapı yönü
    if trend == Bias.NEUTRAL:
        return _reject(timeframe, symbol, "yapı nötr (BOS/CHoCH yok)")
    side = Side.LONG if trend == Bias.BULLISH else Side.SHORT
    reasons.append(f"Yapı {trend.value}: son kırılım yönü {side.value}")

    # 2) son kırılım taze mi?
    recent_events = [e for e in events
                     if e.index >= last_idx - recent and e.bias == trend]
    if not recent_events:
        return _reject(timeframe, symbol,
                       "yakın geçmişte yön ile uyumlu BOS/CHoCH yok")
    ev = recent_events[-1]
    reasons.append(f"{ev.kind} @ {ev.level:.4f} (mum {ev.index})")

    # 3) sweep oldu mu?
    want_sweep = "SSL" if side == Side.LONG else "BSL"
    sweep = next((s for s in reversed(sweeps)
                  if s.kind == want_sweep and s.index >= last_idx - recent), None)
    if sweep is None:
        return _reject(timeframe, symbol, "sweep yok (sweep'siz girişten kaçın)")
    reasons.append(f"{sweep.kind} sweep @ {sweep.level:.4f} (mum {sweep.index})")

    # 4) giriş: taze OB; yoksa açık FVG
    ob = nearest_unmitigated(obs, price, trend, candles)
    if ob is not None:
        entry = ob.mid
        zone_lo, zone_hi = ob.bottom, ob.top
        reasons.append(f"Giriş OB {ob.bottom:.4f}-{ob.top:.4f}")
    else:
        ofvg = open_fvgs(fvgs, bias=trend)
        if not ofvg:
            return _reject(timeframe, symbol, "giriş için OB/FVG yok")
        f = min(ofvg, key=lambda x: abs(x.mid - price))
        entry = f.mid
        zone_lo, zone_hi = f.bottom, f.top
        reasons.append(f"Giriş FVG {f.bottom:.4f}-{f.top:.4f}")

    # 5) stop: giriş bölgesinin (OB/FVG) ötesi — yapısal invalidasyon.
    #    Fiyat POI'yi ters yönde geçerse fikir geçersiz. Sweep seviyesi
    #    bölgenin de ötesindeyse (POI sweep mumunda oluştuysa) onu kullan;
    #    böylece stop hem yapısal hem mümkün olduğunca dar kalır.
    pad = (zone_hi - zone_lo) * 0.1
    if side == Side.LONG:
        base = zone_lo if sweep.level >= zone_lo else sweep.level
        stop = base - pad
    else:
        base = zone_hi if sweep.level <= zone_hi else sweep.level
        stop = base + pad
    reasons.append(f"Stop {stop:.4f} (giriş bölgesi ötesi; sweep {sweep.level:.4f} teyit)")

    # 6) hedef: yön yönünde bir sonraki likidite havuzu
    target = _next_pool_target(pools, entry, side)
    if target is None:
        return _reject(timeframe, symbol, "hedef likidite havuzu yok")
    reasons.append(f"Hedef {target:.4f} (sonraki likidite havuzu)")

    setup = Setup(side=side, entry=entry, stop=stop, target=target,
                  timeframe=timeframe, symbol=symbol, reasons=reasons)

    # 7) R/R denetimi
    if setup.rr < min_rr:
        setup.rejected = f"R/R yetersiz ({setup.rr:.2f} < {min_rr:.1f})"
    return setup


def _next_pool_target(pools: Sequence[LiquidityPool], entry: float,
                      side: Side) -> Optional[float]:
    if side == Side.LONG:
        above = [p.price for p in pools if p.kind == "BSL" and p.price > entry]
        return min(above) if above else None
    below = [p.price for p in pools if p.kind == "SSL" and p.price < entry]
    return max(below) if below else None


def _reject(timeframe: str, symbol: str, why: str) -> Setup:
    return Setup(side=Side.NONE, entry=0, stop=0, target=0,
                 timeframe=timeframe, symbol=symbol, rejected=why)
