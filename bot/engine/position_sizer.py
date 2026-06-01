"""
bot/engine/position_sizer.py — Kelly + ATR Tabanlı Pozisyon Boyutlayıcı
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sabit %2 risk kuralını Kelly Criterion ile iyileştirir:
  • Skor yüksekse → Kelly'den alınan pozisyon risk_pct'yi artırabilir.
  • Skor düşükse  → risk_pct küçülür.
  • Açık pozisyon sayısı arttıkça risk azalır (portföy korelasyon koruma).

TP seviyeleri kısmi pozisyon kapatma şemasına göre hesaplanır:
  TP1 → %40 kapat,  TP2 → %35 kapat,  TP3 → kalan %25.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

logger = logging.getLogger("bot.engine.sizer")

# ── Varsayılan Parametreler ───────────────────────────────────────────
_BASE_RISK_PCT   = 0.020   # Baz risk: %2
_KELLY_FRACTION  = 0.25    # Kelly'nin %25'ini al (tam Kelly çok agresif)
_MAX_RISK_PCT    = 0.030   # Maks risk: %3 (yüksek skor dahil)
_MIN_RISK_PCT    = 0.010   # Min risk: %1 (düşük skor / çok açık poz)
_MAX_LEVERAGE    = 5       # Mutlak kaldıraç tavanı
_MIN_NOTIONAL    = 10.0    # Binance minimum notional (USDT)
_TP1_PCT         = 0.060   # TP1: +%6 / -%6
_TP2_PCT         = 0.140   # TP2: +%14 / -%14
_TP3_PCT         = 0.280   # TP3: +%28 / -%28
_TP1_CLOSE_FRAC  = 0.40    # TP1'de kapat oranı
_TP2_CLOSE_FRAC  = 0.35
_TP3_CLOSE_FRAC  = 0.25


@dataclass
class SizingResult:
    """
    Pozisyon boyutlama çıktısı.

    Attributes:
        valid:       Hesaplama geçerli mi?
        reason:      Geçersizse neden.
        direction:   "LONG" veya "SHORT".
        risk_usdt:   Riske giren USDT miktarı.
        sl_pct:      SL mesafesi yüzdesi.
        leverage:    Kullanılacak kaldıraç.
        notional:    Toplam pozisyon büyüklüğü (USDT).
        quantity:    Coin miktarı.
        tp1_price:   Birinci kâr hedefi.
        tp2_price:   İkinci kâr hedefi.
        tp3_price:   Üçüncü kâr hedefi.
        tp1_qty:     TP1'de kapatılacak miktar.
        tp2_qty:     TP2'de kapatılacak miktar.
        tp3_qty:     TP3'te kapatılacak miktar.
        est_win_rate: Skor bazlı tahmini kazanma oranı.
        kelly_f:     Hesaplanan Kelly kesri.
        expected_value: Tahmini beklenen değer (R cinsinden).
    """

    valid:         bool   = False
    reason:        str    = ""
    direction:     str    = "LONG"
    risk_usdt:     float  = 0.0
    sl_pct:        float  = 0.0
    leverage:      int    = 1
    notional:      float  = 0.0
    quantity:      float  = 0.0
    tp1_price:     float  = 0.0
    tp2_price:     float  = 0.0
    tp3_price:     float  = 0.0
    tp1_qty:       float  = 0.0
    tp2_qty:       float  = 0.0
    tp3_qty:       float  = 0.0
    est_win_rate:  float  = 0.0
    kelly_f:       float  = 0.0
    expected_value: float = 0.0


class PositionSizer:
    """
    Kelly Criterion + sabit %2 risk tabanlı pozisyon boyutlayıcı.

    Args:
        base_risk_pct:  İşlem başına baz risk yüzdesi.
        max_positions:  Aynı anda izin verilen maksimum açık pozisyon.
        kelly_fraction: Kelly çarpanı (1.0 = tam Kelly, 0.25 önerilir).

    Example:
        >>> sizer = PositionSizer()
        >>> result = sizer.calculate(
        ...     balance=500.0, entry=3000.0, sl=2850.0,
        ...     signal_score=7.5, open_count=1
        ... )
        >>> if result.valid:
        ...     print(f"{result.direction} x{result.leverage} qty={result.quantity:.4f}")
    """

    def __init__(
        self,
        base_risk_pct:  float = _BASE_RISK_PCT,
        max_positions:  int   = 4,
        kelly_fraction: float = _KELLY_FRACTION,
    ) -> None:
        self.base_risk_pct  = base_risk_pct
        self.max_positions  = max_positions
        self.kelly_fraction = kelly_fraction

    # ──────────────────────────────────────────────────────────────────
    def calculate(
        self,
        balance:      float,
        entry:        float,
        sl:           float,
        signal_score: float,
        open_count:   int = 0,
    ) -> SizingResult:
        """
        Pozisyon boyutunu hesaplar.

        Args:
            balance:      Mevcut USDT bakiyesi.
            entry:        Giriş fiyatı.
            sl:           Stop-loss fiyatı.
            signal_score: Birleşik sinyal skoru (0-10).
            open_count:   Şu anda açık pozisyon sayısı.

        Returns:
            SizingResult — ``valid=False`` ise işlem açma.
        """
        # ── Temel geçerlilik ──────────────────────────────────────
        if balance <= 0:
            return SizingResult(reason="Geçersiz bakiye")
        if entry <= 0 or sl <= 0:
            return SizingResult(reason="Geçersiz fiyat")
        if open_count >= self.max_positions:
            return SizingResult(
                reason=f"Max {self.max_positions} pozisyon sınırı"
            )

        direction = "LONG" if entry > sl else "SHORT"
        sl_dist   = abs(entry - sl) / entry

        # ── SL mesafesi sınırları ─────────────────────────────────
        if sl_dist < 0.005:
            return SizingResult(reason=f"SL çok yakın: {sl_dist:.2%}")
        if sl_dist > 0.08:
            return SizingResult(reason=f"SL çok uzak: {sl_dist:.2%}")

        # ── Kelly Criterion ───────────────────────────────────────
        est_wr    = self._estimate_win_rate(signal_score)
        blended_rr = (
            _TP1_CLOSE_FRAC * (_TP1_PCT / sl_dist) +
            _TP2_CLOSE_FRAC * (_TP2_PCT / sl_dist)
        )
        kelly_full = est_wr - (1 - est_wr) / blended_rr
        kelly_f    = max(0.0, kelly_full * self.kelly_fraction)

        # Expected value kontrolü
        ev = est_wr * blended_rr - (1 - est_wr)
        if ev < -0.05:
            return SizingResult(
                reason=f"Negatif beklenen değer: EV={ev:.2f}",
                est_win_rate=est_wr,
                kelly_f=kelly_f,
                expected_value=ev,
            )

        # ── Dinamik risk yüzdesi ──────────────────────────────────
        # Açık pozisyon başına risk hafifçe azalır
        position_penalty = open_count * 0.002
        kelly_boost      = kelly_f * self.base_risk_pct

        risk_pct = self.base_risk_pct + kelly_boost - position_penalty
        risk_pct = max(_MIN_RISK_PCT, min(_MAX_RISK_PCT, risk_pct))

        risk_usdt = balance * risk_pct

        # ── Kaldıraç ve V21 GERÇEKLİK KONTROLÜ (LİKİDİTE DUVARI) ──
        notional_needed = risk_usdt / sl_dist
        leverage        = math.ceil(notional_needed / balance)
        leverage        = max(1, min(leverage, _MAX_LEVERAGE))
        leverage        = min(leverage, self._max_leverage_by_score(signal_score))

        notional = balance * leverage
        
        # Binance $50,000 limitini uygula
        _MAX_POS_USD = 50000.0
        if notional > _MAX_POS_USD:
            notional = _MAX_POS_USD
            leverage = math.ceil(notional / balance) if balance > 0 else 1
            risk_usdt = notional * sl_dist

        if notional < _MIN_NOTIONAL:
            return SizingResult(
                reason  = f"Bakiye çok düşük: ${notional:.2f} < ${_MIN_NOTIONAL} minimum",
                est_win_rate=est_wr,
            )

        quantity = notional / entry

        # ── TP seviyeleri ─────────────────────────────────────────
        tp1, tp2, tp3 = self._tp_levels(entry, direction)

        return SizingResult(
            valid         = True,
            reason        = "OK",
            direction     = direction,
            risk_usdt     = round(risk_usdt, 4),
            sl_pct        = round(sl_dist * 100, 3),
            leverage      = leverage,
            notional      = round(notional, 4),
            quantity      = round(quantity, 6),
            tp1_price     = tp1,
            tp2_price     = tp2,
            tp3_price     = tp3,
            tp1_qty       = round(quantity * _TP1_CLOSE_FRAC, 6),
            tp2_qty       = round(quantity * _TP2_CLOSE_FRAC, 6),
            tp3_qty       = round(quantity * _TP3_CLOSE_FRAC, 6),
            est_win_rate  = est_wr,
            kelly_f       = round(kelly_f, 4),
            expected_value = round(ev, 4),
        )

    # ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _estimate_win_rate(score: float) -> float:
        """
        Skor-WR lineer interpolasyon.
        Skor=4 → WR≈45%, Skor=10 → WR≈68%
        Empirik — backtest verisiyle kalibre edilmeli.
        """
        wr = 0.45 + (max(4.0, min(10.0, score)) - 4.0) / 6.0 * 0.23
        return round(wr, 4)

    @staticmethod
    def _max_leverage_by_score(score: float) -> int:
        """Skor tabanlı dinamik kaldıraç tavanı."""
        if score >= 8.0:
            return 5
        if score >= 6.5:
            return 4
        if score >= 5.5:
            return 3
        return 2

    @staticmethod
    def _tp_levels(
        entry:     float,
        direction: str,
    ) -> tuple[float, float, float]:
        """TP1 / TP2 / TP3 fiyat seviyelerini hesaplar."""
        if direction == "LONG":
            tp1 = round(entry * (1 + _TP1_PCT), 8)
            tp2 = round(entry * (1 + _TP2_PCT), 8)
            tp3 = round(entry * (1 + _TP3_PCT), 8)
        else:
            tp1 = round(entry * (1 - _TP1_PCT), 8)
            tp2 = round(entry * (1 - _TP2_PCT), 8)
            tp3 = round(entry * (1 - _TP3_PCT), 8)
        return tp1, tp2, tp3
