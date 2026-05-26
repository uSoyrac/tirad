"""
bot/engine/filters.py — Sert Kalite Kapıları (Hard Gates)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Katmanlı filtre sistemi: her kural bir işlemi tamamen engelleyebilir
veya uyarı listesine ekleyebilir. Hiçbir filtre skoru yumuşatmaz —
ya geç (block) ya da pas geç.

Katmanlar (sırayla değerlendirilir):
  L1 — Veri kalitesi: yeterli mum, fiyat geçerliliği
  L2 — ADR tükenme: günlük aralık %100+ kullanılmış
  L3 — Funding aşırılık: yönün tersi extreme funding
  L4 — Minimum confluence: gösterge onay sayısı yetersiz
  L5 — SL geçerliliği: SL mesafesi makul aralıkta
  L6 — Seans saati: Asia-only saatler düşük öncelik (uyarı)

Tasarım notu:
  Filtreler tek geçişte değerlendirilir; ilk engel bulunduğunda
  erken çıkış yapılır. Performans kritik değil — açıklık önceliklidir.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from bot.engine.base import (
    ConfluenceScore,
    FilterResult,
    MarketStructure,
    Trend,
)

logger = logging.getLogger("bot.engine.filters")

# ── Konfigürasyon sabitleri ───────────────────────────────────────────
_MIN_ROWS          = 100       # DataFrame minimum satır sayısı
_MAX_SL_PCT        = 0.08      # SL mesafesi max %8
_MIN_SL_PCT        = 0.005     # SL mesafesi min %0.5
_MIN_CONFIRMATIONS = 2         # Minimum onay sayısı (hard gate)
_FR_EXTREME_LONG   = 0.0008    # Funding Rate: aşırı long eşiği
_FR_EXTREME_SHORT  = -0.0005   # Funding Rate: aşırı short eşiği


class TradeFilter:
    """
    Katmanlı sert filtre değerlendirici.

    Hiçbir durum bağımlılığı yoktur — tüm metodlar saf fonksiyondur.
    Her çağrı yeni bir FilterResult nesnesi döner.

    Args:
        min_confirmations: Confluence onay eşiği (L4 filtresi).
        check_session:     True → Asya saatlerini uyarıya ekle.

    Example:
        >>> tf = TradeFilter(min_confirmations=3)
        >>> result = tf.evaluate(df, ms, cs, funding_rate=0.0002)
        >>> if result.blocked:
        ...     logger.info(f"Engellendi: {result.reason}")
    """

    def __init__(
        self,
        min_confirmations: int  = _MIN_CONFIRMATIONS,
        check_session:     bool = True,
    ) -> None:
        self.min_confirmations = min_confirmations
        self.check_session     = check_session

    # ──────────────────────────────────────────────────────────────────
    def evaluate_early(
        self,
        df:           pd.DataFrame,
        ms:           MarketStructure,
        funding_rate: float | None = None,
    ) -> FilterResult:
        """
        Confluence hesaplanmadan önce uygulanan erken filtreler (L1, L3, L5).

        L2 (ADR), L4 (confluence onayı) ve L6 (seans) bu aşamada uygulanmaz;
        bunlar için ``evaluate()`` kullanın.

        Args:
            df:           4H OHLCV verisi.
            ms:           MarketStructure sonucu.
            funding_rate: Güncel funding rate (opsiyonel).

        Returns:
            FilterResult — ``blocked=True`` ise analiz sonlandırılmalıdır.
        """
        # L1
        block, reason = self._check_data_quality(df, ms)
        if block:
            return FilterResult(blocked=True, reason=reason)

        # L3 — Funding Rate (önceden biliniyorsa)
        block, reason = self._check_funding(ms.trend, funding_rate)
        if block:
            return FilterResult(blocked=True, reason=reason)

        # L5 — SL geçerliliği
        block, reason = self._check_sl(ms.entry_price, ms.sl_price)
        if block:
            return FilterResult(blocked=True, reason=reason)

        return FilterResult(blocked=False, reason="OK")

    # ──────────────────────────────────────────────────────────────────
    def evaluate(
        self,
        df:           pd.DataFrame,
        ms:           MarketStructure,
        cs:           ConfluenceScore,
        funding_rate: float | None = None,
    ) -> FilterResult:
        """
        Confluence hesaplandıktan sonra tüm katman filtrelerini değerlendirir.

        Args:
            df:           4H OHLCV verisi.
            ms:           MarketStructure sonucu.
            cs:           ConfluenceScore sonucu.
            funding_rate: Güncel funding rate (opsiyonel).

        Returns:
            FilterResult — ``blocked=True`` ise işlem açılmaz.
        """
        warnings: list[str] = []

        # ── L1: Veri kalitesi ─────────────────────────────────────
        block, reason = self._check_data_quality(df, ms)
        if block:
            return FilterResult(blocked=True, reason=reason)

        # ── L2: ADR tükenme ───────────────────────────────────────
        if cs.adr_blocked:
            return FilterResult(
                blocked = True,
                reason  = "ADR: Günlük aralık %100+ kullanılmış — tükenme riski",
            )

        # ── L3: Funding Rate aşırılığı ────────────────────────────
        block, reason = self._check_funding(ms.trend, funding_rate)
        if block:
            return FilterResult(blocked=True, reason=reason)

        # ── L4: Minimum confluence onayı ─────────────────────────
        if cs.confirmation_count < self.min_confirmations:
            return FilterResult(
                blocked = True,
                reason  = (
                    f"Confluence yetersiz: {cs.confirmation_count} onay "
                    f"(minimum {self.min_confirmations} gerekli)"
                ),
            )

        # ── L5: SL geçerliliği ────────────────────────────────────
        block, reason = self._check_sl(ms.entry_price, ms.sl_price)
        if block:
            return FilterResult(blocked=True, reason=reason)

        # ── L6: Seans saati (sadece uyarı) ───────────────────────
        if self.check_session:
            sess_warning = self._check_session(cs)
            if sess_warning:
                warnings.append(sess_warning)

        # ADR EXHAUSTED uyarısı (hard gate değil, önlem ver)
        adr_signal = cs.details.get("adr", {}).get("adr_signal", "")
        if adr_signal == "EXHAUSTED":
            warnings.append("ADR: Günlük aralık %80+ kullanılmış — risk azalt")

        return FilterResult(blocked=False, reason="OK", warnings=warnings)

    # ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _check_data_quality(
        df: pd.DataFrame,
        ms: MarketStructure,
    ) -> tuple[bool, str]:
        """L1: Veri kalitesi kontrolü."""
        if df.empty or len(df) < _MIN_ROWS:
            return True, f"Yetersiz veri: {len(df)} satır (min {_MIN_ROWS})"

        if ms.entry_price <= 0:
            return True, "Geçersiz giriş fiyatı"

        if ms.trend == Trend.NEUTRAL:
            return True, "Nötr trend — yön belirsiz"

        return False, ""

    # ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _check_funding(
        trend:        Trend,
        funding_rate: float | None,
    ) -> tuple[bool, str]:
        """
        L3: Funding rate aşırılık kontrolü.

        Aşırı pozitif funding (>0.08%) → longlar aşırı kalabalık → LONG bloğu.
        Aşırı negatif funding (<-0.05%) → shortlar aşırı kalabalık → SHORT bloğu.
        """
        if funding_rate is None:
            return False, ""

        if trend == Trend.BULLISH and funding_rate >= _FR_EXTREME_LONG:
            return (
                True,
                f"Funding Rate aşırı pozitif: {funding_rate:.4%} "
                f"— longlar kalabalık, LONG engellendi",
            )

        if trend == Trend.BEARISH and funding_rate <= _FR_EXTREME_SHORT:
            return (
                True,
                f"Funding Rate aşırı negatif: {funding_rate:.4%} "
                f"— shortlar kalabalık, SHORT engellendi",
            )

        return False, ""

    # ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _check_sl(entry: float, sl: float) -> tuple[bool, str]:
        """L5: SL mesafesi geçerliliği."""
        if sl <= 0 or entry <= 0:
            return True, "Geçersiz SL/entry fiyatı"

        sl_pct = abs(entry - sl) / entry

        if sl_pct < _MIN_SL_PCT:
            return True, f"SL çok yakın: {sl_pct:.2%} (min {_MIN_SL_PCT:.2%})"

        if sl_pct > _MAX_SL_PCT:
            return True, f"SL çok uzak: {sl_pct:.2%} (max {_MAX_SL_PCT:.2%})"

        return False, ""

    # ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _check_session(cs: ConfluenceScore) -> str | None:
        """L6: Düşük kaliteli seans uyarısı (blok değil)."""
        session = cs.details.get("session", {}).get("current_session", "")
        in_kz   = cs.details.get("session", {}).get("in_kill_zone", False)

        if session == "ASIA" and not in_kz:
            return "Asya seansı — likidite düşük, pozisyon boyutunu küçült"

        if session == "OFF_HOURS":
            return "Seans dışı saat — spread geniş olabilir"

        return None
