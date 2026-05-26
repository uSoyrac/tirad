"""
market/deribit_fetcher.py — Deribit Opsiyon Piyasası Verisi
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
API key gerekmez. Tamamen public endpoint'ler:

  1. DVOL (Deribit Volatility Index) — kripto VIX'i
     BTC DVOL > 80 → panik → kontrarian long fırsatı
     BTC DVOL < 40 → rehavet → dikkatli ol

  2. 25-Delta Opsiyon Eğrisi (Skew)
     Put IV - Call IV
     Pozitif skew (put > call) → piyasa downside satın alıyor → korku
     Negatif skew (call > put) → piyasa upside talep ediyor → açgözlülük
     ICT yorumu: aşırı korku = kontrarian long, aşırı açgözlülük = short

  3. Put/Call Oranı (Open Interest bazlı)
     > 1.2 → çok fazla put pozisyonu = sürü korkusu → kontrarian bullish
     < 0.6 → çok fazla call = sürü açgözlülüğü → kontrarian bearish

  4. Max Pain Fiyatı
     Opsiyon yazarlarının (satıcıların) en az ödeme yapacağı fiyat.
     Expiry yaklaştıkça spot fiyat bu noktaya çekiliyor.
     Spot < Max Pain → yukarı baskı var

Neden edge?  Retail botların %99'u bu veriyi kullanmıyor.
Kurumsal para opsiyon piyasasında konumlanır,
futures piyasası gecikmeli olarak takip eder.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger("market.deribit")

_DERIBIT = "https://www.deribit.com/api/v2/public"
_TIMEOUT = 12


# ── Matematiksel yardımcılar (scipy gerekmez) ─────────────────────────

def _ncdf(x: float) -> float:
    """Standart normal CDF — math.erf ile (harici kütüphane yok)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _bs_delta(S: float, K: float, T: float, sigma: float, opt_type: str) -> float:
    """
    Black-Scholes delta hesabı.
    S: spot fiyat, K: kullanım fiyatı (strike)
    T: vadeye kalan süre (yıl cinsinden)
    sigma: implied volatility (ondalık, 0.80 = %80)
    opt_type: 'C' (call) veya 'P' (put)
    """
    if T <= 1e-6 or sigma <= 1e-6 or S <= 0 or K <= 0:
        return 0.5 if opt_type == "C" else -0.5
    try:
        d1 = (math.log(S / K) + 0.5 * sigma ** 2 * T) / (sigma * math.sqrt(T))
        return _ncdf(d1) if opt_type == "C" else _ncdf(d1) - 1.0
    except (ValueError, ZeroDivisionError):
        return 0.5 if opt_type == "C" else -0.5


def _parse_instrument(name: str) -> Optional[tuple]:
    """
    'BTC-27JUN25-100000-C' → (currency, expiry, strike, opt_type)
    Hata durumunda None döner.
    """
    parts = name.split("-")
    if len(parts) != 4:
        return None
    currency, expiry_str, strike_str, opt_type = parts
    if opt_type not in ("C", "P"):
        return None
    try:
        strike = float(strike_str)
        expiry = datetime.strptime(expiry_str, "%d%b%y").replace(
            hour=8, minute=0, second=0, tzinfo=timezone.utc
        )
        return currency, expiry, strike, opt_type
    except ValueError:
        return None


# ══════════════════════════════════════════════════════════════════════
#  1. DVOL — Deribit Volatilite İndeksi
# ══════════════════════════════════════════════════════════════════════

def fetch_dvol(currency: str = "BTC") -> Optional[float]:
    """
    DVOL'un son değerini çeker (son 1 saatlik veri).
    BTC DVOL: genellikle 40-150 arası. VIX gibi düşün.
    """
    try:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        r = requests.get(
            f"{_DERIBIT}/get_volatility_index_data",
            params={
                "currency":        currency.upper(),
                "start_timestamp": now_ms - 3_600_000,
                "end_timestamp":   now_ms,
                "resolution":      "60",
            },
            timeout=_TIMEOUT,
        )
        data = r.json().get("result", {}).get("data", [])
        if data:
            # Format: [timestamp, open, high, low, close]
            return float(data[-1][4])
    except Exception as e:
        logger.debug("DVOL fetch hatası %s: %s", currency, e)
    return None


# ══════════════════════════════════════════════════════════════════════
#  2. Opsiyon Özet Verisi
# ══════════════════════════════════════════════════════════════════════

def _fetch_book_summary(currency: str) -> list:
    """Tüm aktif opsiyon enstrümanlarının özet verisini çeker."""
    try:
        r = requests.get(
            f"{_DERIBIT}/get_book_summary_by_currency",
            params={"currency": currency.upper(), "kind": "option"},
            timeout=_TIMEOUT,
        )
        return r.json().get("result", [])
    except Exception as e:
        logger.debug("Book summary fetch hatası %s: %s", currency, e)
        return []


def _fetch_index_price(currency: str) -> Optional[float]:
    """Deribit index fiyatını çeker (BTC/ETH)."""
    try:
        r = requests.get(
            f"{_DERIBIT}/get_index_price",
            params={"index_name": f"{currency.lower()}_usd"},
            timeout=_TIMEOUT,
        )
        return float(r.json()["result"]["index_price"])
    except Exception as e:
        logger.debug("Index price fetch hatası %s: %s", currency, e)
        return None


# ══════════════════════════════════════════════════════════════════════
#  3. Ana Analiz
# ══════════════════════════════════════════════════════════════════════

def analyze_options(currency: str = "BTC") -> dict:
    """
    Deribit opsiyon piyasasını analiz eder.

    Returns:
        dvol:                  float | None  — Deribit Volatility Index
        skew_25d:              float  — Put25d IV - Call25d IV (puan cinsinden)
        put_call_ratio:        float  — OI bazlı put/call oranı
        max_pain:              float | None  — Max pain fiyatı
        max_pain_distance_pct: float  — Spot'un max pain'e uzaklığı (%)
        put25_iv:              float | None  — 25-delta put IV (%)
        call25_iv:             float | None  — 25-delta call IV (%)
        nearest_expiry:        str    — En yakın vade tarihi
        options_score:         float  — Confluence için -2..+2 skor
        available:             bool
    """
    _empty = {
        "dvol": None, "skew_25d": 0.0, "put_call_ratio": 1.0,
        "max_pain": None, "max_pain_distance_pct": 0.0,
        "put25_iv": None, "call25_iv": None, "nearest_expiry": None,
        "options_score": 0.0, "available": False,
    }

    summaries = _fetch_book_summary(currency)
    if not summaries:
        return _empty

    # Spot fiyat
    spot = _fetch_index_price(currency)
    if not spot:
        # Yedek: opsiyon verilerinden tahmin et
        prices = [s.get("underlying_price", 0) for s in summaries if s.get("underlying_price", 0) > 0]
        if prices:
            spot = float(sorted(prices)[len(prices) // 2])
    if not spot or spot <= 0:
        return _empty

    now = datetime.now(timezone.utc)

    # Opsiyonları parse et
    parsed = []
    for s in summaries:
        name = s.get("instrument_name", "")
        result = _parse_instrument(name)
        if not result:
            continue
        _, expiry, strike, opt_type = result
        if expiry <= now:
            continue

        T = (expiry - now).total_seconds() / (365.25 * 24 * 3600)
        iv_raw = s.get("mid_iv") or s.get("mark_iv") or 0.0
        if not iv_raw or iv_raw <= 0:
            continue
        iv = iv_raw / 100.0  # Ondalığa çevir

        parsed.append({
            "expiry": expiry, "strike": strike, "opt_type": opt_type,
            "T": T, "iv": iv,
            "oi": float(s.get("open_interest", 0) or 0),
        })

    if not parsed:
        return _empty

    # En yakın vade
    expiries = sorted(set(p["expiry"] for p in parsed))
    nearest  = expiries[0]
    near     = [p for p in parsed if p["expiry"] == nearest]

    # BS delta hesapla
    for opt in near:
        opt["delta"] = _bs_delta(spot, opt["strike"], opt["T"], opt["iv"], opt["opt_type"])

    puts  = [o for o in near if o["opt_type"] == "P"]
    calls = [o for o in near if o["opt_type"] == "C"]

    # ── 25-delta skew ────────────────────────────────────────────
    put25  = min(puts,  key=lambda o: abs(o["delta"] + 0.25)) if puts  else None
    call25 = min(calls, key=lambda o: abs(o["delta"] - 0.25)) if calls else None

    skew_25d  = 0.0
    put25_iv  = None
    call25_iv = None
    if put25 and call25:
        put25_iv  = round(put25["iv"]  * 100, 2)
        call25_iv = round(call25["iv"] * 100, 2)
        skew_25d  = round(put25_iv - call25_iv, 2)

    # ── Put/Call oranı (OI bazlı) ─────────────────────────────────
    put_oi  = sum(o["oi"] for o in near if o["opt_type"] == "P")
    call_oi = sum(o["oi"] for o in near if o["opt_type"] == "C")
    pc_ratio = round(put_oi / (call_oi + 1e-10), 3)

    # ── Max Pain ──────────────────────────────────────────────────
    strikes   = sorted(set(o["strike"] for o in near))
    call_oi_d = {o["strike"]: o["oi"] for o in near if o["opt_type"] == "C"}
    put_oi_d  = {o["strike"]: o["oi"] for o in near if o["opt_type"] == "P"}

    max_pain = None
    if strikes:
        pain = {}
        for K_test in strikes:
            c_loss = sum(oi * max(K_test - Ks, 0) for Ks, oi in call_oi_d.items())
            p_loss = sum(oi * max(Ks - K_test, 0) for Ks, oi in put_oi_d.items())
            pain[K_test] = c_loss + p_loss
        max_pain = min(pain, key=pain.get)

    mp_dist = round((max_pain - spot) / spot * 100, 2) if max_pain else 0.0

    # ── DVOL ──────────────────────────────────────────────────────
    dvol = fetch_dvol(currency)

    # ── Confluence Skoru (-2..+2) ─────────────────────────────────
    score = 0.0

    # Skew yorumu (kontrarian):
    # Yüksek pozitif skew = piyasa çok korkuyor = kontrarian bullish
    if skew_25d >= 15:     score += 1.5
    elif skew_25d >= 8:    score += 0.75
    elif skew_25d >= 2:    score += 0.25
    elif skew_25d >= -2:   score += 0.0
    elif skew_25d >= -8:   score -= 0.25
    else:                  score -= 0.75  # Aşırı açgözlülük

    # Put/Call oranı (kontrarian):
    if pc_ratio >= 1.5:    score += 1.0
    elif pc_ratio >= 1.15: score += 0.5
    elif pc_ratio <= 0.55: score -= 0.5
    elif pc_ratio <= 0.7:  score -= 0.25

    # DVOL (panik = fırsat):
    if dvol is not None:
        if dvol >= 100:    score += 1.0
        elif dvol >= 75:   score += 0.5
        elif dvol >= 55:   score += 0.25
        elif dvol <= 35:   score -= 0.25  # Aşırı rehavet

    # Max pain çekimi:
    # Spot < max pain → fiyat yukarı çekilecek (bullish baskı)
    if mp_dist > 8:        score -= 0.5   # Spot çok yukarıda, aşağı çekilir
    elif mp_dist < -8:     score += 0.5   # Spot çok aşağıda, yukarı çekilir

    score = max(-2.0, min(2.0, round(score, 2)))

    return {
        "dvol":                  dvol,
        "skew_25d":              skew_25d,
        "put_call_ratio":        pc_ratio,
        "max_pain":              max_pain,
        "max_pain_distance_pct": mp_dist,
        "put25_iv":              put25_iv,
        "call25_iv":             call25_iv,
        "nearest_expiry":        nearest.strftime("%Y-%m-%d"),
        "spot":                  spot,
        "options_score":         score,
        "available":             True,
    }


# ══════════════════════════════════════════════════════════════════════
#  4. Confluence Entegrasyon Noktası
# ══════════════════════════════════════════════════════════════════════

def fetch_deribit_score(symbol: str) -> dict:
    """
    Confluence için tek giriş noktası.
    symbol: 'BTC/USDT' veya 'ETH/USDT'

    Returns: analyze_options() sonucu veya boş dict (desteklenmeyen parite)
    """
    currency = symbol.split("/")[0].upper()
    if currency not in ("BTC", "ETH"):
        return {"options_score": 0.0, "available": False}
    try:
        return analyze_options(currency)
    except Exception as e:
        logger.debug("Deribit fetch_deribit_score hatası %s: %s", symbol, e)
        return {"options_score": 0.0, "available": False}
