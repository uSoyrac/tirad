"""
Klasik teknik indikatörler — pandas-ta tabanlı.
Anti-repainting: shift(1) ile her hesap bir önceki kapanmış muma göre.
"""
import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)


@dataclass
class ClassicResult:
    ema_bullish: bool = False
    ema_partial: bool = False
    macd_bullish: bool = False
    rsi_hidden_div: bool = False
    rsi_classic_div: bool = False
    stoch_rsi_bullish: bool = False
    bb_squeeze_breakout: bool = False
    vwap_above: bool = False
    obv_uptrend: bool = False

    # Değerler
    ema8: float | None = None
    ema21: float | None = None
    ema55: float | None = None
    ema200: float | None = None
    rsi: float | None = None
    macd_hist: float | None = None
    current_price: float | None = None

    score: float = 0.0
    max_score: float = 10.0
    details: dict = field(default_factory=dict)


def _safe_last(series: pd.Series, shift: int = 1) -> float | None:
    """Anti-repainting: shift(1) ile bir önceki kapanmış mum değeri."""
    shifted = series.shift(shift)
    if shifted.empty or pd.isna(shifted.iloc[-1]):
        return None
    return float(shifted.iloc[-1])


def analyze_ema(df: pd.DataFrame, periods: list = None) -> dict:
    """EMA ribbon analizi. Tam sıralama = +2, kısmi = +1, ters = -1"""
    if periods is None:
        periods = [8, 21, 55, 200]

    closes = df["close"]
    emas = {}
    for p in periods:
        ema = ta.ema(closes, length=p)
        if ema is not None and not ema.empty:
            emas[p] = _safe_last(ema)

    if len(emas) < len(periods) or any(v is None for v in emas.values()):
        return {"score": 0, "bullish": False, "partial": False, "values": emas}

    vals = [emas[p] for p in sorted(periods)]  # [ema8, ema21, ema55, ema200]

    # Tam bullish sıralama: ema8 > ema21 > ema55 > ema200
    full_bullish = all(vals[i] > vals[i + 1] for i in range(len(vals) - 1))

    # Kısmi: En az 2 ardışık doğru sırada
    partial = sum(1 for i in range(len(vals) - 1) if vals[i] > vals[i + 1]) >= 2

    score = 2.0 if full_bullish else (1.0 if partial else -1.0)

    return {
        "score": score, "bullish": full_bullish, "partial": partial and not full_bullish,
        "values": emas,
    }


def analyze_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """MACD histogram analizi. Büyüyor + sıfır üstü = +2"""
    closes = df["close"]
    macd_df = ta.macd(closes, fast=fast, slow=slow, signal=signal)
    if macd_df is None or macd_df.empty:
        return {"score": 0, "bullish": False, "hist": None}

    col_hist = [c for c in macd_df.columns if "h" in c.lower()]
    if not col_hist:
        return {"score": 0, "bullish": False, "hist": None}

    hist = macd_df[col_hist[0]]
    current_hist = _safe_last(hist)
    prev_hist = _safe_last(hist, shift=2)

    if current_hist is None or prev_hist is None:
        return {"score": 0, "bullish": False, "hist": current_hist}

    growing_positive = current_hist > 0 and current_hist > prev_hist
    score = 2.0 if growing_positive else (1.0 if current_hist > 0 else 0.0)

    return {"score": score, "bullish": growing_positive, "hist": current_hist}


def detect_rsi_divergence(df: pd.DataFrame, period: int = 14, lookback: int = 30) -> dict:
    """
    RSI diverjans tespiti.
    Gizli boğa: Fiyat düşük yaptı ama RSI yüksek yaptı = +2
    Klasik boğa: Fiyat yüksek yaptı ama RSI düşük yaptı = +1
    """
    closes = df["close"]
    lows = df["low"]

    rsi_series = ta.rsi(closes, length=period)
    if rsi_series is None or rsi_series.empty:
        return {"score": 0, "hidden": False, "classic": False, "rsi": None}

    current_rsi = _safe_last(rsi_series)

    if len(df) < lookback + period:
        return {"score": 0, "hidden": False, "classic": False, "rsi": current_rsi}

    price_window = lows.iloc[-lookback:-1]
    rsi_window = rsi_series.iloc[-lookback:-1].shift(1).dropna()

    if len(price_window) < 10 or len(rsi_window) < 10:
        return {"score": 0, "hidden": False, "classic": False, "rsi": current_rsi}

    price_min_idx = price_window.idxmin()
    rsi_at_price_min = rsi_window.get(price_min_idx, None)
    rsi_recent = rsi_window.iloc[-5:].mean()

    hidden_bull_div = False
    classic_bull_div = False

    if rsi_at_price_min is not None:
        price_made_lower_low = price_window.iloc[-1] < price_window.iloc[0]
        rsi_made_higher_low = rsi_window.iloc[-1] > rsi_at_price_min

        if price_made_lower_low and rsi_made_higher_low:
            hidden_bull_div = True

        price_made_higher_high = lows.iloc[-2] > price_window.max()
        rsi_made_lower_high = (current_rsi or 50) < rsi_window.max()

        if price_made_higher_high and rsi_made_lower_high:
            classic_bull_div = True

    score = 2.0 if hidden_bull_div else (1.0 if classic_bull_div else 0.0)

    return {
        "score": score, "hidden": hidden_bull_div,
        "classic": classic_bull_div, "rsi": current_rsi,
    }


def analyze_stoch_rsi(df: pd.DataFrame, period: int = 14, smooth_k: int = 3, smooth_d: int = 3) -> dict:
    """Stochastic RSI — 20 altından yukarı kesişim = +1"""
    closes = df["close"]
    stoch = ta.stochrsi(closes, length=period, rsi_length=period, k=smooth_k, d=smooth_d)
    if stoch is None or stoch.empty:
        return {"score": 0, "bullish": False}

    k_col = [c for c in stoch.columns if "k" in c.lower()]
    d_col = [c for c in stoch.columns if "d" in c.lower() and "k" not in c.lower()]

    if not k_col:
        return {"score": 0, "bullish": False}

    k = stoch[k_col[0]]
    current_k = _safe_last(k)
    prev_k = _safe_last(k, shift=2)

    if current_k is None or prev_k is None:
        return {"score": 0, "bullish": False}

    # 20 altından yukarı geçiş (önceki bar < 20, şu an > 20)
    cross_up_from_oversold = prev_k < 20 and current_k > 20
    score = 1.0 if cross_up_from_oversold else 0.0

    return {"score": score, "bullish": cross_up_from_oversold, "k": current_k}


def analyze_bollinger(df: pd.DataFrame, period: int = 20, std: float = 2.0) -> dict:
    """Bollinger Band — squeeze sonrası yukarı kırılma = +1"""
    closes = df["close"]
    bbands = ta.bbands(closes, length=period, std=std)
    if bbands is None or bbands.empty:
        return {"score": 0, "squeeze_breakout": False}

    upper_col = [c for c in bbands.columns if "u" in c.lower()]
    lower_col = [c for c in bbands.columns if "l" in c.lower() and "m" not in c.lower()]
    bw_col = [c for c in bbands.columns if "bw" in c.lower() or "bandwidth" in c.lower()]

    if not upper_col or not lower_col:
        return {"score": 0, "squeeze_breakout": False}

    upper = bbands[upper_col[0]]
    lower = bbands[lower_col[0]]
    width = (upper - lower) / closes

    current_price = _safe_last(closes)
    current_upper = _safe_last(upper)
    prev_width = _safe_last(width, shift=2)
    current_width = _safe_last(width)

    if any(v is None for v in [current_price, current_upper, prev_width, current_width]):
        return {"score": 0, "squeeze_breakout": False}

    squeeze_was_on = prev_width < width.rolling(20).mean().shift(2).iloc[-1] * 0.8
    breakout_up = current_price > current_upper

    score = 1.0 if (squeeze_was_on and breakout_up) else 0.0
    return {"score": score, "squeeze_breakout": squeeze_was_on and breakout_up}


def analyze_vwap(df: pd.DataFrame) -> dict:
    """VWAP — fiyat VWAP üstünde = +1"""
    if "volume" not in df.columns:
        return {"score": 0, "above": False, "vwap": None}

    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    cum_tp_vol = (typical_price * df["volume"]).cumsum()
    cum_vol = df["volume"].cumsum()
    vwap = cum_tp_vol / cum_vol

    current_price = _safe_last(df["close"])
    current_vwap = _safe_last(vwap)

    if current_price is None or current_vwap is None or current_vwap == 0:
        return {"score": 0, "above": False, "vwap": current_vwap}

    above = current_price > current_vwap
    return {"score": 1.0 if above else 0.0, "above": above, "vwap": current_vwap}


def analyze_obv(df: pd.DataFrame) -> dict:
    """OBV uptrend + fiyat uptrend = +1"""
    closes = df["close"]
    obv_series = ta.obv(closes, df["volume"])
    if obv_series is None or obv_series.empty:
        return {"score": 0, "uptrend": False}

    obv_now = _safe_last(obv_series)
    obv_prev = _safe_last(obv_series, shift=10)
    price_now = _safe_last(closes)
    price_prev = _safe_last(closes, shift=10)

    if any(v is None for v in [obv_now, obv_prev, price_now, price_prev]):
        return {"score": 0, "uptrend": False}

    obv_up = obv_now > obv_prev
    price_up = price_now > price_prev

    score = 1.0 if (obv_up and price_up) else 0.0
    return {"score": score, "uptrend": obv_up and price_up}


def analyze_classic(df: pd.DataFrame, config: dict = None) -> ClassicResult:
    """
    Ana klasik indikatör analizi — tümünü birleştirir.
    Maksimum puan: 10
    """
    if config is None:
        config = {}

    result = ClassicResult()

    if df.empty or len(df) < 210:
        logger.warning("Klasik analiz için yetersiz veri (min 210 bar gerekli)")
        return result

    ema_periods = config.get("ema_periods", [8, 21, 55, 200])
    macd_cfg = config.get("macd", {"fast": 12, "slow": 26, "signal": 9})
    rsi_period = config.get("rsi_period", 14)
    stoch_cfg = config.get("stoch_rsi", {"period": 14, "smooth_k": 3, "smooth_d": 3})
    bb_cfg = config.get("bollinger", {"period": 20, "std": 2.0})

    score = 0.0
    details = {}

    # 1. EMA
    ema_data = analyze_ema(df, ema_periods)
    result.ema_bullish = ema_data["bullish"]
    result.ema_partial = ema_data["partial"]
    result.ema8 = ema_data["values"].get(8)
    result.ema21 = ema_data["values"].get(21)
    result.ema55 = ema_data["values"].get(55)
    result.ema200 = ema_data["values"].get(200)
    score += max(0, ema_data["score"])
    if ema_data["bullish"]:
        details["ema"] = "EMA Ribbon Bullish Sıralama ✅ (+2)"
    elif ema_data["partial"]:
        details["ema"] = "EMA Kısmi Sıralama (+1)"

    # 2. MACD
    macd_data = analyze_macd(df, macd_cfg["fast"], macd_cfg["slow"], macd_cfg["signal"])
    result.macd_bullish = macd_data["bullish"]
    result.macd_hist = macd_data["hist"]
    score += macd_data["score"]
    if macd_data["bullish"]:
        details["macd"] = f"MACD Pozitif Momentum ✅ (+2) hist={macd_data['hist']:.6f}"

    # 3. RSI Diverjans
    rsi_data = detect_rsi_divergence(df, rsi_period)
    result.rsi_hidden_div = rsi_data["hidden"]
    result.rsi_classic_div = rsi_data["classic"]
    result.rsi = rsi_data["rsi"]
    score += rsi_data["score"]
    if rsi_data["hidden"]:
        details["rsi"] = f"RSI Gizli Boğa Diverjansı ✅ (+2) RSI={rsi_data['rsi']:.1f}"
    elif rsi_data["classic"]:
        details["rsi"] = f"RSI Klasik Diverjans (+1) RSI={rsi_data['rsi']:.1f}"

    # 4. Stochastic RSI
    stoch_data = analyze_stoch_rsi(df, stoch_cfg["period"], stoch_cfg["smooth_k"], stoch_cfg["smooth_d"])
    result.stoch_rsi_bullish = stoch_data["bullish"]
    score += stoch_data["score"]
    if stoch_data["bullish"]:
        details["stoch"] = "Stoch RSI Oversold'dan Yukarı ✅ (+1)"

    # 5. Bollinger
    bb_data = analyze_bollinger(df, bb_cfg["period"], bb_cfg["std"])
    result.bb_squeeze_breakout = bb_data["squeeze_breakout"]
    score += bb_data["score"]
    if bb_data["squeeze_breakout"]:
        details["bb"] = "Bollinger Squeeze Kırılma ✅ (+1)"

    # 6. VWAP
    vwap_data = analyze_vwap(df)
    result.vwap_above = vwap_data["above"]
    score += vwap_data["score"]
    if vwap_data["above"]:
        details["vwap"] = f"VWAP Üstünde ✅ (+1) VWAP={vwap_data['vwap']:.4f}"

    # 7. OBV
    obv_data = analyze_obv(df)
    result.obv_uptrend = obv_data["uptrend"]
    score += obv_data["score"]
    if obv_data["uptrend"]:
        details["obv"] = "OBV Uptrend Konfirmasyonu ✅ (+1)"

    result.current_price = _safe_last(df["close"])
    result.score = min(score, result.max_score)
    result.details = details
    return result
