"""
Trade Setup Hesaplamaları: Giriş bölgesi, Stop Loss, Take Profit.
"""
import logging
from dataclasses import dataclass

from analysis.smc_engine import SMCResult
from analysis.composite_scorer import CompositeScore

logger = logging.getLogger(__name__)


@dataclass
class TradeSetup:
    symbol: str
    direction: str  # LONG / SHORT
    entry_low: float
    entry_high: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    sl_pct: float
    tp1_pct: float
    tp2_pct: float
    tp3_pct: float
    valid: bool = True
    invalid_reason: str = ""


def calculate_trade_setup(
    score: CompositeScore,
    smc: SMCResult,
    current_price: float,
    config: dict = None,
) -> TradeSetup | None:
    """
    Giriş/SL/TP hesaplar.
    SL kuralı: OB alt sınırının %0.5 altı, max -%8.
    """
    if config is None:
        config = {}

    direction = score.direction
    if direction == "NEUTRAL":
        return None

    sl_buffer = config.get("sl_buffer", 0.005)
    max_sl = config.get("max_sl_distance", 0.08)
    tp_targets = config.get("tp_targets", {"tp1": 0.06, "tp2": 0.14, "tp3": 0.28})

    if direction == "BULLISH" or direction == "LONG":
        dir_label = "LONG"

        # Giriş bölgesi: Bullish OB tercih, yoksa FVG orta noktası
        if smc.bullish_ob_low is not None and smc.bullish_ob_high is not None:
            entry_low = smc.bullish_ob_low
            entry_high = smc.bullish_ob_high
        elif smc.fvg_bullish:
            fvg = smc.fvg_bullish[0]
            mid = fvg["mid"]
            entry_low = mid * 0.995
            entry_high = mid * 1.005
        else:
            # Fallback: Mevcut fiyata göre yakın destek
            entry_low = current_price * 0.985
            entry_high = current_price * 1.002

        # Stop Loss
        if smc.bullish_ob_low is not None:
            sl = smc.bullish_ob_low * (1 - sl_buffer)
        else:
            sl = entry_low * (1 - 0.03)  # Minimum %3

        entry_mid = (entry_low + entry_high) / 2
        sl_pct = (entry_mid - sl) / entry_mid

        # SL çok geniş → setup geçersiz
        if sl_pct > max_sl:
            return TradeSetup(
                symbol=score.symbol, direction=dir_label,
                entry_low=entry_low, entry_high=entry_high,
                stop_loss=sl, tp1=0, tp2=0, tp3=0,
                sl_pct=sl_pct, tp1_pct=0, tp2_pct=0, tp3_pct=0,
                valid=False, invalid_reason=f"SL çok geniş: %{sl_pct*100:.1f} > %{max_sl*100:.0f}",
            )

        # Take Profits
        tp1 = entry_mid * (1 + tp_targets["tp1"])
        tp2 = entry_mid * (1 + tp_targets["tp2"])
        tp3 = entry_mid * (1 + tp_targets["tp3"])

        # FVG ve OB hedefleri varsa öncelik ver
        if smc.fvg_bearish and smc.fvg_bearish[0]["mid"] > entry_mid:
            tp1 = smc.fvg_bearish[0]["mid"]
        if smc.bearish_ob is not None and smc.bearish_ob > entry_mid:
            tp2 = smc.bearish_ob

    elif direction == "BEARISH" or direction == "SHORT":
        dir_label = "SHORT"

        if smc.bearish_ob_low is not None and smc.bearish_ob_high is not None:
            entry_low = smc.bearish_ob_low
            entry_high = smc.bearish_ob_high
        elif smc.fvg_bearish:
            fvg = smc.fvg_bearish[0]
            mid = fvg["mid"]
            entry_low = mid * 0.995
            entry_high = mid * 1.005
        else:
            entry_low = current_price * 0.998
            entry_high = current_price * 1.015

        entry_mid = (entry_low + entry_high) / 2

        if smc.bearish_ob_high is not None:
            sl = smc.bearish_ob_high * (1 + sl_buffer)
        else:
            sl = entry_high * (1 + 0.03)

        sl_pct = (sl - entry_mid) / entry_mid

        if sl_pct > max_sl:
            return TradeSetup(
                symbol=score.symbol, direction=dir_label,
                entry_low=entry_low, entry_high=entry_high,
                stop_loss=sl, tp1=0, tp2=0, tp3=0,
                sl_pct=sl_pct, tp1_pct=0, tp2_pct=0, tp3_pct=0,
                valid=False, invalid_reason=f"SL çok geniş: %{sl_pct*100:.1f} > %{max_sl*100:.0f}",
            )

        tp1 = entry_mid * (1 - tp_targets["tp1"])
        tp2 = entry_mid * (1 - tp_targets["tp2"])
        tp3 = entry_mid * (1 - tp_targets["tp3"])

        if smc.fvg_bullish and smc.fvg_bullish[0]["mid"] < entry_mid:
            tp1 = smc.fvg_bullish[0]["mid"]

    else:
        return None

    return TradeSetup(
        symbol=score.symbol,
        direction=dir_label,
        entry_low=round(entry_low, 6),
        entry_high=round(entry_high, 6),
        stop_loss=round(sl, 6),
        tp1=round(tp1, 6),
        tp2=round(tp2, 6),
        tp3=round(tp3, 6),
        sl_pct=round(sl_pct, 4),
        tp1_pct=round(abs(tp1 - entry_mid) / entry_mid, 4),
        tp2_pct=round(abs(tp2 - entry_mid) / entry_mid, 4),
        tp3_pct=round(abs(tp3 - entry_mid) / entry_mid, 4),
        valid=True,
    )
