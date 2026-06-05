"""
Claude API ile doğal dil trade özeti üretimi.
Sadece skor >= min_score_for_synthesis olan assetler için çağrılır.
Prompt caching ile maliyet optimizasyonu.
"""
import logging
import os

import anthropic

from analysis.composite_scorer import CompositeScore
from signals.trade_setup import TradeSetup
from signals.position_sizer import PositionSize

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """Sen uzman bir kripto ve borsa teknik analistsin. Görevin:
1. Verilen teknik analiz verilerini yorumlamak
2. Trade setini kısa, net Türkçe olarak özetlemek
3. Kullanıcıya somut tavsiye vermek (giriş/çıkış seviyeleri dahil)
4. Risk uyarısı eklemek

Yanıtın formatı:
- Maksimum 250 kelime
- Net, profesyonel ton
- Jargonu minimumda tut
- Her zaman risk uyarısı ekle"""


def build_analysis_prompt(
    score: CompositeScore,
    setup: TradeSetup | None,
    pos: PositionSize | None,
) -> str:
    parts = [
        f"Asset: {score.symbol} ({score.asset_type.upper()})",
        f"Yön: {score.direction} | Composite Skor: {score.composite:.1f}/10",
        f"Sinyal: {score.signal_level}",
        "",
        "SMC Tespitler:",
    ]

    for k, v in score.smc_details.items():
        parts.append(f"  - {v}")

    parts.append("\nKlasik İndikatörler:")
    for k, v in score.classic_details.items():
        parts.append(f"  - {v}")

    parts.append("\nKurumsal Metrikler:")
    for k, v in score.institutional_details.items():
        parts.append(f"  - {v}")

    if score.mtf_details:
        parts.append("\nMulti-Timeframe:")
        for k, v in score.mtf_details.items():
            parts.append(f"  - {v}")

    if score.social_details:
        parts.append("\nSosyal Analiz:")
        for k, v in score.social_details.items():
            parts.append(f"  - {v}")

    if setup and setup.valid:
        parts.extend([
            "",
            "Trade Setup:",
            f"  Giriş: {setup.entry_low:.4f} — {setup.entry_high:.4f}",
            f"  Stop Loss: {setup.stop_loss:.4f} (-%{setup.sl_pct*100:.1f})",
            f"  TP1: {setup.tp1:.4f} (+%{setup.tp1_pct*100:.1f}) → %40 kapat",
            f"  TP2: {setup.tp2:.4f} (+%{setup.tp2_pct*100:.1f}) → %35 kapat",
            f"  TP3: {setup.tp3:.4f} (+%{setup.tp3_pct*100:.1f}) → %25 kapat",
        ])

    if pos:
        parts.extend([
            f"  Kaldıraç: {pos.leverage}x",
            f"  Pozisyon: ${pos.position_size:.0f} (%2 risk = ${pos.risk_amount:.0f})",
        ])

    parts.extend([
        "",
        "Bu verilere dayanarak kısa ve net bir değerlendirme yap. "
        "Önemli riskleri vurgula. Türkçe yanıtla.",
    ])

    return "\n".join(parts)


def synthesize_with_claude(
    score: CompositeScore,
    setup: TradeSetup | None = None,
    pos: PositionSize | None = None,
    config: dict = None,
) -> str:
    """
    Claude Sonnet ile trade özeti üretir.
    API key yoksa veya skor düşükse boş string döner.
    """
    if config is None:
        config = {}

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY yok — Claude sentetizi atlanıyor")
        return ""

    min_score = config.get("min_score_for_synthesis", 6.0)
    if score.composite < min_score:
        return ""

    model = config.get("model", "claude-sonnet-4-6")
    max_tokens = config.get("max_tokens", 1500)
    temperature = config.get("temperature", 0.1)

    client = anthropic.Anthropic(api_key=api_key)

    prompt = build_analysis_prompt(score, setup, pos)

    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},  # Prompt caching
                }
            ],
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        )
        return response.content[0].text
    except Exception as e:
        logger.error(f"Claude API hatası: {e}")
        return f"[Claude analizi alınamadı: {e}]"
