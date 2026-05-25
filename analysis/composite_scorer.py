"""
Composite Scorer — tüm analiz katmanlarını birleştirir.
Toplam max puan: SMC:10 + Klasik:10 + Kurumsal:7 + MTF:4 + Sosyal:6 = 37
Normalize: (ham_puan / 37) × 10 → 0-10 arası
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime

from analysis.smc_engine import SMCResult
from analysis.classic_indicators import ClassicResult
from analysis.institutional import InstitutionalResult

logger = logging.getLogger(__name__)

MAX_TOTAL = 37.0
STRONG_SIGNAL = 8.0
MEDIUM_SIGNAL = 6.0
WATCHLIST = 4.0


@dataclass
class CompositeScore:
    symbol: str
    asset_type: str  # 'crypto' or 'bist'
    timestamp: str = ""
    direction: str = "NEUTRAL"

    # Ham puanlar
    smc_score: float = 0.0
    classic_score: float = 0.0
    institutional_score: float = 0.0
    mtf_score: float = 0.0
    social_score: float = 0.0

    # Normalize edilmiş final skor (0-10)
    composite: float = 0.0

    # Ham toplam
    raw_total: float = 0.0

    # Sinyal seviyesi
    signal_level: str = "NO_SIGNAL"  # STRONG, MEDIUM, WATCHLIST, NO_SIGNAL

    # Fiyat bilgisi
    current_price: float | None = None
    trend: str = "NEUTRAL"

    # Detaylar
    smc_details: dict = field(default_factory=dict)
    classic_details: dict = field(default_factory=dict)
    institutional_details: dict = field(default_factory=dict)
    mtf_details: dict = field(default_factory=dict)
    social_details: dict = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"{self.symbol} | {self.signal_level} | "
            f"Skor: {self.composite:.1f}/10 | Yön: {self.direction}"
        )


def compute_mtf_score(tf_trends: dict) -> tuple[float, dict]:
    """
    Multi-timeframe confluence puanlaması.
    tf_trends: {'1w': 'BULLISH'/'BEARISH'/'NEUTRAL', '1d': ..., '4h': ..., '1h': ...}
    """
    details = {}

    if not tf_trends:
        return 0.0, details

    primary = tf_trends.get("4h", "NEUTRAL")
    if primary == "NEUTRAL":
        return 0.0, {"mtf": "4H Nötr — MTF skor 0"}

    tfs = ["1w", "1d", "4h", "1h"]
    aligned = [t for t in tfs if tf_trends.get(t) == primary]
    count = len(aligned)

    if count == 4:
        score = 4.0
        details["mtf"] = f"Tam MTF Uyum ({', '.join(tfs)}) ✅ (+4)"
    elif count == 3 and "4h" in aligned:
        score = 2.0
        details["mtf"] = f"3 TF Uyum ({', '.join(aligned)}) ✅ (+2)"
    elif count == 2 and "4h" in aligned and "1h" in aligned:
        score = 1.0
        details["mtf"] = f"4H+1H Uyum ✅ (+1)"
    else:
        score = 0.0
        details["mtf"] = "Çelişkili TF (0)"

    return min(score, 4.0), details


def compute_social_score(social_data: dict | None) -> tuple[float, dict]:
    """
    Sosyal puan hesaplama.
    social_data: {
        'sentiment': 0-1,
        'source_count': int,
        'platform_count': int,
        'bullish_ratio': 0-1,
        'mention_count': int,
    }
    """
    if not social_data:
        return 0.0, {"social": "Sosyal veri yok (0)"}

    score = 0.0
    details = {}

    sentiment = social_data.get("sentiment", 0)
    platform_count = social_data.get("platform_count", 0)
    bullish_ratio = social_data.get("bullish_ratio", 0)
    mention_count = social_data.get("mention_count", 0)

    # Sentiment (0-3 puan)
    if sentiment >= 0.65:
        score += 3.0
        details["sentiment"] = f"Güçlü Pozitif Sentiment {sentiment:.2f} ✅ (+3)"
    elif sentiment >= 0.5:
        score += 1.5
        details["sentiment"] = f"Nötr-Pozitif Sentiment {sentiment:.2f} (+1.5)"

    # Platform çeşitliliği (0-2 puan)
    if platform_count >= 3:
        score += 2.0
        details["platforms"] = f"{platform_count} Farklı Platform ✅ (+2)"
    elif platform_count >= 2:
        score += 1.0
        details["platforms"] = f"{platform_count} Platform (+1)"

    # Consensus (0-1 puan)
    if bullish_ratio >= 0.6:
        score += 1.0
        details["consensus"] = f"Boğa Consensus {bullish_ratio:.0%} ✅ (+1)"

    return min(score, 6.0), details


def score_to_signal_level(score: float) -> str:
    if score >= STRONG_SIGNAL:
        return "STRONG"
    elif score >= MEDIUM_SIGNAL:
        return "MEDIUM"
    elif score >= WATCHLIST:
        return "WATCHLIST"
    return "NO_SIGNAL"


def compute_composite(
    symbol: str,
    asset_type: str,
    smc: SMCResult,
    classic: ClassicResult,
    institutional: InstitutionalResult,
    tf_trends: dict = None,
    social_data: dict = None,
) -> CompositeScore:
    """
    Tüm bileşenleri birleştirip normalize edilmiş CompositeScore döndürür.
    """
    result = CompositeScore(
        symbol=symbol,
        asset_type=asset_type,
        timestamp=datetime.utcnow().isoformat(),
    )

    # Puanlar
    result.smc_score = smc.score
    result.classic_score = classic.score
    result.institutional_score = institutional.score

    mtf_score, mtf_details = compute_mtf_score(tf_trends or {})
    result.mtf_score = mtf_score

    social_score, social_details = compute_social_score(social_data)
    result.social_score = social_score

    # Toplam ve normalize
    result.raw_total = (
        result.smc_score + result.classic_score + result.institutional_score
        + result.mtf_score + result.social_score
    )
    result.composite = round((result.raw_total / MAX_TOTAL) * 10, 2)

    # Yön belirleme
    result.trend = smc.trend
    result.direction = smc.trend  # SMC trendi ana yön

    # Sinyal seviyesi
    result.signal_level = score_to_signal_level(result.composite)

    # Fiyat
    result.current_price = classic.current_price

    # Detaylar
    result.smc_details = smc.details
    result.classic_details = classic.details
    result.institutional_details = institutional.details
    result.mtf_details = mtf_details
    result.social_details = social_details

    logger.info(
        f"{symbol}: composite={result.composite:.2f}/10 | "
        f"SMC={result.smc_score:.1f} | Classic={result.classic_score:.1f} | "
        f"Institutional={result.institutional_score:.1f} | MTF={result.mtf_score:.1f} | "
        f"Social={result.social_score:.1f} → {result.signal_level}"
    )

    return result
