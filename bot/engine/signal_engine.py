"""
bot/engine/signal_engine.py — Optimal Sinyal Motoru v3
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SignalEngine: Tüm katmanları orkestre eden ana sınıf.

Mimari:
  ┌─────────────────────────────────────────────────┐
  │  SignalEngine.analyze(symbol)                   │
  │                                                 │
  │  1. Veri çek         → MarketDataFetcher        │
  │  2. SMC/ICT analiz   → MarketStructureAnalyzer  │
  │  3. Hard gates       → TradeFilter (L1–L3)      │
  │  4. Confluence skor  → ConfluenceScorer         │
  │  5. Kalite kapısı    → TradeFilter (L4–L6)      │
  │  6. Nihai skor       → ağırlıklı kombinasyon    │
  │  7. Pozisyon boyutu  → PositionSizer            │
  │  8. SignalResult döner                          │
  └─────────────────────────────────────────────────┘

Tasarım kararları:
  • AI/LLM isteğe bağlı — ``use_llm=False`` (varsayılan) tam çalışır.
  • Her katman bağımsız hata yakalama yapar; tek hata sistemi
    durdurmaz, o katman atlanır.
  • Ağırlıklar backtest destekli: SMC %55, Confluence %45.
    (önceki keyfi 60/25/15 yerine kanıta dayalı)
  • Tüm skor kombinasyonu ``_combine_scores()`` içinde merkezileştirildi.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from bot.engine.base import (
    Action,
    ConfluenceScore,
    FilterResult,
    MarketStructure,
    SignalResult,
    Trend,
)
from bot.engine.confluence import ConfluenceScorer
from bot.engine.filters import TradeFilter
from bot.engine.market_structure import MarketStructureAnalyzer
from bot.engine.position_sizer import PositionSizer, SizingResult

logger = logging.getLogger("bot.engine.signal")

# ── Ağırlıklar ────────────────────────────────────────────────────────
_SMC_WEIGHT  = 0.55   # SMC/ICT — piyasa yapısı çekirdeği
_ADV_WEIGHT  = 0.45   # Confluence — destekleyici göstergeler
# NOT: LLM kullanılıyorsa ±1.5 boost öncekiyle aynı kalıyor

# ── Skor eşikleri ────────────────────────────────────────────────────
_MIN_FINAL_SCORE   = 5.5    # Bu altında → None döner
_STRONG_BUY_SCORE  = 7.5
_BUY_SCORE         = 5.5


class SignalEngine:
    """
    Kripto vadeli işlem sinyal motoru — v3 (optimal, OOP).

    Tüm alt bileşenler constructor'da bir kez oluşturulur; thread-safe değil
    ama tek thread kullanımında sorun yok.

    Args:
        min_score:         Sinyal üretmek için minimum birleşik skor.
        min_confirmations: Confluence'da minimum onay sayısı (hard gate).
        use_llm:           True → Ollama mevcutsa LLM boost uygula.
        atr_sl_mult:       SL mesafesi = ATR × bu çarpan.
        balance:           Mevcut bakiye (PositionSizer için).
        open_count:        Şu anki açık pozisyon sayısı.

    Example:
        >>> engine = SignalEngine(balance=500.0)
        >>> result = engine.analyze("ETH/USDT")
        >>> if result:
        ...     print(result.action, result.composite, result.entry_price)
    """

    def __init__(
        self,
        min_score:          float = _MIN_FINAL_SCORE,
        min_confirmations:  int   = 2,
        use_llm:            bool  = False,
        atr_sl_mult:        float = 1.5,
        balance:            float = 0.0,
        open_count:         int   = 0,
    ) -> None:
        self.min_score         = min_score
        self.use_llm           = use_llm
        self.balance           = balance
        self.open_count        = open_count

        # Alt bileşenler — her sembol için yeniden kullanılır
        self._structure  = None   # Lazy, sembol başına oluştur
        self._confluence = None
        self._filter     = TradeFilter(min_confirmations=min_confirmations)
        self._sizer      = PositionSizer()

    # ──────────────────────────────────────────────────────────────────
    def analyze(
        self,
        symbol:       str,
        social_data:  Optional[dict] = None,
        df_override:  Optional[pd.DataFrame] = None,
    ) -> Optional[SignalResult]:
        """
        Tek sembol için tam analiz pipeline'ını çalıştırır.

        Args:
            symbol:       "ETH/USDT" formatında işlem çifti.
            social_data:  Opsiyonel sosyal/duygu verisi dict'i.
            df_override:  Test için dış veri enjeksiyonu (yoksa Binance'ten çeker).

        Returns:
            SignalResult veya None (kalite eşiği geçilmediyse).
        """
        logger.debug(f"▶ {symbol} analiz başlıyor")

        # ── Adım 1: Veri ─────────────────────────────────────────
        df = df_override if df_override is not None else self._fetch(symbol)
        if df is None or df.empty or len(df) < 100:
            logger.debug(f"{symbol}: Veri yetersiz — atlandı")
            return None

        # ── Adım 2: SMC/ICT Piyasa Yapısı ────────────────────────
        structure_analyzer = MarketStructureAnalyzer(symbol)
        ms = structure_analyzer.analyze(df)

        if ms.trend == Trend.NEUTRAL:
            logger.debug(f"{symbol}: NEUTRAL trend — atlandı")
            return None

        # ── Adım 3: Erken hard gate (veri/trend/SL) ───────────────
        # Confluence henüz hesaplanmadı; sadece L1/L3/L5 kontrol edilir.
        early_filter = self._filter.evaluate_early(df, ms, funding_rate=None)
        if early_filter.blocked:
            logger.debug(f"{symbol}: Hard gate (erken) — {early_filter.reason}")
            return None

        # ── Adım 4: OI + Funding Rate çek ────────────────────────
        oi_list, px_list, funding = self._fetch_oi_funding(symbol, df)

        # ── Adım 5: Confluence skoru ──────────────────────────────
        confluence_scorer = ConfluenceScorer(symbol)
        cs = confluence_scorer.score(df, ms, oi_list, px_list, funding, symbol=symbol)

        # ── Adım 6a: Rejim hard gate ──────────────────────────────
        if cs.regime_blocked:
            regime_info = cs.details.get("regime", {})
            reason = regime_info.get("reason", "Uygunsuz piyasa rejimi")
            logger.debug(f"{symbol}: Rejim gate — {reason}")
            return None

        # ── Adım 6b: Tam hard gate değerlendirmesi ────────────────
        filter_result = self._filter.evaluate(df, ms, cs, funding)
        if filter_result.blocked:
            logger.debug(f"{symbol}: Hard gate — {filter_result.reason}")
            return None

        # ── Adım 7: Nihai skor hesabı ─────────────────────────────
        final_score = self._combine_scores(ms.composite_score, cs.total)

        # İsteğe bağlı LLM boost
        llm_boost = 0.0
        if self.use_llm:
            llm_boost = self._llm_boost(symbol, ms, cs, social_data)
            final_score = min(10.0, max(0.0, final_score + llm_boost))

        final_score = round(final_score, 2)

        if final_score < self.min_score:
            logger.debug(f"{symbol}: Skor düşük {final_score:.1f} < {self.min_score}")
            return None

        # ── Adım 8: Pozisyon boyutu ───────────────────────────────
        sizing = SizingResult()   # Varsayılan (balance yoksa)
        if self.balance > 0:
            sizing = self._sizer.calculate(
                balance      = self.balance,
                entry        = ms.entry_price,
                sl           = ms.sl_price,
                signal_score = final_score,
                open_count   = self.open_count,
            )
            if not sizing.valid:
                logger.debug(f"{symbol}: Sizing hatası — {sizing.reason}")
                # Boyutlama hatası sinyali ENGELLEMEZ — sadece boyut bilgisiz gelir

        # ── Adım 9: TP seviyeleri ─────────────────────────────────
        tp1, tp2, tp3 = self._tp_levels(ms.entry_price, ms.trend)
        if sizing.valid:
            tp1, tp2, tp3 = sizing.tp1_price, sizing.tp2_price, sizing.tp3_price

        # ── Adım 10: Action kararı ────────────────────────────────
        action = self._decide_action(final_score, ms.trend)

        # ── Sonuç paketi ──────────────────────────────────────────
        return SignalResult(
            symbol           = symbol,
            action           = action,
            direction        = "LONG" if ms.trend == Trend.BULLISH else "SHORT",
            composite        = final_score,
            smc_score        = ms.composite_score,
            adv_score        = cs.total,
            entry_price      = ms.entry_price,
            sl_price         = ms.sl_price,
            tp1_price        = tp1,
            tp2_price        = tp2,
            tp3_price        = tp3,
            confirmations    = cs.confirmation_count,
            filter_warnings  = filter_result.warnings,
            market_structure = ms,
            confluence       = cs,
            session          = cs.details.get("session", {}).get("current_session", "UNKNOWN"),
            funding_rate     = funding,
            timestamp        = datetime.now(timezone.utc).isoformat(),
        )

    # ──────────────────────────────────────────────────────────────────
    def scan_watchlist(
        self,
        symbols:    list[str],
        min_score:  Optional[float] = None,
    ) -> list[SignalResult]:
        """
        Sembol listesini tara, sinyal üretenlerini döner.

        Args:
            symbols:   Sembol listesi (["ETH/USDT", "BTC/USDT", ...]).
            min_score: Override minimum skor (yoksa self.min_score).

        Returns:
            Skora göre azalan sırada SignalResult listesi.
        """
        threshold = min_score or self.min_score
        results   = []

        for sym in symbols:
            try:
                result = self.analyze(sym)
                if result and result.composite >= threshold:
                    results.append(result)
            except Exception as exc:
                logger.warning(f"{sym} tarama hatası: {exc}")

        results.sort(key=lambda r: r.composite, reverse=True)
        logger.info(f"Tarama tamamlandı: {len(symbols)} sembol → {len(results)} sinyal")
        return results

    # ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _fetch(symbol: str) -> Optional[pd.DataFrame]:
        """Binance'ten 4H OHLCV verisi çeker."""
        try:
            from live_scan import ohlcv
            df = ohlcv(symbol, "4h", 400)
            return df if not df.empty else None
        except Exception as exc:
            logger.warning(f"{symbol} veri çekme hatası: {exc}")
            return None

    # ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _fetch_oi_funding(
        symbol: str,
        df: Optional[pd.DataFrame] = None,
    ) -> tuple[Optional[list], Optional[list], Optional[float]]:
        """
        OI geçmişi + Funding Rate çeker.

        Öncelik sırası:
          1. Binance Futures public endpoint (openInterestHist) — gerçek zaman serisi
          2. ccxt fallback (eski yöntem)

        OI serisine eşleşen kapanış fiyatları df'den timestamp hizalamasıyla alınır.
        """
        try:
            from market.data_fetcher import BinanceFetcher
            fetcher = BinanceFetcher()

            # ── Funding Rate ─────────────────────────────────────
            funding = fetcher.fetch_funding_rate(symbol)

            # ── OI Geçmişi (Binance public endpoint) ─────────────
            oi_values, _ = fetcher.fetch_oi_history(symbol, interval="4h", limit=20)

            if oi_values and len(oi_values) >= 2:
                # Eşleşen kapanış fiyatlarını df'den al
                if df is not None and not df.empty and len(df) >= len(oi_values):
                    px_list = df["close"].iloc[-len(oi_values):].tolist()
                else:
                    # df yoksa spot fiyatı kullan (yaklaşık)
                    try:
                        ticker = fetcher.exchange.fetch_ticker(symbol)
                        last_px = float(ticker.get("last", 0) or 0)
                        px_list = [last_px] * len(oi_values)
                    except Exception:
                        px_list = [1.0] * len(oi_values)

                return oi_values, px_list, funding

            # ── Fallback: ccxt / advanced_indicators ─────────────
            from bot.advanced_indicators import fetch_oi_and_funding
            oi_list, px_list, fr = fetch_oi_and_funding(symbol, limit=8)
            if fr is None:
                fr = funding
            return oi_list, px_list, fr

        except Exception as exc:
            logger.debug(f"{symbol} OI/FR çekme hatası: {exc}")
            return None, None, None

    # ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _combine_scores(smc: float, adv: float) -> float:
        """
        SMC ve Confluence skorlarını ağırlıklı ortalama ile birleştirir.

        Not: Önceki 60/25/15 şeması yerine 55/45 kullanılıyor.
        Cross-validation terimi kaldırıldı — gereksiz karmaşıklık.
        """
        return round(smc * _SMC_WEIGHT + adv * _ADV_WEIGHT, 4)

    # ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _decide_action(score: float, trend: Trend) -> Action:
        """Skor + trend yönünden Action enum döner."""
        if trend == Trend.BULLISH:
            if score >= _STRONG_BUY_SCORE:
                return Action.STRONG_BUY
            if score >= _BUY_SCORE:
                return Action.BUY
            return Action.HOLD
        elif trend == Trend.BEARISH:
            if score >= _STRONG_BUY_SCORE:
                return Action.STRONG_SELL
            if score >= _BUY_SCORE:
                return Action.SELL
            return Action.HOLD
        return Action.HOLD

    # ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _tp_levels(
        entry: float,
        trend: Trend,
    ) -> tuple[float, float, float]:
        """TP1/TP2/TP3 — PositionSizer mevcut değilken fallback."""
        from bot.engine.position_sizer import _TP1_PCT, _TP2_PCT, _TP3_PCT
        if trend == Trend.BULLISH:
            return (
                round(entry * (1 + _TP1_PCT), 8),
                round(entry * (1 + _TP2_PCT), 8),
                round(entry * (1 + _TP3_PCT), 8),
            )
        return (
            round(entry * (1 - _TP1_PCT), 8),
            round(entry * (1 - _TP2_PCT), 8),
            round(entry * (1 - _TP3_PCT), 8),
        )

    # ──────────────────────────────────────────────────────────────────
    def _llm_boost(
        self,
        symbol:      str,
        ms:          MarketStructure,
        cs:          ConfluenceScore,
        social_data: Optional[dict],
    ) -> float:
        """
        Opsiyonel LLM boost — Ollama mevcut değilse 0.0 döner.

        Maks etki: ±1.5 puan (toplam skorun ~%10-15'i).
        """
        try:
            from bot.signal_engine import analyze_full as _old_analyze  # eski layer3
            from agents.debate import TechnicalReport, SentimentData, run_debate

            tech = TechnicalReport(
                symbol          = symbol,
                composite_score = ms.composite_score,
                trend           = ms.trend.value,
                entry_price     = ms.entry_price,
                sl_price        = ms.sl_price,
                tp1_price       = self._tp_levels(ms.entry_price, ms.trend)[0],
                tp2_price       = self._tp_levels(ms.entry_price, ms.trend)[1],
                tp3_price       = self._tp_levels(ms.entry_price, ms.trend)[2],
                bos_bull        = ms.bos_bull,
                choch_bull      = ms.choch_bull,
                bos_bear        = ms.bos_bear,
                choch_bear      = ms.choch_bear,
                spring          = cs.details.get("wyckoff", {}).get("spring_detected", False),
                utad            = cs.details.get("wyckoff", {}).get("utad_detected",   False),
                ib_breakout     = cs.details.get("ib",  {}).get("ib_breakout",  "NONE"),
                adr_signal      = cs.details.get("adr", {}).get("adr_signal",   "NEUTRAL"),
                adr_pct_used    = cs.details.get("adr", {}).get("adr_pct_used", 0),
                poc_confluence  = cs.details.get("poc", {}).get("confluence_type", "NEUTRAL"),
                oi_trend        = cs.details.get("oi",  {}).get("oi_trend",      "UNKNOWN"),
                fr_signal       = cs.details.get("fr",  {}).get("fr_signal",     "NEUTRAL"),
                vwap_position   = cs.details.get("vwap", {}).get("band_position", "UNKNOWN"),
                wyckoff_phase   = cs.details.get("wyckoff", {}).get("wyckoff_phase", "NEUTRAL"),
                session         = cs.details.get("session", {}).get("current_session", "UNKNOWN"),
                advanced_score  = cs.total,
            )

            sent = SentimentData(
                symbol        = symbol,
                score         = social_data.get("score", 0.5) if social_data else 0.5,
                label         = social_data.get("label", "NÖTR") if social_data else "NÖTR",
                mention_count = social_data.get("mention_count", 0) if social_data else 0,
                headlines     = social_data.get("headlines", []) if social_data else [],
            )

            debate = run_debate(tech, sent, max_rounds=1, use_llm=True)

            if debate:
                action = debate.action
                if action == "STRONG_BUY"  and ms.trend == Trend.BULLISH:  return 1.5
                if action == "BUY"         and ms.trend == Trend.BULLISH:  return 0.5
                if action == "STRONG_SELL" and ms.trend == Trend.BULLISH:  return -1.5
                if action == "STRONG_SELL" and ms.trend == Trend.BEARISH:  return 1.5
                if action == "SELL"        and ms.trend == Trend.BEARISH:  return 0.5
                if action == "STRONG_BUY"  and ms.trend == Trend.BEARISH:  return -1.5

        except Exception as exc:
            logger.debug(f"{symbol} LLM boost hatası (atlandı): {exc}")

        return 0.0
