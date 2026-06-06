"""
bot/engine/market_structure.py — SMC/ICT Piyasa Yapısı Analizörü
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
live_scan.py'nin SMC fonksiyonlarını OOP sarmalayıcı ile sarar.

Sorumluluklar:
  • BOS / CHoCH / MSS tespiti
  • Order Block + Breaker Block haritası
  • Fair Value Gap (FVG + Volume Imbalance)
  • Liquidity Map (BSL/SSL, sweep tespiti)
  • OTE (Optimal Trade Entry, Fibonacci 0.62-0.79)
  • Composite SMC skoru (0-10)
  • ATR tabanlı SL/TP hesabı
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from bot.engine.base import BaseAnalyzer, MarketStructure, Trend

logger = logging.getLogger("bot.engine.structure")

# ── Ağırlıklar (deneyimle kalibre edilmiş) ───────────────────────────
_W_BOS        = 2.0   # Trend kırılması — en güçlü sinyal
_W_CHOCH      = 1.5   # Karakter değişimi
_W_OB_NEAR    = 2.0   # Yakın order block (son 20 mum)
_W_OB_FAR     = 1.0   # Uzak order block
_W_FVG        = 1.5   # Doldurulmamış FVG
_W_SWEEP      = 1.0   # Likidite süpürmesi → reversal fırsatı
_W_OTE        = 0.5   # OTE bölgesi
_W_BREAKER    = 1.0   # Breaker block


class MarketStructureAnalyzer(BaseAnalyzer):
    """
    SMC/ICT tabanlı piyasa yapısı analizörü.

    live_scan.py fonksiyonlarını sararak OOP arayüzü sağlar.
    Tüm hesaplamalar yalnızca geçmiş veriye bakar (anti-repainting).

    Args:
        symbol: İşlem çifti ("ETH/USDT").
        atr_sl_mult: ATR çarpanı — SL mesafesi = ATR × çarpan.

    Example:
        >>> analyzer = MarketStructureAnalyzer("ETH/USDT")
        >>> ms = analyzer.analyze(df_4h)
        >>> print(ms.trend, ms.composite_score)
    """

    def __init__(self, symbol: str, atr_sl_mult: float = 1.5) -> None:
        super().__init__(symbol)
        self.atr_sl_mult = atr_sl_mult

    # ──────────────────────────────────────────────────────────────────
    def analyze(self, df: pd.DataFrame) -> MarketStructure:
        """
        4H OHLCV verisini analiz eder, MarketStructure döner.

        Args:
            df: DatetimeIndex'li OHLCV DataFrame, min 100 satır.

        Returns:
            Tam doldurulmuş MarketStructure nesnesi.
            Yetersiz veri durumunda varsayılan (NEUTRAL) döner.
        """
        if df.empty or len(df) < 100:
            logger.debug(f"{self.symbol}: Yetersiz veri ({len(df)} satır)")
            return MarketStructure()

        try:
            return self._run_analysis(df)
        except Exception as exc:
            logger.warning(f"{self.symbol} SMC analiz hatası: {exc}", exc_info=True)
            return MarketStructure()

    # ──────────────────────────────────────────────────────────────────
    def _run_analysis(self, df: pd.DataFrame) -> MarketStructure:
        """İç analiz mantığı — tüm SMC katmanlarını çalıştırır."""
        # live_scan'dan fonksiyonları içe aktar (lazy import — hız ve çevrim koruması)
        from live_scan import (
            market_structure as smc_market_structure,
            order_blocks,
            fair_value_gaps,
            liquidity_map,
            optimal_trade_entry,
            atr_fn,
        )

        # ── 1. Piyasa yapısı (trend, BOS, CHoCH, MSS) ────────────
        ms_raw     = smc_market_structure(df)
        trend_str  = ms_raw.get("trend", "NEUTRAL")
        trend      = Trend(trend_str) if trend_str in Trend._value2member_map_ else Trend.NEUTRAL

        # ── 2. Order Blocks ───────────────────────────────────────
        bull_obs, bear_obs, bull_brk, bear_brk = order_blocks(df)

        # ── 3. Fair Value Gaps ────────────────────────────────────
        bull_fvg, bear_fvg = fair_value_gaps(df)

        # ── 4. Liquidity Map ──────────────────────────────────────
        _, _, sweep_up, sweep_dn = liquidity_map(df)

        # ── 5. OTE ───────────────────────────────────────────────
        ote = optimal_trade_entry(df)

        # ── 6. ATR + SL ──────────────────────────────────────────
        atr_series = atr_fn(df, 14)
        atr_val    = float(atr_series.iloc[-2]) if len(atr_series) >= 2 else 0.0
        entry      = float(df["close"].iloc[-2])  # Kapanmış son mum (repainting yok)
        sl_price   = self._calc_sl(entry, atr_val, trend)

        # ── 7. Composite SMC skoru ────────────────────────────────
        score = self._score(
            trend       = trend,
            ms_raw      = ms_raw,
            bull_obs    = bull_obs,
            bear_obs    = bear_obs,
            bull_fvg    = bull_fvg,
            bear_fvg    = bear_fvg,
            bull_brk    = bull_brk,
            bear_brk    = bear_brk,
            sweep_up    = sweep_up,
            sweep_dn    = sweep_dn,
            ote         = ote,
        )

        return MarketStructure(
            trend           = trend,
            bos_bull        = ms_raw.get("bos_bull", False),
            bos_bear        = ms_raw.get("bos_bear", False),
            choch_bull      = ms_raw.get("choch_bull", False),
            choch_bear      = ms_raw.get("choch_bear", False),
            bull_obs        = bull_obs,
            bear_obs        = bear_obs,
            bull_fvg        = bull_fvg,
            bear_fvg        = bear_fvg,
            ote             = ote,
            liq_sweep_up    = sweep_up,
            liq_sweep_dn    = sweep_dn,
            composite_score = score,
            entry_price     = entry,
            sl_price        = sl_price,
        )

    # ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _calc_sl(
        entry: float,
        atr:   float,
        trend: Trend,
    ) -> float:
        """ATR tabanlı SL hesabı. Geçersiz girişlerde entry döner."""
        if atr <= 0 or entry <= 0:
            return entry
        if trend == Trend.BULLISH:
            return round(entry - atr * 1.5, 8)
        elif trend == Trend.BEARISH:
            return round(entry + atr * 1.5, 8)
        return entry

    # ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _score(
        trend:    Trend,
        ms_raw:   dict,
        bull_obs: list,
        bear_obs: list,
        bull_fvg: list,
        bear_fvg: list,
        bull_brk: list,
        bear_brk: list,
        sweep_up: bool,
        sweep_dn: bool,
        ote:      Optional[dict],
    ) -> float:
        """
        Ağırlıklı SMC skoru hesaplar, 0-10 aralığına normalize eder.

        Yalnızca trend yönünü destekleyen sinyaller sayılır.
        Karşı yönden zayıflatma uygulanır.
        """
        raw = 0.0
        is_bull = trend == Trend.BULLISH
        is_bear = trend == Trend.BEARISH

        if trend == Trend.NEUTRAL:
            return 0.0

        # BOS / CHoCH
        if is_bull and ms_raw.get("bos_bull"):
            raw += _W_BOS
        if is_bear and ms_raw.get("bos_bear"):
            raw += _W_BOS
        if is_bull and ms_raw.get("choch_bull"):
            raw += _W_CHOCH
        if is_bear and ms_raw.get("choch_bear"):
            raw += _W_CHOCH

        # Order Blocks (yön uyumlu)
        active_obs = bull_obs if is_bull else bear_obs
        for i, ob in enumerate(active_obs[:3]):
            w = _W_OB_NEAR if ob.get("bars_ago", 99) <= 20 else _W_OB_FAR
            raw += w * (0.8 ** i)  # Her sonraki OB biraz daha az ağırlık

        # Breaker Blocks (yön uyumlu karşı yön)
        active_brk = bull_brk if is_bull else bear_brk
        raw += len(active_brk[:2]) * _W_BREAKER

        # FVG
        active_fvg = bull_fvg if is_bull else bear_fvg
        for i, fvg in enumerate(active_fvg[:3]):
            raw += _W_FVG * (0.7 ** i)

        # Likidite Süpürmesi (karşı yön süpürmesi = bizim yönde güç)
        if is_bull and sweep_dn:   # SSL süpürmesi → bullish reversal
            raw += _W_SWEEP
        if is_bear and sweep_up:   # BSL süpürmesi → bearish reversal
            raw += _W_SWEEP

        # OTE
        if ote:
            if is_bull and ote.get("bull_ote"):
                raw += _W_OTE
            if is_bear and ote.get("bear_ote"):
                raw += _W_OTE

        # Karşı yön cezası: karşı sinyaller skoru düşürür
        counter_obs = bear_obs if is_bull else bull_obs
        counter_fvg = bear_fvg if is_bull else bull_fvg
        counter_penalty = (
            min(len(counter_obs), 2) * 0.3 +
            min(len(counter_fvg), 2) * 0.2
        )
        raw = max(0.0, raw - counter_penalty)

        # Maksimum teorik skor ≈ 12 → 0-10 normalize
        normalized = min(10.0, round(raw / 12.0 * 10.0, 2))
        return normalized
