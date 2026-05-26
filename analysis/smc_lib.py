"""
analysis/smc_lib.py — smartmoneyconcepts kütüphane sarmalayıcısı
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
pip install smartmoneyconcepts>=0.0.26

Görevler:
  1. Cross-validation: Mevcut SMC motorunun tespitlerini ikinci kaynakla teyit et.
     Her iki motor aynı sinyali görüyorsa composite_score'a güven boost eklenir.
  2. PDH/PDL: Previous Day High/Low — ICT'de kritik seviyeler, mevcut motorda yok.
  3. Kesin retracement/OTE Fibonacci seviyeleri.

Anti-repainting: tüm fonksiyonlar df.iloc[:-1] slice ile çalışır,
son açık mumu görmez (BinanceFetcher zaten çıkarmış olsa da double-check).

Fallback: kütüphane kurulu değilse tüm fonksiyonlar no-op döner,
sistem kesintisiz çalışmaya devam eder.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("analysis.smc_lib")

try:
    from smartmoneyconcepts import smc as _smc
    _SMC_AVAILABLE = True
except ImportError:
    _smc = None
    _SMC_AVAILABLE = False
    logger.info("smartmoneyconcepts kurulu değil — pip install smartmoneyconcepts")


# ══════════════════════════════════════════════════════════════════════
#  YARDIMCILAR
# ══════════════════════════════════════════════════════════════════════

def _prep(df: pd.DataFrame) -> pd.DataFrame:
    """DataFrame'i kütüphane formatına hazırla: küçük harf kolonlar, açık mum yok."""
    out = df.copy()
    out.columns = out.columns.str.lower()
    required = {"open", "high", "low", "close", "volume"}
    if not required.issubset(set(out.columns)):
        raise ValueError("DataFrame eksik kolon: open/high/low/close/volume gerekli")
    return out.iloc[:-1] if len(out) > 1 else out


def _safe_bool(series: pd.Series, value: int, lookback: int = 5) -> bool:
    """Serinin son `lookback` satırında `value` var mı."""
    try:
        tail = series.dropna().tail(lookback)
        return bool((tail == value).any())
    except Exception:
        return False


def _last_level(df_col: pd.Series, mask: pd.Series) -> Optional[float]:
    """Mask=True olan son satırdaki seviye."""
    try:
        idx = mask[mask].last_valid_index()
        if idx is not None:
            return float(df_col.loc[idx])
    except Exception:
        pass
    return None


# ══════════════════════════════════════════════════════════════════════
#  1. PREVIOUS DAY HIGH / LOW (PDH / PDL)
#     ICT temel konsepti: dün kapanan günün yüksek/alçağı önemli seviyedir.
# ══════════════════════════════════════════════════════════════════════

def previous_day_levels(df: pd.DataFrame) -> dict:
    """
    PDH (Previous Day High) ve PDL (Previous Day Low) hesapla.
    Fiyat PDH'yi kırıp kapanırsa → güçlü bullish yapı.
    Fiyat PDL'yi kırıp kapanırsa → güçlü bearish yapı.

    Returns:
        pdh, pdl, pdh_broken, pdl_broken, pdh_distance_pct, pdl_distance_pct
    """
    empty = {
        "pdh": None, "pdl": None,
        "pdh_broken": False, "pdl_broken": False,
        "pdh_distance_pct": None, "pdl_distance_pct": None,
    }

    if not _SMC_AVAILABLE or df.empty or len(df) < 10:
        return empty

    try:
        ohlc = _prep(df)
        result = _smc.previous_high_low(ohlc, time_frame="1D")

        pdh_col = result.get("PreviousHigh") if isinstance(result, dict) else (
            result["PreviousHigh"] if "PreviousHigh" in result.columns else None
        )
        pdl_col = result.get("PreviousLow") if isinstance(result, dict) else (
            result["PreviousLow"] if "PreviousLow" in result.columns else None
        )

        if pdh_col is None or pdl_col is None:
            return empty

        pdh = float(pdh_col.dropna().iloc[-1]) if not pdh_col.dropna().empty else None
        pdl = float(pdl_col.dropna().iloc[-1]) if not pdl_col.dropna().empty else None

        current = float(ohlc["close"].iloc[-1])

        pdh_broken = bool(pdh and current > pdh)
        pdl_broken = bool(pdl and current < pdl)
        pdh_dist = round((current - pdh) / pdh * 100, 3) if pdh else None
        pdl_dist = round((current - pdl) / pdl * 100, 3) if pdl else None

        return {
            "pdh": pdh,
            "pdl": pdl,
            "pdh_broken": pdh_broken,
            "pdl_broken": pdl_broken,
            "pdh_distance_pct": pdh_dist,
            "pdl_distance_pct": pdl_dist,
        }

    except Exception as exc:
        logger.debug("PDH/PDL hesaplama hatası: %s", exc)
        return empty


# ══════════════════════════════════════════════════════════════════════
#  2. CROSS-VALIDATION
#     Mevcut SMC motoru ile smartmoneyconcepts karşılaştırması.
#     Her uyuşan sinyal için score_boost artar.
# ══════════════════════════════════════════════════════════════════════

def cross_validate(
    df: pd.DataFrame,
    trend: str,
    existing_bos_bull: bool = False,
    existing_bos_bear: bool = False,
    existing_fvg_bull: list = None,
    existing_fvg_bear: list = None,
    existing_ob_bull: list = None,
    existing_ob_bear: list = None,
) -> dict:
    """
    smartmoneyconcepts ile mevcut motorun çıktılarını karşılaştırır.

    Her kategori için:
      - Tam uyuşma → +0.4 boost
      - Kısmi uyuşma → +0.2 boost

    Returns:
        score_boost: float  (0.0 – 1.5, composite_score'a eklenir)
        agreements: list    (hangi sinyaller onaylandı)
        lib_bos_bull: bool
        lib_bos_bear: bool
        lib_fvg_bull_count: int
        lib_fvg_bear_count: int
        lib_ob_bull_count: int
        lib_ob_bear_count: int
        pdh_pdl: dict
    """
    if existing_fvg_bull is None:
        existing_fvg_bull = []
    if existing_fvg_bear is None:
        existing_fvg_bear = []
    if existing_ob_bull is None:
        existing_ob_bull = []
    if existing_ob_bear is None:
        existing_ob_bear = []

    empty = {
        "score_boost": 0.0,
        "agreements": [],
        "lib_bos_bull": False,
        "lib_bos_bear": False,
        "lib_fvg_bull_count": 0,
        "lib_fvg_bear_count": 0,
        "lib_ob_bull_count": 0,
        "lib_ob_bear_count": 0,
        "pdh_pdl": {},
    }

    if not _SMC_AVAILABLE or df.empty or len(df) < 50:
        return empty

    try:
        ohlc = _prep(df)
        boost = 0.0
        agreements = []

        # ── Swing Highs/Lows (BOS/CHoCH için gerekli) ────────────
        swings = _smc.swing_highs_lows(ohlc, swing_length=10)

        # ── BOS / CHoCH ───────────────────────────────────────────
        bos_df = _smc.bos_choch(ohlc, swings, close_break=True)

        lib_bos_bull = False
        lib_bos_bear = False
        lib_choch_bull = False
        lib_choch_bear = False

        if "BOS" in bos_df.columns:
            lib_bos_bull = _safe_bool(bos_df["BOS"], 1, lookback=6)
            lib_bos_bear = _safe_bool(bos_df["BOS"], -1, lookback=6)
        if "CHOCH" in bos_df.columns:
            lib_choch_bull = _safe_bool(bos_df["CHOCH"], 1, lookback=6)
            lib_choch_bear = _safe_bool(bos_df["CHOCH"], -1, lookback=6)

        # Cross-validate BOS
        if trend == "BULLISH":
            if existing_bos_bull and lib_bos_bull:
                boost += 0.4
                agreements.append("BOS Bullish (çift teyit)")
            elif lib_choch_bull and trend == "BULLISH":
                boost += 0.2
                agreements.append("CHoCH Bullish (lib teyit)")
        elif trend == "BEARISH":
            if existing_bos_bear and lib_bos_bear:
                boost += 0.4
                agreements.append("BOS Bearish (çift teyit)")
            elif lib_choch_bear:
                boost += 0.2
                agreements.append("CHoCH Bearish (lib teyit)")

        # ── Fair Value Gaps ───────────────────────────────────────
        fvg_df = _smc.fvg(ohlc)

        lib_fvg_bull = 0
        lib_fvg_bear = 0
        if "FVG" in fvg_df.columns:
            unmitigated = fvg_df[fvg_df.get("MitigatedIndex", pd.Series(dtype=float)).isna()] if "MitigatedIndex" in fvg_df.columns else fvg_df
            lib_fvg_bull = int((fvg_df["FVG"] == 1).sum())
            lib_fvg_bear = int((fvg_df["FVG"] == -1).sum())

        if trend == "BULLISH" and existing_fvg_bull and lib_fvg_bull > 0:
            boost += 0.3
            agreements.append("FVG Bullish (çift teyit)")
        elif trend == "BEARISH" and existing_fvg_bear and lib_fvg_bear > 0:
            boost += 0.3
            agreements.append("FVG Bearish (çift teyit)")

        # ── Order Blocks ──────────────────────────────────────────
        ob_df = _smc.ob(ohlc, swings)

        lib_ob_bull = 0
        lib_ob_bear = 0
        if "OB" in ob_df.columns:
            lib_ob_bull = int((ob_df["OB"] == 1).sum())
            lib_ob_bear = int((ob_df["OB"] == -1).sum())

        if trend == "BULLISH" and existing_ob_bull and lib_ob_bull > 0:
            boost += 0.3
            agreements.append("Order Block Bullish (çift teyit)")
        elif trend == "BEARISH" and existing_ob_bear and lib_ob_bear > 0:
            boost += 0.3
            agreements.append("Order Block Bearish (çift teyit)")

        # ── PDH/PDL ───────────────────────────────────────────────
        pdh_pdl = previous_day_levels(df)

        if trend == "BULLISH" and pdh_pdl.get("pdh_broken"):
            boost += 0.2
            agreements.append("PDH kırıldı — bullish momentum")
        elif trend == "BEARISH" and pdh_pdl.get("pdl_broken"):
            boost += 0.2
            agreements.append("PDL kırıldı — bearish momentum")

        return {
            "score_boost": round(min(1.5, boost), 2),
            "agreements": agreements,
            "lib_bos_bull": lib_bos_bull,
            "lib_bos_bear": lib_bos_bear,
            "lib_fvg_bull_count": lib_fvg_bull,
            "lib_fvg_bear_count": lib_fvg_bear,
            "lib_ob_bull_count": lib_ob_bull,
            "lib_ob_bear_count": lib_ob_bear,
            "pdh_pdl": pdh_pdl,
        }

    except Exception as exc:
        logger.debug("Cross-validation hatası: %s", exc)
        return empty


# ══════════════════════════════════════════════════════════════════════
#  3. OTE / RETRACEMENTS (Optimal Trade Entry)
#     Fibonacci %61.8 – %78.6 bölgesi
# ══════════════════════════════════════════════════════════════════════

def ote_levels(df: pd.DataFrame, trend: str) -> dict:
    """
    OTE bölgesi: Fibonacci 0.618 – 0.786 arası.
    Mevcut fiyat bu bölgedeyse giriş kalitesi artar.

    Returns:
        in_ote: bool
        ote_low, ote_high: float
        retracement_pct: float  (ne kadar geri çekildi)
        ote_score: float  (0.0 – 1.0)
    """
    empty = {"in_ote": False, "ote_low": None, "ote_high": None,
             "retracement_pct": None, "ote_score": 0.0}

    if not _SMC_AVAILABLE or df.empty or len(df) < 30:
        return empty

    try:
        ohlc = _prep(df)
        swings = _smc.swing_highs_lows(ohlc, swing_length=10)
        ret_df = _smc.retracements(ohlc, swings)

        if ret_df.empty or "Retracement" not in ret_df.columns:
            return empty

        last_ret = ret_df["Retracement"].dropna()
        if last_ret.empty:
            return empty

        ret_pct = float(last_ret.iloc[-1])
        current = float(ohlc["close"].iloc[-1])

        # Swing range (son swing)
        sh_idx = swings[swings["HighLow"] == 1].last_valid_index() if "HighLow" in swings.columns else None
        sl_idx = swings[swings["HighLow"] == -1].last_valid_index() if "HighLow" in swings.columns else None

        if sh_idx is None or sl_idx is None:
            return empty

        swing_high = float(ohlc.loc[sh_idx, "high"]) if sh_idx in ohlc.index else None
        swing_low = float(ohlc.loc[sl_idx, "low"]) if sl_idx in ohlc.index else None

        if swing_high is None or swing_low is None:
            return empty

        rng = swing_high - swing_low
        if rng <= 0:
            return empty

        # OTE = Fib 0.618 – 0.786 geri çekilme seviyesi
        if trend == "BULLISH":
            ote_low = swing_high - rng * 0.786
            ote_high = swing_high - rng * 0.618
        else:
            ote_low = swing_low + rng * 0.618
            ote_high = swing_low + rng * 0.786

        in_ote = bool(ote_low <= current <= ote_high)

        # Skor: OTE içindeyse tam puan, yakınsa kısmi
        if in_ote:
            score = 1.0
        elif abs(current - (ote_low + ote_high) / 2) / rng < 0.1:
            score = 0.5
        else:
            score = 0.0

        return {
            "in_ote": in_ote,
            "ote_low": round(ote_low, 6),
            "ote_high": round(ote_high, 6),
            "retracement_pct": round(ret_pct * 100, 1),
            "ote_score": score,
        }

    except Exception as exc:
        logger.debug("OTE hesaplama hatası: %s", exc)
        return empty


# ══════════════════════════════════════════════════════════════════════
#  4. LIQUIDITY SWEEP (LIB)
#     smartmoneyconcepts'in liquidity tespiti
# ══════════════════════════════════════════════════════════════════════

def liquidity_levels(df: pd.DataFrame) -> dict:
    """
    Tespit edilen equal high/low (BSL/SSL) ve sweep edilip edilmediği.

    Returns:
        bsl_levels: list of float  (Buyside Liquidity)
        ssl_levels: list of float  (Sellside Liquidity)
        bsl_swept_count: int
        ssl_swept_count: int
    """
    empty = {"bsl_levels": [], "ssl_levels": [], "bsl_swept_count": 0, "ssl_swept_count": 0}

    if not _SMC_AVAILABLE or df.empty or len(df) < 30:
        return empty

    try:
        ohlc = _prep(df)
        swings = _smc.swing_highs_lows(ohlc, swing_length=10)
        liq_df = _smc.liquidity(ohlc, swings, range_percent=0.01)

        if liq_df.empty or "Liquidity" not in liq_df.columns:
            return empty

        bsl = liq_df[liq_df["Liquidity"] == 1]
        ssl = liq_df[liq_df["Liquidity"] == -1]

        bsl_levels = bsl["Level"].dropna().tolist() if "Level" in bsl.columns else []
        ssl_levels = ssl["Level"].dropna().tolist() if "Level" in ssl.columns else []

        swept_col = "Swept" if "Swept" in liq_df.columns else None
        bsl_swept = int(bsl[swept_col].sum()) if swept_col and swept_col in bsl.columns else 0
        ssl_swept = int(ssl[swept_col].sum()) if swept_col and swept_col in ssl.columns else 0

        return {
            "bsl_levels": [round(float(l), 6) for l in bsl_levels[-5:]],
            "ssl_levels": [round(float(l), 6) for l in ssl_levels[-5:]],
            "bsl_swept_count": bsl_swept,
            "ssl_swept_count": ssl_swept,
        }

    except Exception as exc:
        logger.debug("Liquidity levels hatası: %s", exc)
        return empty


# ══════════════════════════════════════════════════════════════════════
#  5. TAM ANALİZ (Tek çağrı ile hepsini döndür)
# ══════════════════════════════════════════════════════════════════════

def full_smc_lib_analysis(
    df: pd.DataFrame,
    trend: str = "NEUTRAL",
    existing_bos_bull: bool = False,
    existing_bos_bear: bool = False,
    existing_fvg_bull: list = None,
    existing_fvg_bear: list = None,
    existing_ob_bull: list = None,
    existing_ob_bear: list = None,
) -> dict:
    """
    Tüm smc_lib analizini tek seferinde çalıştırır.

    Returns:
        cross_val: dict     (score_boost, agreements, ...)
        ote: dict           (in_ote, ote_low, ote_high, ote_score)
        liquidity: dict     (bsl_levels, ssl_levels, ...)
        pdh_pdl: dict       (pdh, pdl, pdh_broken, pdl_broken)
        available: bool     (kütüphane kurulu mu)
    """
    if existing_fvg_bull is None:
        existing_fvg_bull = []
    if existing_fvg_bear is None:
        existing_fvg_bear = []
    if existing_ob_bull is None:
        existing_ob_bull = []
    if existing_ob_bear is None:
        existing_ob_bear = []

    cross_val = cross_validate(
        df, trend,
        existing_bos_bull=existing_bos_bull,
        existing_bos_bear=existing_bos_bear,
        existing_fvg_bull=existing_fvg_bull,
        existing_fvg_bear=existing_fvg_bear,
        existing_ob_bull=existing_ob_bull,
        existing_ob_bear=existing_ob_bear,
    )

    ote = ote_levels(df, trend)
    liq = liquidity_levels(df)

    return {
        "cross_val": cross_val,
        "ote": ote,
        "liquidity": liq,
        "pdh_pdl": cross_val.get("pdh_pdl", {}),
        "available": _SMC_AVAILABLE,
    }
