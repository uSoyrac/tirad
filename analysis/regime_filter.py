"""
analysis/regime_filter.py — Piyasa Rejimi Tespiti
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ADX + Realized Volatility kullanarak piyasanın durumunu tespit eder:

  TRENDING   → ADX ≥ 25, volatilite normal: sinyal al
  RANGING    → ADX < 20: sinyal alma, whipsaw riski yüksek
  VOLATILE   → ATR anormal yüksek: stop'lar vurulur, sinyal alma
  TRANSITION → Geçiş, ihtiyatlı ol

Neden standart botlardan üstün:
  Çoğu bot her koşulda işlem açar. Gerçek edge büyük ölçüde
  KÖTÜ koşullarda işlem AÇMAMAKTAN gelir.
"""

from __future__ import annotations

import logging
from typing import Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("analysis.regime")


def _rma(series: pd.Series, period: int) -> pd.Series:
    """Wilder's Smoothed Moving Average (ADX ve ATR için standart)."""
    return series.ewm(alpha=1.0 / period, adjust=False).mean()


def compute_adx(df: pd.DataFrame, period: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    ADX, +DI, -DI hesaplar.
    Returns: (adx, di_plus, di_minus) — hepsi 0-100 arası
    """
    high  = df["high"]
    low   = df["low"]
    close = df["close"]

    prev_high  = high.shift(1)
    prev_low   = low.shift(1)
    prev_close = close.shift(1)

    # True Range
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)

    # Directional Movement
    up_move   = high - prev_high
    down_move = prev_low - low

    plus_dm  = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    atr14    = _rma(tr, period)
    plus_di  = 100.0 * _rma(plus_dm, period)  / atr14.replace(0, np.nan)
    minus_di = 100.0 * _rma(minus_dm, period) / atr14.replace(0, np.nan)

    dx  = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = _rma(dx.fillna(0), period)

    return adx.fillna(0), plus_di.fillna(0), minus_di.fillna(0)


def detect_regime(df: pd.DataFrame, adx_period: int = 14) -> dict:
    """
    Piyasa rejimini tespit eder.

    Args:
        df:         OHLCV DataFrame (en az 60 bar gerekli)
        adx_period: ADX hesap periyodu (varsayılan 14)

    Returns:
        regime:           "TRENDING" | "RANGING" | "VOLATILE" | "TRANSITION" | "UNKNOWN"
        adx:              float 0-100
        di_plus:          float 0-100
        di_minus:         float 0-100
        atr_pct:          ATR'nin fiyata oranı (%)
        vol_regime:       "LOW" | "NORMAL" | "HIGH" | "EXTREME"
        vol_ratio:        Kısa/uzun ATR oranı (1.0 = normal)
        trend_direction:  "BULLISH" | "BEARISH"
        should_trade:     bool — False ise sinyal açma
        regime_score:     float -2..+2 (confluence için)
        reason:           str açıklama
    """
    if df.empty or len(df) < adx_period * 4:
        return {
            "regime": "UNKNOWN", "adx": 0.0, "di_plus": 0.0, "di_minus": 0.0,
            "atr_pct": 0.0, "vol_regime": "NORMAL", "vol_ratio": 1.0,
            "trend_direction": "NEUTRAL", "should_trade": True,
            "regime_score": 0.0, "reason": "Yetersiz veri",
        }

    adx_s, di_plus_s, di_minus_s = compute_adx(df, adx_period)

    adx      = float(adx_s.iloc[-1])
    di_plus  = float(di_plus_s.iloc[-1])
    di_minus = float(di_minus_s.iloc[-1])

    # ATR volatilite rejimi
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr14     = float(_rma(tr, 14).iloc[-1])
    atr50_val = float(tr.rolling(50).mean().iloc[-1]) if len(df) >= 50 else atr14
    atr_pct   = (atr14 / float(close.iloc[-1])) * 100.0 if float(close.iloc[-1]) > 0 else 0.0
    vol_ratio = atr14 / (atr50_val + 1e-10)

    if vol_ratio >= 2.5:
        vol_regime = "EXTREME"
    elif vol_ratio >= 1.6:
        vol_regime = "HIGH"
    elif vol_ratio >= 0.75:
        vol_regime = "NORMAL"
    else:
        vol_regime = "LOW"

    # Trend yönü (+DI vs -DI)
    trend_direction = "BULLISH" if di_plus > di_minus else "BEARISH"

    # ── Rejim sınıflandırması ───────────────────────────────────────
    if vol_regime == "EXTREME":
        regime      = "VOLATILE"
        should_trade = False
        reason      = f"Aşırı volatilite (ATR x{vol_ratio:.1f} normal üstü)"
        score       = -2.0

    elif adx >= 30 and vol_regime in ("NORMAL", "HIGH"):
        regime      = "TRENDING"
        should_trade = True
        reason      = f"Güçlü trend (ADX={adx:.1f})"
        score       = 1.5

    elif adx >= 25 and vol_regime == "NORMAL":
        regime      = "TRENDING"
        should_trade = True
        reason      = f"Trend (ADX={adx:.1f})"
        score       = 1.0

    elif adx < 18:
        regime      = "RANGING"
        should_trade = False
        reason      = f"Yatay piyasa (ADX={adx:.1f} < 18)"
        score       = -1.5

    elif adx < 22:
        regime      = "RANGING"
        should_trade = False
        reason      = f"Zayıf trend / yatay (ADX={adx:.1f})"
        score       = -1.0

    else:
        regime      = "TRANSITION"
        should_trade = adx >= 23
        reason      = f"Geçiş (ADX={adx:.1f})"
        score       = 0.0

    return {
        "regime":          regime,
        "adx":             round(adx, 2),
        "di_plus":         round(di_plus, 2),
        "di_minus":        round(di_minus, 2),
        "atr_pct":         round(atr_pct, 3),
        "vol_regime":      vol_regime,
        "vol_ratio":       round(vol_ratio, 2),
        "trend_direction": trend_direction,
        "should_trade":    should_trade,
        "regime_score":    round(score, 2),
        "reason":          reason,
    }
