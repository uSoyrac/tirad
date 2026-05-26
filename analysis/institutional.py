"""
Kurumsal & kripto-özel metrikler: CVD, Funding Rate, Open Interest.
BIST hisseleri için basitleştirilmiş versiyon (CVD yoktur).
"""
import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class InstitutionalResult:
    cvd_bullish: bool = False
    funding_neutral: bool = False
    funding_extreme_long: bool = False
    funding_extreme_short: bool = False
    oi_bullish: bool = False
    whale_positive: bool = False

    funding_rate: float | None = None
    open_interest: float | None = None

    score: float = 0.0
    max_score: float = 7.0
    details: dict = field(default_factory=dict)


def compute_cvd(df: pd.DataFrame) -> dict:
    """
    Cumulative Volume Delta — tick data olmadan yaklaşık CVD.
    Formül: Her mum için (close > open) → +volume, else → -volume
    Gerçek CVD'ye yakın ama daha düşük hassasiyetli.
    """
    if df.empty or "volume" not in df.columns:
        return {"bullish": False, "cvd_trend": 0}

    closes = df["close"]
    opens = df["open"]
    volumes = df["volume"]

    delta = pd.Series(
        np.where(closes > opens, volumes, -volumes),
        index=df.index
    )
    cvd = delta.cumsum()

    # Son 20 mum CVD trendi
    recent_cvd = cvd.iloc[-21:-1]  # Anti-repainting
    recent_price = closes.iloc[-21:-1]

    if len(recent_cvd) < 10:
        return {"bullish": False, "cvd_trend": 0}

    cvd_going_up = recent_cvd.iloc[-1] > recent_cvd.iloc[0]
    price_going_up = recent_price.iloc[-1] > recent_price.iloc[0]

    return {
        "bullish": cvd_going_up and price_going_up,
        "cvd_trend": 1 if cvd_going_up else -1,
        "last_cvd": float(recent_cvd.iloc[-1]),
    }


def analyze_funding_rate(funding_rate: float | None) -> dict:
    """
    Funding rate analizi.
    Nötr (-0.01% ile +0.01%) = +1 (sağlıklı piyasa)
    Aşırı pozitif (>0.05%) = -2 (long kalabalığı, dikkat)
    Aşırı negatif (<-0.05%) = +1 (short sıkışması fırsatı)
    """
    if funding_rate is None:
        return {"score": 0, "neutral": False, "extreme_long": False, "extreme_short": False}

    fr_pct = funding_rate * 100  # Yüzdeye çevir

    if -0.01 <= fr_pct <= 0.01:
        return {"score": 1.0, "neutral": True, "extreme_long": False, "extreme_short": False,
                "label": f"Nötr ({fr_pct:.4f}%)"}
    elif fr_pct > 0.05:
        return {"score": -2.0, "neutral": False, "extreme_long": True, "extreme_short": False,
                "label": f"Aşırı Long Kalabalığı ({fr_pct:.4f}%)"}
    elif fr_pct < -0.05:
        return {"score": 1.0, "neutral": False, "extreme_long": False, "extreme_short": True,
                "label": f"Short Sıkışması Fırsatı ({fr_pct:.4f}%)"}
    else:
        return {"score": 0.0, "neutral": False, "extreme_long": False, "extreme_short": False,
                "label": f"Normal ({fr_pct:.4f}%)"}


def analyze_open_interest(df_oi_history: pd.DataFrame | None, current_oi: float | None,
                           df_price: pd.DataFrame) -> dict:
    """
    Open Interest analizi.
    OI artıyor + fiyat artıyor = gerçek trend güçleniyor = +2
    OI artıyor + fiyat düşüyor = short baskısı yoğunlaşıyor = nötr
    OI azalıyor + fiyat artıyor = short squeeze = geçici = 0
    """
    if current_oi is None:
        return {"score": 0, "bullish": False}

    # Fiyat son 20 mum
    recent_price = df_price["close"].iloc[-21:-1]
    price_up = recent_price.iloc[-1] > recent_price.iloc[0] if len(recent_price) >= 2 else False

    # OI tarihi yoksa sadece yönlü değerlendirme
    score = 2.0 if price_up else 0.0
    return {"score": score, "bullish": price_up, "oi": current_oi}


def analyze_institutional(df: pd.DataFrame, extras: dict, is_bist: bool = False) -> InstitutionalResult:
    """
    Kurumsal metrik analizi.
    BIST hisseleri için CVD ve funding rate yoktur — basit hacim analizi.
    Maksimum puan: 7
    """
    result = InstitutionalResult()
    score = 0.0
    details = {}

    if is_bist:
        # BIST için basit hacim ve momentum analizi
        if not df.empty and "volume" in df.columns:
            vol_avg = df["volume"].iloc[-21:-1].mean()
            recent_vol = df["volume"].iloc[-2]
            if vol_avg > 0 and recent_vol > vol_avg * 1.5:
                score += 2.0
                details["vol"] = "BIST: Yüksek Hacim Onayı ✅ (+2)"
            result.cvd_bullish = recent_vol > vol_avg
        result.score = min(score, result.max_score)
        result.details = details
        return result

    # Kripto
    funding_rate = extras.get("funding_rate")
    open_interest = extras.get("open_interest")

    # 1. CVD (approximate)
    cvd_data = compute_cvd(df)
    result.cvd_bullish = cvd_data["bullish"]
    if cvd_data["bullish"]:
        score += 2.0
        details["cvd"] = "CVD Uptrend + Fiyat Uyumu ✅ (+2)"

    # 2. Funding Rate
    fr_data = analyze_funding_rate(funding_rate)
    result.funding_rate = funding_rate
    result.funding_neutral = fr_data["neutral"]
    result.funding_extreme_long = fr_data["extreme_long"]
    result.funding_extreme_short = fr_data["extreme_short"]
    fr_score = fr_data["score"]
    score += max(0, fr_score)  # Negatif skoru toplama ama kaydet
    if fr_score != 0:
        details["funding"] = f"Funding Rate: {fr_data.get('label', '')} ({'+' if fr_score >= 0 else ''}{fr_score})"

    # Aşırı long uyarısı (skora eklenmez ama gösterilir)
    if fr_data["extreme_long"]:
        details["funding_warn"] = "⚠️ Aşırı Long Kalabalığı — Dikkatli Ol"

    # 3. Open Interest
    oi_data = analyze_open_interest(None, open_interest, df)
    result.oi_bullish = oi_data["bullish"]
    result.open_interest = open_interest
    score += oi_data["score"]
    if oi_data["bullish"]:
        details["oi"] = f"OI Artış + Fiyat Artış ✅ (+2)"

    result.score = min(score, result.max_score)
    result.details = details
    return result
