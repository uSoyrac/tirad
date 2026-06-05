"""
bot/advanced_indicators.py — İleri Seviye Teknik Göstergeler
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Kapsar:
  • Initial Balance (IB) — Günlük ilk 2 mum aralığı kırılma/reddi
  • ADR (Average Daily Range) — Günlük volatilite tükenmesi kontrolü
  • POC + SMC Çakışması — Hacim profili + OB/FVG kesişimi
  • Open Interest Delta — OI yönü ile fiyat yönü uyumu
  • Funding Rate Sinyali — Aşırı uzun/kısa → kontrarian fırsat
  • Session Analizi — Asia/London/NY oturumu güç haritası
  • Market Microstructure — Büyük mum kalıpları, delta uyumsuzluğu
  • Wyckoff Gelişmiş — Spring, UTAD, LPS, LPSY tespit
  • ADR Sınır Kontrolü — Günlük hareket tükenme testi
  • VWAP Sapma Bantları — VWAP ± stddev seviyeleri

Tüm fonksiyonlar pandas DataFrame alır, dict döner.
Tüm analizler sadece geçmiş veriye bakar (anti-repainting).
"""

import math
import numpy as np
import pandas as pd
from typing import Optional, Tuple, Dict, List
import logging

logger = logging.getLogger("bot.advanced")

# ══════════════════════════════════════════════════════════════════════
#  YARDIMCI FONKSİYONLAR
# ══════════════════════════════════════════════════════════════════════

def _safe(arr, default=0.0):
    """NaN/Inf korumalı float dönüşüm."""
    try:
        v = float(arr)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def _resample_daily(df_4h: pd.DataFrame) -> pd.DataFrame:
    """4H DataFrame'i günlük OHLCV'ye dönüştür."""
    try:
        return df_4h.resample("1D").agg({
            "open":  "first",
            "high":  "max",
            "low":   "min",
            "close": "last",
            "volume":"sum",
        }).dropna()
    except Exception:
        return pd.DataFrame()


# ══════════════════════════════════════════════════════════════════════
#  1. INITIAL BALANCE (IB)
# ══════════════════════════════════════════════════════════════════════

def initial_balance(df: pd.DataFrame, session_bars: int = 2) -> dict:
    """
    Initial Balance analizi.

    4H veri için IB = günün ilk 2 mumu (00:00 – 08:00 UTC).
    Mantık (ICT / Floor Traders):
      • IB oluşurken piyasa 'açılış' aralığını belirler.
      • IB High kırılırsa → boğa genişlemesi (long önyargı).
      • IB Low kırılırsa → ayı genişlemesi (short önyargı).
      • IB içinde kalırsa → yatay / dağılım seansı.
      • IB Red: fiyat IB'yi aştıktan sonra içeri dönerse → sahte kırılma.

    Döner:
        ib_high, ib_low, ib_mid, ib_range_pct,
        above_ib: bool, below_ib: bool, ib_breakout: str,
        ib_rejection: bool,   # Kırılıp geri döndü = fakeout
        ib_score: float (0–4, boğa/ayı gücü)
    """
    if len(df) < session_bars + 4:
        return _empty_ib()

    # Son tamamlanan günün IB'sini al (son session_bars mumu)
    ib_slice = df.iloc[-(session_bars + 4): -4]
    if len(ib_slice) < session_bars:
        return _empty_ib()

    ib_high = float(ib_slice["high"].max())
    ib_low  = float(ib_slice["low"].min())
    ib_mid  = (ib_high + ib_low) / 2
    ib_range_pct = (ib_high - ib_low) / ib_low * 100 if ib_low > 0 else 0

    # Son birkaç mum IB'ye göre nerede?
    recent = df.iloc[-4:]
    last_close = _safe(df["close"].iloc[-1])
    last_high  = _safe(df["high"].iloc[-1])
    last_low   = _safe(df["low"].iloc[-1])

    above_ib = last_close > ib_high
    below_ib = last_close < ib_low

    # Kırılma teyidi (son 3 kapanış)
    recent_closes = df["close"].iloc[-3:].values
    bull_breakout = all(c > ib_high for c in recent_closes)
    bear_breakout = all(c < ib_low  for c in recent_closes)

    if bull_breakout:
        ib_breakout = "BULL"
    elif bear_breakout:
        ib_breakout = "BEAR"
    else:
        ib_breakout = "NONE"

    # IB Rejection = kırıldı ama geri döndü (fakeout)
    max_recent_high = float(recent["high"].max())
    min_recent_low  = float(recent["low"].min())

    ib_rejection_bull = (max_recent_high > ib_high) and (last_close < ib_high)
    ib_rejection_bear = (min_recent_low  < ib_low)  and (last_close > ib_low)
    ib_rejection = ib_rejection_bull or ib_rejection_bear

    # IB Skoru (0–4)
    score = 0.0
    if ib_breakout == "BULL": score += 2.5
    elif ib_breakout == "BEAR": score -= 2.5

    if above_ib and not ib_rejection: score += 1.0
    if below_ib and not ib_rejection: score -= 1.0

    # Rejection: kontrarian
    if ib_rejection_bull: score -= 1.5  # Yukarı kırıp döndü = aşağı
    if ib_rejection_bear: score += 1.5  # Aşağı kırıp döndü = yukarı

    return {
        "ib_high":         ib_high,
        "ib_low":          ib_low,
        "ib_mid":          ib_mid,
        "ib_range_pct":    ib_range_pct,
        "above_ib":        above_ib,
        "below_ib":        below_ib,
        "ib_breakout":     ib_breakout,
        "ib_rejection":    ib_rejection,
        "ib_rejection_bull": ib_rejection_bull,
        "ib_rejection_bear": ib_rejection_bear,
        "ib_score":        round(score, 2),
    }


def _empty_ib():
    return {"ib_high": 0, "ib_low": 0, "ib_mid": 0, "ib_range_pct": 0,
            "above_ib": False, "below_ib": False, "ib_breakout": "NONE",
            "ib_rejection": False, "ib_rejection_bull": False,
            "ib_rejection_bear": False, "ib_score": 0.0}


# ══════════════════════════════════════════════════════════════════════
#  2. ADR (AVERAGE DAILY RANGE)
# ══════════════════════════════════════════════════════════════════════

def average_daily_range(df: pd.DataFrame, period: int = 14) -> dict:
    """
    ADR — Günlük ortalama hareket aralığı (ATR'dan farklı: gap dahil değil).

    Crypto 24/7 → gap yok, ATR ≈ ADR. Yine de günlük high-low kullanırız.

    Sinyal mantığı:
      • ADR_pct_used < 40% → gün daha erken, momentum devam edebilir
      • ADR_pct_used 40-70% → normal seans, tarafsız
      • ADR_pct_used > 80% → tükenme riski yüksek (TP yaklaştır / giriş geciktir)
      • ADR_pct_used > 100% → olağandışı volatilite günü (büyük haber / likidite avı)

    Döner:
        adr_value: günlük ortalama aralık (USDT)
        adr_pct:   ADR'ın son kapanışa oranı (%)
        today_range: bugünün range'i (high-low)
        adr_pct_used: bugünün range'in ADR'ın kaçı (%)
        adr_signal: "ROOM" / "NEUTRAL" / "EXHAUSTED"
        adr_score: float (−2 → +2)
    """
    daily = _resample_daily(df)
    if len(daily) < period + 2:
        return _empty_adr()

    daily["range"] = daily["high"] - daily["low"]
    adr_value = float(daily["range"].iloc[-(period + 1):-1].mean())

    # Bugünün hareketini hesapla (son 6 bar = 24 saat 4H bazında)
    today_bars = df.iloc[-6:]
    today_high = float(today_bars["high"].max())
    today_low  = float(today_bars["low"].min())
    today_range = today_high - today_low
    last_close  = float(df["close"].iloc[-1])

    adr_pct = (adr_value / last_close * 100) if last_close > 0 else 0
    adr_pct_used = (today_range / adr_value * 100) if adr_value > 0 else 0

    # ADR tamamlanma yüzdesi ve yön (nereye doğru hareket etti?)
    adr_direction = "NEUTRAL"
    if len(today_bars) >= 2:
        first_close = float(today_bars["close"].iloc[0])
        if last_close > first_close * 1.001:
            adr_direction = "UP"
        elif last_close < first_close * 0.999:
            adr_direction = "DOWN"

    # Kalan ADR potansiyeli
    adr_remaining = max(0, adr_value - today_range)
    adr_remaining_pct = (adr_remaining / adr_value * 100) if adr_value > 0 else 0

    # Sinyal
    if adr_pct_used < 40:
        adr_signal = "ROOM"
        adr_score  = 1.5
    elif adr_pct_used < 75:
        adr_signal = "NEUTRAL"
        adr_score  = 0.0
    elif adr_pct_used < 100:
        adr_signal = "EXHAUSTED"
        adr_score  = -1.0
    else:
        adr_signal = "OVEREXTENDED"
        adr_score  = -2.0

    return {
        "adr_value":       round(adr_value, 4),
        "adr_pct":         round(adr_pct, 2),
        "today_range":     round(today_range, 4),
        "adr_pct_used":    round(adr_pct_used, 1),
        "adr_remaining":   round(adr_remaining, 4),
        "adr_remaining_pct": round(adr_remaining_pct, 1),
        "adr_direction":   adr_direction,
        "adr_signal":      adr_signal,
        "adr_score":       round(adr_score, 2),
    }


def _empty_adr():
    return {"adr_value": 0, "adr_pct": 0, "today_range": 0, "adr_pct_used": 0,
            "adr_remaining": 0, "adr_remaining_pct": 0,
            "adr_direction": "NEUTRAL", "adr_signal": "NEUTRAL", "adr_score": 0.0}


# ══════════════════════════════════════════════════════════════════════
#  3. POC + SMC ÇAKIŞMASI (Confluence)
# ══════════════════════════════════════════════════════════════════════

def poc_smc_confluence(
    df: pd.DataFrame,
    bull_obs: list,
    bear_obs: list,
    bull_fvg: list,
    bear_fvg: list,
    tolerance_pct: float = 0.008,   # %0.8 tolerans
) -> dict:
    """
    POC (Point of Control) ile SMC bölgelerinin çakışması.

    POC = Hacim profili içinde en fazla hacim geçen fiyat seviyesi.
    Çakışma = POC ile OB veya FVG aynı bölgede → çok güçlü destek/direnç.

    Tolerans: fiyat seviyelerinin tolerans_pct içinde olması.

    Döner:
        poc_price: float
        poc_bull_ob_hit: bool (POC bull OB içinde)
        poc_bear_ob_hit: bool
        poc_bull_fvg_hit: bool
        poc_bear_fvg_hit: bool
        confluence_score: float (0–4)
        confluence_type: "STRONG_BULL" / "STRONG_BEAR" / "BULL" / "BEAR" / "NEUTRAL"
    """
    if len(df) < 50:
        return _empty_poc()

    # POC hesapla: fiyatı 200 dilime böl, en yüksek hacimli dilim
    price_min = float(df["low"].min())
    price_max = float(df["high"].max())
    if price_min >= price_max:
        return _empty_poc()

    bins = 200
    bin_size = (price_max - price_min) / bins
    if bin_size <= 0:
        return _empty_poc()

    volume_by_price = np.zeros(bins)
    for _, row in df.iterrows():
        lo = row["low"]; hi = row["high"]; vol = row["volume"]
        lo_bin = int((lo - price_min) / bin_size)
        hi_bin = int((hi - price_min) / bin_size)
        lo_bin = max(0, min(lo_bin, bins - 1))
        hi_bin = max(0, min(hi_bin, bins - 1))
        span = max(1, hi_bin - lo_bin + 1)
        for b in range(lo_bin, hi_bin + 1):
            volume_by_price[b] += vol / span

    poc_bin  = int(np.argmax(volume_by_price))
    poc_price = price_min + (poc_bin + 0.5) * bin_size

    def near(a, b):
        return abs(a - b) / max(abs(b), 1e-10) < tolerance_pct

    # OB çakışma kontrolü
    poc_bull_ob = any(near(poc_price, ob["mid"]) for ob in bull_obs)
    poc_bear_ob = any(near(poc_price, ob["mid"]) for ob in bear_obs)
    poc_bull_fvg = any(near(poc_price, fvg["mid"]) for fvg in bull_fvg)
    poc_bear_fvg = any(near(poc_price, fvg["mid"]) for fvg in bear_fvg)

    # Mevcut fiyatın POC'a göre konumu
    last_price = float(df["close"].iloc[-1])
    price_above_poc = last_price > poc_price * (1 + tolerance_pct)
    price_below_poc = last_price < poc_price * (1 - tolerance_pct)
    price_at_poc    = not price_above_poc and not price_below_poc

    # Confluence skoru
    score = 0.0
    if poc_bull_ob:   score += 2.5
    if poc_bull_fvg:  score += 1.5
    if poc_bear_ob:   score -= 2.5
    if poc_bear_fvg:  score -= 1.5

    # POC desteği: fiyat POC'un üstünde → boğa
    if price_above_poc: score += 0.5
    if price_below_poc: score -= 0.5

    if score >= 3:
        c_type = "STRONG_BULL"
    elif score >= 1:
        c_type = "BULL"
    elif score <= -3:
        c_type = "STRONG_BEAR"
    elif score <= -1:
        c_type = "BEAR"
    else:
        c_type = "NEUTRAL"

    return {
        "poc_price":       round(poc_price, 4),
        "poc_bull_ob":     poc_bull_ob,
        "poc_bear_ob":     poc_bear_ob,
        "poc_bull_fvg":    poc_bull_fvg,
        "poc_bear_fvg":    poc_bear_fvg,
        "price_above_poc": price_above_poc,
        "price_below_poc": price_below_poc,
        "price_at_poc":    price_at_poc,
        "confluence_score": round(score, 2),
        "confluence_type": c_type,
    }


def _empty_poc():
    return {"poc_price": 0, "poc_bull_ob": False, "poc_bear_ob": False,
            "poc_bull_fvg": False, "poc_bear_fvg": False,
            "price_above_poc": False, "price_below_poc": False, "price_at_poc": False,
            "confluence_score": 0.0, "confluence_type": "NEUTRAL"}


# ══════════════════════════════════════════════════════════════════════
#  4. OPEN INTEREST DELTA (Futures OI Analizi)
# ══════════════════════════════════════════════════════════════════════

def open_interest_signal(
    oi_series: Optional[list] = None,
    price_series: Optional[list] = None,
) -> dict:
    """
    Open Interest Delta sinyali.

    OI + Fiyat Matris:
      ↑OI + ↑Fiyat = Yeni long'lar giriyor → BULLISH (güçlü trend)
      ↑OI + ↓Fiyat = Yeni short'lar giriyor → BEARISH (güçlü trend)
      ↓OI + ↑Fiyat = Short'lar kapatılıyor → BULLISH (zayıf, daha az güvenilir)
      ↓OI + ↓Fiyat = Long'lar kapatılıyor → BEARISH (zayıf, daha az güvenilir)

    oi_series: Son N OI değerleri (USDT notional)
    price_series: Aynı dönem kapanış fiyatları
    """
    if not oi_series or not price_series or len(oi_series) < 3:
        return {"oi_trend": "UNKNOWN", "oi_score": 0.0,
                "oi_rising": False, "oi_divergence": False}

    oi = np.array(oi_series, dtype=float)
    px = np.array(price_series, dtype=float)

    # OI trend
    oi_change_pct = (oi[-1] - oi[0]) / max(abs(oi[0]), 1e-10) * 100
    px_change_pct = (px[-1] - px[0]) / max(abs(px[0]), 1e-10) * 100

    oi_rising = oi_change_pct > 1.0
    oi_falling = oi_change_pct < -1.0
    px_rising  = px_change_pct > 0.5
    px_falling = px_change_pct < -0.5

    # OI-Fiyat uyumsuzluğu (divergence): fiyat yukarı ama OI düşüyor
    oi_divergence = (px_rising and oi_falling) or (px_falling and oi_rising)

    score = 0.0
    oi_trend = "NEUTRAL"

    if oi_rising and px_rising:
        score = 3.0;    oi_trend = "BULL_STRONG"
    elif oi_rising and px_falling:
        score = -3.0;   oi_trend = "BEAR_STRONG"
    elif oi_falling and px_rising:
        score = 1.0;    oi_trend = "BULL_WEAK"
    elif oi_falling and px_falling:
        score = -1.0;   oi_trend = "BEAR_WEAK"

    # Divergence penaltisi
    if oi_divergence:
        score *= 0.5

    return {
        "oi_trend":        oi_trend,
        "oi_score":        round(score, 2),
        "oi_rising":       oi_rising,
        "oi_divergence":   oi_divergence,
        "oi_change_pct":   round(oi_change_pct, 2),
        "px_change_pct":   round(px_change_pct, 2),
    }


# ══════════════════════════════════════════════════════════════════════
#  5. FUNDING RATE SİGNALİ
# ══════════════════════════════════════════════════════════════════════

def funding_rate_signal(funding_rate: Optional[float]) -> dict:
    """
    Funding Rate kontrarian sinyali.

    Funding Rate Mantığı (Binance Perpetual Futures):
      Pozitif FR: Long'lar short'lara öder → piyasa 'aşırı long'.
                  Kontrarian: SHORT fırsatı (kalabalık zaten long, squeeze riski).
      Negatif FR: Short'lar long'lara öder → piyasa 'aşırı short'.
                  Kontrarian: LONG fırsatı (kalabalık zaten short, short squeeze).

    Eşikler (Binance 8 saatte bir):
      Normal:   -0.01% ile +0.01%
      Dikkat:   ±0.03–0.08% → orta derece aşırılık
      Aşırı:    > +0.10% veya < -0.05% → güçlü kontrarian sinyal

    Döner:
        fr_value: float, fr_signal: str, fr_score: float (−3 → +3)
        is_extreme: bool
    """
    if funding_rate is None:
        return {"fr_value": 0, "fr_signal": "UNKNOWN",
                "fr_score": 0.0, "is_extreme": False}

    fr = float(funding_rate)

    # Skorlama (kontrarian — crowd negatif ise LONG, pozitif ise SHORT)
    if fr < -0.0005:         # %−0.05: aşırı short → güçlü LONG sinyali
        score = 3.0;  signal = "EXTREME_NEGATIVE_→_LONG"
    elif fr < -0.0003:       # %−0.03
        score = 2.0;  signal = "NEGATIVE_→_LONG"
    elif fr < -0.0001:       # %−0.01
        score = 0.5;  signal = "SLIGHTLY_NEGATIVE"
    elif fr <= 0.0001:
        score = 0.0;  signal = "NEUTRAL"
    elif fr <= 0.0003:
        score = -0.5; signal = "SLIGHTLY_POSITIVE"
    elif fr <= 0.0008:       # %+0.08
        score = -2.0; signal = "POSITIVE_→_SHORT"
    else:                    # > %+0.10: aşırı long → güçlü SHORT sinyali
        score = -3.0; signal = "EXTREME_POSITIVE_→_SHORT"

    is_extreme = abs(fr) > 0.0005

    return {
        "fr_value":  fr,
        "fr_pct":    round(fr * 100, 4),
        "fr_signal": signal,
        "fr_score":  round(score, 2),
        "is_extreme": is_extreme,
    }


# ══════════════════════════════════════════════════════════════════════
#  6. SEANS ANALİZİ (Asia / London / NY)
# ══════════════════════════════════════════════════════════════════════

def session_analysis(df: pd.DataFrame) -> dict:
    """
    ICT Seans Teorisi:
      • Asia (00:00–08:00 UTC): Düşük hacim, likidite oluşumu, stop avı.
      • London (08:00–16:00 UTC): Yüksek hacim, yönü belirler, manipülasyon.
      • NY AM (13:00–17:00 UTC): Gerçek trend başlar, en güvenilir seans.
      • NY PM (17:00–21:00 UTC): Devam veya reversal.

    Özellikler:
      • London Kill Zone (08:00–10:00 UTC): SMC giriş kalitesi en yüksek.
      • NY Kill Zone (13:00–15:00 UTC): ICT optimal entry bölgesi.
      • Asia Range: London bu range'i aşarsa → gerçek hareket.

    4H bar için her bar UTC saatine göre seans etiketlenir.
    """
    if len(df) < 12:
        return {"current_session": "UNKNOWN", "session_score": 0.0}

    try:
        last_ts = df.index[-1]
        # UTC saat
        if hasattr(last_ts, "hour"):
            hour_utc = last_ts.hour
        else:
            hour_utc = 12  # bilinmiyorsa NY

        if 0 <= hour_utc < 8:
            current_session = "ASIA"
            session_score   = 0.5
        elif 8 <= hour_utc < 13:
            current_session = "LONDON"
            session_score   = 2.0  # En yüksek hareket
        elif 13 <= hour_utc < 17:
            current_session = "NY_AM"
            session_score   = 2.5  # En güvenilir yön
        elif 17 <= hour_utc < 21:
            current_session = "NY_PM"
            session_score   = 1.5
        else:
            current_session = "OFF_HOURS"
            session_score   = 0.3

        # Asia Range hesapla (son 2 bar ≈ 08:00'den öncesi)
        asia_bars = df.iloc[-6:-4]  # kabaca Asia saatleri
        asia_high = float(asia_bars["high"].max()) if len(asia_bars) > 0 else 0
        asia_low  = float(asia_bars["low"].min()) if len(asia_bars) > 0 else 0
        last_close = float(df["close"].iloc[-1])

        asia_range_break = "NONE"
        if asia_high > 0 and last_close > asia_high:
            asia_range_break = "BULL"
        elif asia_low > 0 and last_close < asia_low:
            asia_range_break = "BEAR"

        # London Kill Zone (08:00-10:00) veya NY Kill Zone (13:00-15:00) mu?
        in_kill_zone = (8 <= hour_utc <= 10) or (13 <= hour_utc <= 15)

        if in_kill_zone:
            session_score *= 1.3  # Kill zone'da sinyal daha değerli

        return {
            "current_session":  current_session,
            "session_score":    round(session_score, 2),
            "in_kill_zone":     in_kill_zone,
            "asia_high":        asia_high,
            "asia_low":         asia_low,
            "asia_range_break": asia_range_break,
            "hour_utc":         hour_utc,
        }
    except Exception as e:
        logger.debug(f"Session analiz hatası: {e}")
        return {"current_session": "UNKNOWN", "session_score": 1.0,
                "in_kill_zone": False, "asia_range_break": "NONE", "hour_utc": 12}


# ══════════════════════════════════════════════════════════════════════
#  7. VWAP + SAPMA BANTLARI
# ══════════════════════════════════════════════════════════════════════

def vwap_bands(df: pd.DataFrame, std_mult: float = 2.0) -> dict:
    """
    VWAP (Volume Weighted Average Price) ve ±1/±2 standart sapma bantları.

    Kullanım:
      • Fiyat VWAP üstünde → boğa yapısı (kurumlar net long)
      • Fiyat VWAP'ın +2σ üstünde → aşırı alım (TP noktası veya giriş için bekle)
      • Fiyat VWAP'ın −2σ altında → aşırı satım (long için potansiyel)
      • VWAP geri dönüşü → Mean reversion trade fırsatı

    4H bar için günlük kümülatif VWAP hesaplanır.
    """
    if len(df) < 10:
        return _empty_vwap()

    try:
        typical = (df["high"] + df["low"] + df["close"]) / 3
        vol = df["volume"]
        cum_vol = vol.cumsum()
        cum_tp_vol = (typical * vol).cumsum()
        vwap = cum_tp_vol / cum_vol.replace(0, np.nan)

        last_price = float(df["close"].iloc[-1])
        last_vwap  = float(vwap.iloc[-1])

        # Standart sapma
        deviation = (typical - vwap).abs()
        std_dev   = float(deviation.rolling(20).std().iloc[-1])

        upper1 = last_vwap + std_mult * std_dev
        lower1 = last_vwap - std_mult * std_dev
        upper2 = last_vwap + std_mult * 2 * std_dev
        lower2 = last_vwap - std_mult * 2 * std_dev

        above_vwap = last_price > last_vwap
        pct_from_vwap = (last_price - last_vwap) / last_vwap * 100

        # Bant konumu
        if last_price > upper2:
            band_position = "EXTREME_HIGH"
            vwap_score = -2.0
        elif last_price > upper1:
            band_position = "HIGH"
            vwap_score = -0.5
        elif last_price > last_vwap:
            band_position = "ABOVE"
            vwap_score = 1.0
        elif last_price > lower1:
            band_position = "BELOW"
            vwap_score = -0.5
        elif last_price > lower2:
            band_position = "LOW"
            vwap_score = 1.5  # Aşırı satım → reversal fırsatı
        else:
            band_position = "EXTREME_LOW"
            vwap_score = 2.5  # Çok aşırı satım → güçlü reversal

        return {
            "vwap":          round(last_vwap, 4),
            "upper1":        round(upper1, 4),
            "lower1":        round(lower1, 4),
            "upper2":        round(upper2, 4),
            "lower2":        round(lower2, 4),
            "above_vwap":    above_vwap,
            "pct_from_vwap": round(pct_from_vwap, 2),
            "band_position": band_position,
            "vwap_score":    round(vwap_score, 2),
            "std_dev":       round(std_dev, 4),
        }
    except Exception:
        return _empty_vwap()


def _empty_vwap():
    return {"vwap": 0, "upper1": 0, "lower1": 0, "upper2": 0, "lower2": 0,
            "above_vwap": False, "pct_from_vwap": 0,
            "band_position": "UNKNOWN", "vwap_score": 0.0, "std_dev": 0}


# ══════════════════════════════════════════════════════════════════════
#  8. GELİŞMİŞ WYCKOFF (Spring, UTAD, LPS, LPSY)
# ══════════════════════════════════════════════════════════════════════

def wyckoff_advanced(df: pd.DataFrame) -> dict:
    """
    Gelişmiş Wyckoff analizi.

    Temel Wyckoff yapıları:
      ACCUMULATION:
        SC  (Selling Climax)       → aşırı satım dip
        AR  (Automatic Rally)      → SC'den hızlı geri dönüş
        ST  (Secondary Test)       → SC seviyesine geri test
        Spring                     → ST'nin altını test edip geri dönme (en önemli)
        LPS (Last Point of Support)→ Spring'ten sonra yükselme, geri çekilme
        SOS (Sign of Strength)     → LPS'ten sonra güçlü kırılma

      DISTRIBUTION:
        PSY (Preliminary Supply)   → son yükseliş direnci
        BC  (Buying Climax)        → aşırı alım tepe
        AR  (Automatic Reaction)   → BC'den hızlı düşüş
        UTAD (Upthrust After Distribution) → BC üstünü test, hemen döner
        LPSY (Last Point of Supply)→ son direnç noktası
        SOW  (Sign of Weakness)    → kırılma aşağı

    Basitleştirilmiş tespit (tick bazlı hesaplama):
    """
    if len(df) < 50:
        return {"wyckoff_phase": "UNKNOWN", "wyckoff_score": 0.0,
                "spring_detected": False, "utad_detected": False}

    try:
        close = df["close"]
        volume = df["volume"]
        high   = df["high"]
        low    = df["low"]

        # Son 50 bar üzerinde analiz
        w = df.iloc[-50:]
        avg_vol = float(w["volume"].mean())
        avg_rng = float((w["high"] - w["low"]).mean())

        # Selling Climax / Spring tespit
        # Spring: Düşük hacimli gövde küçük düşüş (fiyat dibi test ediyor ama hacim yok)
        recent_low = float(w["low"].min())
        recent_hi  = float(w["high"].max())
        last_close = float(close.iloc[-1])
        last_vol   = float(volume.iloc[-1])
        last_range = float(high.iloc[-1] - low.iloc[-1])

        # Spring koşulları: son bar düşük vol + düşük range + fiyat dipten dönüyor
        spring_detected = (
            last_vol < avg_vol * 0.7 and
            last_range < avg_rng * 0.8 and
            float(low.iloc[-1]) <= recent_low * 1.01 and
            last_close > float(low.iloc[-1]) * 1.005
        )

        # UTAD: son bar yüksek vol + yüksek range + fiyat tepeden geri döndü
        utad_detected = (
            last_vol > avg_vol * 1.3 and
            last_range > avg_rng * 1.2 and
            float(high.iloc[-1]) >= recent_hi * 0.99 and
            last_close < float(high.iloc[-1]) * 0.995
        )

        # Genel Wyckoff fazı (basit)
        price_quartile = (last_close - recent_low) / max(recent_hi - recent_low, 1e-10)

        if spring_detected:
            wyckoff_phase  = "SPRING"
            wyckoff_score  = 3.5
        elif utad_detected:
            wyckoff_phase  = "UTAD"
            wyckoff_score  = -3.5
        elif price_quartile < 0.25:
            wyckoff_phase  = "ACCUMULATION_PHASE"
            wyckoff_score  = 2.0
        elif price_quartile < 0.40:
            wyckoff_phase  = "LPS_ZONE"
            wyckoff_score  = 1.5
        elif price_quartile > 0.75:
            wyckoff_phase  = "DISTRIBUTION_PHASE"
            wyckoff_score  = -2.0
        elif price_quartile > 0.60:
            wyckoff_phase  = "LPSY_ZONE"
            wyckoff_score  = -1.5
        else:
            wyckoff_phase  = "NEUTRAL"
            wyckoff_score  = 0.0

        # Volume climax kontrolü
        vol_climax = last_vol > avg_vol * 2.5
        if vol_climax and price_quartile < 0.3:
            wyckoff_phase = "SELLING_CLIMAX"
            wyckoff_score = 2.5
        elif vol_climax and price_quartile > 0.7:
            wyckoff_phase = "BUYING_CLIMAX"
            wyckoff_score = -2.5

        return {
            "wyckoff_phase":   wyckoff_phase,
            "wyckoff_score":   round(wyckoff_score, 2),
            "spring_detected": spring_detected,
            "utad_detected":   utad_detected,
            "vol_climax":      vol_climax,
            "price_quartile":  round(price_quartile, 3),
        }
    except Exception as e:
        logger.debug(f"Wyckoff analiz hatası: {e}")
        return {"wyckoff_phase": "UNKNOWN", "wyckoff_score": 0.0,
                "spring_detected": False, "utad_detected": False}


# ══════════════════════════════════════════════════════════════════════
#  9. GELİŞMİŞ SKOR BİRLEŞTİRME
# ══════════════════════════════════════════════════════════════════════

def advanced_composite_score(
    df:          pd.DataFrame,
    bull_obs:    list = None,
    bear_obs:    list = None,
    bull_fvg:    list = None,
    bear_fvg:    list = None,
    oi_series:   list = None,
    px_series:   list = None,
    funding_rate: float = None,
    direction:   str = "NEUTRAL",   # "BULLISH" / "BEARISH" / "NEUTRAL"
) -> dict:
    """
    Tüm gelişmiş indikatörleri birleştirir.

    MAX_SCORE = 14 (normaliz edilmeden)
    Döner: advanced_score (0-10), detaylar
    """
    bull_obs  = bull_obs  or []
    bear_obs  = bear_obs  or []
    bull_fvg  = bull_fvg  or []
    bear_fvg  = bear_fvg  or []

    # Tüm bileşenleri hesapla
    ib     = initial_balance(df)
    adr    = average_daily_range(df)
    poc    = poc_smc_confluence(df, bull_obs, bear_obs, bull_fvg, bear_fvg)
    oi_sig = open_interest_signal(oi_series, px_series)
    fr_sig = funding_rate_signal(funding_rate)
    sess   = session_analysis(df)
    vwap_b = vwap_bands(df)
    wyck_a = wyckoff_advanced(df)

    # Yön bazlı skor toplama
    # (+) bull sinyalleri, (−) bear sinyalleri
    raw_score = 0.0

    if direction == "BULLISH":
        raw_score += max(0, ib["ib_score"])        # IB bull katkısı
        raw_score += max(0, adr["adr_score"])      # ADR room (momentum var)
        raw_score += max(0, poc["confluence_score"])  # POC bull confluence
        raw_score += max(0, oi_sig["oi_score"])    # OI bull
        raw_score += max(0, fr_sig["fr_score"])    # Funding kontrarian (negatif FR → long)
        raw_score += max(0, wyck_a["wyckoff_score"])  # Spring / Accumulation
        # VWAP: aşırı satım veya VWAP üstü
        if vwap_b["band_position"] in ("EXTREME_LOW", "LOW"):
            raw_score += 2.0
        elif vwap_b["above_vwap"]:
            raw_score += 0.5

    elif direction == "BEARISH":
        raw_score += max(0, -ib["ib_score"])       # IB bear katkısı
        raw_score += max(0, adr["adr_score"])      # ADR room (bear tarafı da aynı)
        raw_score += max(0, -poc["confluence_score"])  # POC bear confluence
        raw_score += max(0, -oi_sig["oi_score"])   # OI bear
        raw_score += max(0, -fr_sig["fr_score"])   # Funding kontrarian (pozitif FR → short)
        raw_score += max(0, -wyck_a["wyckoff_score"])  # UTAD / Distribution
        if vwap_b["band_position"] in ("EXTREME_HIGH", "HIGH"):
            raw_score += 2.0
        elif not vwap_b["above_vwap"]:
            raw_score += 0.5

    # Session bonusu
    if direction != "NEUTRAL":
        raw_score *= (1.0 + sess["session_score"] * 0.05)

    # ADR tükenme CEZASI (yön ne olursa olsun)
    if adr["adr_signal"] == "EXHAUSTED":
        raw_score *= 0.75
    elif adr["adr_signal"] == "OVEREXTENDED":
        raw_score *= 0.50

    # Maksimum 10'a normalize
    MAX_RAW = 14.0
    adv_score = min(10.0, (raw_score / MAX_RAW) * 10)

    return {
        "advanced_score": round(adv_score, 2),
        "raw_score":      round(raw_score, 2),

        # Alt bileşenler
        "ib":      ib,
        "adr":     adr,
        "poc":     poc,
        "oi":      oi_sig,
        "fr":      fr_sig,
        "session": sess,
        "vwap":    vwap_b,
        "wyckoff": wyck_a,
    }


# ══════════════════════════════════════════════════════════════════════
#  10. OI + FUNDING VERİSİ ÇEKME (Binance ccxt)
# ══════════════════════════════════════════════════════════════════════

def fetch_oi_and_funding(symbol: str, limit: int = 10) -> tuple:
    """
    Binance Futures'tan Open Interest geçmişi ve Funding Rate çeker.
    Döner: (oi_list, px_list, funding_rate)
    API key gerekmez (public endpoint).
    """
    try:
        import ccxt
        exc = ccxt.binance({
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        })

        # Funding rate
        try:
            fr_data = exc.fetch_funding_rate(symbol)
            funding = fr_data.get("fundingRate", None)
        except Exception:
            funding = None

        # Open Interest History (son limit * 4H)
        try:
            # ccxt doesn't always have OI history natively, fallback to ticker
            ticker = exc.fetch_ticker(symbol)
            # Use mark price as proxy when OI unavailable
            oi_list = None
            px_list = None

            # Try fetch_open_interest_history if available
            if hasattr(exc, "fetch_open_interest_history"):
                oi_hist = exc.fetch_open_interest_history(
                    symbol, "4h", limit=limit
                )
                if oi_hist:
                    oi_list = [float(x.get("openInterest", 0)) for x in oi_hist]
                    px_list = [float(x.get("close", 0)) for x in oi_hist]
        except Exception:
            oi_list = None
            px_list = None

        return oi_list, px_list, funding

    except Exception as e:
        logger.debug(f"OI/Funding çekilemedi ({symbol}): {e}")
        return None, None, None
