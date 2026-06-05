"""
bot/engine/confluence.py — Çoklu Gösterge Uyum Skor Hesaplayıcı
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
İzlenen göstergeler:
  • Initial Balance (IB)     — Günlük ilk 2 mum kırılma/reddi
  • ADR                      — Günlük aralık tükenme kontrolü
  • POC + SMC Çakışması      — Hacim profili + OB/FVG kesişimi
  • Open Interest Delta       — OI + fiyat yön uyumu
  • Funding Rate              — Aşırı long/short → kontrarian fırsat
  • Seans Analizi             — Asia/London/NY ağırlık haritası
  • VWAP Bantları             — Uç sapma → ortalamaya dönüş fırsatı
  • Wyckoff Gelişmiş          — Spring/UTAD desen tespiti

Tasarım ilkeleri:
  • Tüm hesaplamalar yalnızca geçmiş veriye bakar.
  • Her gösterge bağımsız ölçeklenir, sonra birleştirilir.
  • ``adr_blocked`` → True ise TradeFilter hard gate'i tetikler.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import pandas as pd

from bot.engine.base import (
    ConfluenceScore,
    MarketStructure,
    Trend,
)

logger = logging.getLogger("bot.engine.confluence")

# ── Gösterge Ağırlıkları (0-10 normalize sonrası etki) ───────────────
# Toplamları = 1.0 → doğrudan ağırlıklı ortalama
_WEIGHT_IB       = 0.12
_WEIGHT_ADR      = 0.13   # ADR önemli: exhaustion = en sık kayıp nedeni
_WEIGHT_POC      = 0.18   # En yüksek: fiyat + hacim = güçlü kanıt
_WEIGHT_OI       = 0.15
_WEIGHT_FR       = 0.14   # Funding: kripto'ya özgü, yüksek tahmin gücü
_WEIGHT_SESSION  = 0.12
_WEIGHT_VWAP     = 0.10
_WEIGHT_WYCKOFF  = 0.06   # En belirsiz: düşük ağırlık


class ConfluenceScorer:
    """
    Gelişmiş göstergeleri birleştirerek 0-10 uyum skoru üretir.

    Kullanım:
        >>> scorer = ConfluenceScorer("ETH/USDT")
        >>> cs = scorer.score(df_4h, market_structure, oi_list, px_list, fr)
        >>> if cs.adr_blocked:
        ...     return None  # Tükenmiş piyasa — işlem açma
        >>> print(cs.total, cs.confirmation_count)

    Args:
        symbol:  İşlem çifti.
        min_confirmations: Önerilen minimum pozitif gösterge sayısı.
                           TradeFilter bu değeri kullanabilir.
    """

    def __init__(
        self,
        symbol:            str,
        min_confirmations: int = 3,
    ) -> None:
        self.symbol = symbol
        self.min_confirmations = min_confirmations

    # ──────────────────────────────────────────────────────────────────
    def score(
        self,
        df:          pd.DataFrame,
        ms:          MarketStructure,
        oi_series:   Optional[List[float]] = None,
        px_series:   Optional[List[float]] = None,
        funding_rate: Optional[float]      = None,
    ) -> ConfluenceScore:
        """
        Tüm gelişmiş göstergeleri hesaplayarak ConfluenceScore döner.

        Args:
            df:           4H OHLCV verisi.
            ms:           Önceden hesaplanmış MarketStructure.
            oi_series:    Son N dönemlik OI listesi (varsa).
            px_series:    OI ile eş zamanlı kapanış fiyatları.
            funding_rate: Güncel funding rate (varsa).

        Returns:
            ConfluenceScore (``adr_blocked`` özelliğini kontrol edin).
        """
        if df.empty or len(df) < 50:
            logger.debug(f"{self.symbol}: Yetersiz veri — confluence atlandı")
            return ConfluenceScore()

        try:
            return self._compute(df, ms, oi_series, px_series, funding_rate)
        except Exception as exc:
            logger.warning(f"{self.symbol} confluence hatası: {exc}", exc_info=True)
            return ConfluenceScore()

    # ──────────────────────────────────────────────────────────────────
    def _compute(
        self,
        df:           pd.DataFrame,
        ms:           MarketStructure,
        oi_series:    Optional[List[float]],
        px_series:    Optional[List[float]],
        funding_rate: Optional[float],
    ) -> ConfluenceScore:
        """İç hesaplama — tüm göstergeler çalıştırılır."""
        from bot.advanced_indicators import (
            initial_balance,
            average_daily_range,
            poc_smc_confluence,
            open_interest_signal,
            funding_rate_signal,
            session_analysis,
            vwap_bands,
            wyckoff_advanced,
        )

        direction = ms.trend.value  # "BULLISH" / "BEARISH"
        details: dict = {}

        # ── 1. Initial Balance ────────────────────────────────────
        ib_res      = initial_balance(df)
        ib_score    = float(ib_res.get("ib_score", 0.0))
        ib_score    = self._clamp(ib_score)
        details["ib"] = ib_res

        # ── 2. ADR (Average Daily Range) ──────────────────────────
        adr_res    = average_daily_range(df)
        adr_score  = float(adr_res.get("adr_score", 0.0))
        adr_signal = adr_res.get("adr_signal", "NEUTRAL")
        adr_blocked = adr_signal == "OVEREXTENDED"   # Hard gate: %100+ kullanım
        adr_score   = self._clamp(adr_score)
        details["adr"] = adr_res

        # ── 3. POC + SMC Confluence ───────────────────────────────
        poc_res   = poc_smc_confluence(
            df,
            bull_obs = ms.bull_obs,
            bear_obs = ms.bear_obs,
            bull_fvg = ms.bull_fvg,
            bear_fvg = ms.bear_fvg,
        )
        poc_score = float(poc_res.get("confluence_score", 0.0))
        poc_score = self._clamp(poc_score)
        details["poc"] = poc_res

        # ── 4. Open Interest ─────────────────────────────────────
        if oi_series and px_series and len(oi_series) >= 2:
            oi_res   = open_interest_signal(oi_series, px_series)
            oi_score = float(oi_res.get("oi_score", 0.0))
        else:
            oi_res   = {}
            oi_score = 0.0
        oi_score = self._clamp(oi_score)
        details["oi"] = oi_res

        # ── 5. Funding Rate ───────────────────────────────────────
        if funding_rate is not None:
            fr_res   = funding_rate_signal(funding_rate)
            fr_score = float(fr_res.get("fr_score", 0.0))
        else:
            fr_res   = {}
            fr_score = 0.0
        fr_score = self._clamp(fr_score)
        details["fr"] = fr_res

        # ── 6. Session Analizi ────────────────────────────────────
        sess_res     = session_analysis(df)
        sess_score   = float(sess_res.get("session_score", 0.0))
        sess_score   = self._clamp(sess_score)
        details["session"] = sess_res

        # ── 7. VWAP Bantları ──────────────────────────────────────
        vwap_res   = vwap_bands(df)
        vwap_score = float(vwap_res.get("vwap_score", 0.0))
        vwap_score = self._clamp(vwap_score)
        details["vwap"] = vwap_res

        # ── 8. Wyckoff Gelişmiş ───────────────────────────────────
        wyck_res    = wyckoff_advanced(df)
        wyck_score  = self._wyckoff_score(wyck_res, ms.trend)
        wyck_score  = self._clamp(wyck_score)
        details["wyckoff"] = wyck_res

        # ── ADR EXHAUSTED → ×0.75 cezası (hard gate değil ama skor kesiyor) ──
        if adr_signal == "EXHAUSTED":
            multiplier = 0.75
        else:
            multiplier = 1.0

        # ── Ağırlıklı ortalama (0-10 aralığı) ────────────────────
        # Önce ham skorları normalize et: -2..+2.5 → 0..1
        def _norm(v: float, lo: float = -2.5, hi: float = 2.5) -> float:
            return max(0.0, min(1.0, (v - lo) / (hi - lo)))

        weighted = (
            _norm(ib_score)    * _WEIGHT_IB    +
            _norm(adr_score)   * _WEIGHT_ADR   +
            _norm(poc_score)   * _WEIGHT_POC   +
            _norm(oi_score)    * _WEIGHT_OI    +
            _norm(fr_score)    * _WEIGHT_FR    +
            _norm(sess_score)  * _WEIGHT_SESSION +
            _norm(vwap_score)  * _WEIGHT_VWAP  +
            _norm(wyck_score)  * _WEIGHT_WYCKOFF
        )
        total = round(min(10.0, weighted * 10.0 * multiplier), 2)

        # ── Onay sayısı (pozitif katkı veren gösterge adedi) ─────
        confirmations = sum([
            ib_score    > 0.2,
            adr_score   > 0.0,
            poc_score   > 0.3,
            oi_score    > 0.2,
            fr_score    > 0.2,
            sess_score  > 0.5,
            vwap_score  > 0.2,
            wyck_score  > 0.5,
        ])

        return ConfluenceScore(
            ib_score      = ib_score,
            adr_score     = adr_score,
            poc_score     = poc_score,
            oi_score      = oi_score,
            fr_score      = fr_score,
            session_score = sess_score,
            vwap_score    = vwap_score,
            wyckoff_score = wyck_score,
            total         = total,
            confirmation_count = confirmations,
            adr_blocked   = adr_blocked,
            details       = details,
        )

    # ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _wyckoff_score(wyck_res: dict, trend: Trend) -> float:
        """Wyckoff sonucunu yön uyumlu skora çevirir."""
        spring = wyck_res.get("spring_detected", False)
        utad   = wyck_res.get("utad_detected",   False)

        if trend == Trend.BULLISH and spring:
            return 2.0
        if trend == Trend.BEARISH and utad:
            return 2.0
        if trend == Trend.BULLISH and utad:
            return -1.0   # Ters sinyal
        if trend == Trend.BEARISH and spring:
            return -1.0
        return 0.0

    # ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _clamp(value: float, lo: float = -3.0, hi: float = 3.0) -> float:
        """Skor değerini güvenli aralığa sıkıştırır."""
        try:
            v = float(value)
            return max(lo, min(hi, v)) if v == v else 0.0  # NaN koruması
        except (TypeError, ValueError):
            return 0.0
