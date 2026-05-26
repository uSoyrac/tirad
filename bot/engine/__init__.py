"""
bot/engine — Optimal Sinyal Motoru v3
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OOP mimarisi, PEP 8, tam tip-anotasyonları.

Alt modüller:
  base            — Enum'lar, veri sınıfları, soyut temel
  market_structure — SMC/ICT çekirdek analizi
  confluence      — ADR, IB, POC, Funding, Session, VWAP skor birleştirici
  filters         — Sert kalite kapıları (hard gate)
  position_sizer  — Kelly + ATR tabanlı boyutlandırma
  signal_engine   — SignalEngine orkestratörü (ana giriş noktası)
"""

from bot.engine.base import Trend, SignalResult, FilterResult, ConfluenceScore
from bot.engine.signal_engine import SignalEngine

__all__ = [
    "SignalEngine",
    "SignalResult",
    "Trend",
    "FilterResult",
    "ConfluenceScore",
]
