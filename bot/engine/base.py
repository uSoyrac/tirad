"""
bot/engine/base.py — Temel veri yapıları ve soyut sınıflar
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Enum'lar, dataclass'lar, ABC tanımları.
Hiçbir hesaplama içermez — sadece tip tanımları.
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd


# ══════════════════════════════════════════════════════════════════════
#  ENUM'LAR
# ══════════════════════════════════════════════════════════════════════

class Trend(str, enum.Enum):
    """Piyasa yapısı yönü."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class Session(str, enum.Enum):
    """Kripto işlem seansları (UTC)."""

    ASIA       = "ASIA"       # 00:00–07:00 UTC
    LONDON     = "LONDON"     # 07:00–12:00 UTC
    NEW_YORK   = "NEW_YORK"   # 12:00–20:00 UTC
    OVERLAP    = "OVERLAP"    # 12:00–16:00 UTC (London+NY)
    OFF_HOURS  = "OFF_HOURS"  # 20:00–00:00 UTC


class Action(str, enum.Enum):
    """İşlem kararı."""

    STRONG_BUY  = "STRONG_BUY"
    BUY         = "BUY"
    HOLD        = "HOLD"
    SELL        = "SELL"
    STRONG_SELL = "STRONG_SELL"
    BLOCKED     = "BLOCKED"
    TREND_HUNTER_LONG  = "TREND_HUNTER_LONG"
    TREND_HUNTER_SHORT = "TREND_HUNTER_SHORT"


# ══════════════════════════════════════════════════════════════════════
#  MARKET STRUCTURE RESULT
# ══════════════════════════════════════════════════════════════════════

@dataclass
class MarketStructure:
    """
    SMC/ICT piyasa yapısı sonucu.

    Attributes:
        trend:       Genel yön (BOS/CHoCH'dan türetilen).
        bos_bull:    Son 3 mum önceki swing high'ı kapattı.
        bos_bear:    Son 3 mum önceki swing low'u kapattı.
        choch_bull:  Bearish yapıda yukarı kırılma (reversal).
        choch_bear:  Bullish yapıda aşağı kırılma (reversal).
        bull_obs:    Aktif bullish order block listesi.
        bear_obs:    Aktif bearish order block listesi.
        bull_fvg:    Doldurulmamış bullish FVG listesi.
        bear_fvg:    Doldurulmamış bearish FVG listesi.
        ote:         OTE Fibonacci geri çekilme analizi.
        liq_sweep_up:  BSL süpürmesi tespiti.
        liq_sweep_dn:  SSL süpürmesi tespiti.
        composite_score: 0-10 SMC ham skoru.
        entry_price:   Önerilen giriş fiyatı.
        sl_price:      Stop-loss fiyatı.
    """

    trend:           Trend            = Trend.NEUTRAL
    bos_bull:        bool             = False
    bos_bear:        bool             = False
    choch_bull:      bool             = False
    choch_bear:      bool             = False
    bull_obs:        List[dict]       = field(default_factory=list)
    bear_obs:        List[dict]       = field(default_factory=list)
    bull_fvg:        List[dict]       = field(default_factory=list)
    bear_fvg:        List[dict]       = field(default_factory=list)
    ote:             Optional[dict]   = None
    liq_sweep_up:    bool             = False
    liq_sweep_dn:    bool             = False
    composite_score: float            = 0.0
    entry_price:     float            = 0.0
    sl_price:        float            = 0.0


# ══════════════════════════════════════════════════════════════════════
#  CONFLUENCE SCORE
# ══════════════════════════════════════════════════════════════════════

@dataclass
class ConfluenceScore:
    """
    Gelişmiş gösterge skor bileşeni.

    Her alt skor kendi aralığında (genellikle -2 ile +2.5) gelir.
    ``total`` 0-10 aralığına normalize edilmiş birleşik skordur.
    ``confirmation_count`` ≥3 olması önerilir (yumuşak eşik).

    Attributes:
        ib_score:       Initial Balance kırılma/ret skoru.
        adr_score:      ADR kullanım skoru (exhausted = negatif).
        poc_score:      POC + SMC çakışma skoru.
        oi_score:       Open Interest delta skoru.
        fr_score:       Funding Rate kontrarian skoru.
        session_score:  Aktif seans ağırlık skoru.
        vwap_score:     VWAP bant pozisyon skoru.
        wyckoff_score:  Wyckoff Spring/UTAD skoru.
        total:          Normalize birleşik skor (0-10).
        confirmation_count: Pozitif katkı veren gösterge sayısı.
        adr_blocked:    True → ADR tükenmiş; hard gate tetiklendi.
        details:        Her gösterge için ham değer sözlüğü.
    """

    ib_score:           float       = 0.0
    adr_score:          float       = 0.0
    poc_score:          float       = 0.0
    oi_score:           float       = 0.0
    fr_score:           float       = 0.0
    session_score:      float       = 0.0
    vwap_score:         float       = 0.0
    wyckoff_score:      float       = 0.0
    total:              float       = 0.0
    confirmation_count: int         = 0
    adr_blocked:        bool        = False
    details:            Dict        = field(default_factory=dict)


# ══════════════════════════════════════════════════════════════════════
#  FILTER RESULT
# ══════════════════════════════════════════════════════════════════════

@dataclass
class FilterResult:
    """
    Hard gate (sert filtre) çıktısı.

    Attributes:
        blocked: True → işlem kesinlikle açılmaz.
        reason:  Engellenme nedeni (debug için).
        warnings: Yumuşak uyarılar (engellemez ama dikkat gerektirir).
    """

    blocked:  bool       = False
    reason:   str        = ""
    warnings: List[str]  = field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════
#  SIGNAL RESULT  (ana çıktı)
# ══════════════════════════════════════════════════════════════════════

@dataclass
class SignalResult:
    """
    Tam sinyal paketi — SignalEngine.analyze() çıktısı.

    Attributes:
        symbol:        İşlem çifti ("ETH/USDT").
        action:        Önerilen eylem.
        direction:     "LONG" veya "SHORT".
        composite:     0-10 nihai ağırlıklı skor.
        smc_score:     SMC/ICT katman skoru.
        adv_score:     Gelişmiş gösterge skoru.
        entry_price:   Giriş fiyatı.
        sl_price:      Stop-loss.
        tp1_price:     Birinci kâr hedefi.
        tp2_price:     İkinci kâr hedefi.
        tp3_price:     Üçüncü kâr hedefi.
        atr_value:     ATR değeri (SL/TP hesabında kullanıldı).
        confirmations: Pozitif katkı veren gösterge sayısı.
        filter_warnings: Engelleyen olmayan ama dikkat gerektiren uyarılar.
        market_structure: Ham MarketStructure nesnesi.
        confluence:    Ham ConfluenceScore nesnesi.
        session:       Aktif seans bilgisi.
        funding_rate:  Güncel funding rate (varsa).
        timestamp:     Sinyal üretim zamanı (ISO string).
    """

    symbol:           str
    action:           Action
    direction:        str
    composite:        float
    smc_score:        float
    adv_score:        float
    entry_price:      float
    sl_price:         float
    tp1_price:        float
    tp2_price:        float
    tp3_price:        float
    atr_value:        float              = 0.0
    confirmations:    int                = 0
    filter_warnings:  List[str]          = field(default_factory=list)
    market_structure: Optional[MarketStructure] = None
    confluence:       Optional[ConfluenceScore]  = None
    session:          str                = "UNKNOWN"
    funding_rate:     Optional[float]    = None
    timestamp:        str                = ""
    is_ignition:      bool               = False


# ══════════════════════════════════════════════════════════════════════
#  SOYUT TEMEL SINIF
# ══════════════════════════════════════════════════════════════════════

class BaseAnalyzer(ABC):
    """
    Tüm analizör sınıflarının soyut temel sınıfı.

    Her alt sınıf kendi ``analyze()`` metodunu uygulamalıdır.
    DataFrame her zaman 4H candlestick (OHLCV) varsayılır.
    """

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

    @abstractmethod
    def analyze(self, df: pd.DataFrame) -> object:
        """
        DataFrame alır, spesifik analiz nesnesi döner.

        Args:
            df: 4H OHLCV verisi, index datetime, en az 100 satır.

        Returns:
            Analizöre özgü sonuç nesnesi.
        """
        ...
