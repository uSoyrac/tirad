"""
market/coinglass_fetcher.py — Ücretsiz Likidite & Sentiment Verisi
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
API key gerekmez. Tamamen public endpoint'ler:

  Kaynak 1 — Binance Forced Orders (fapi/v1/allForceOrders)
    Son N zorla tasfiye emrini çeker. Long/Short tasfiye oranını hesaplar.
    → Çok fazla long tasfiyesi: bearish baskı altında.
    → Çok fazla short tasfiyesi: short squeeze potansiyeli (bullish).

  Kaynak 2 — Alternative.me Fear & Greed Index
    0-100 arası kripto piyasası duygu göstergesi.
    0-25 → Aşırı Korku (kontrarian: alım fırsatı)
    75-100 → Aşırı Açgözlülük (kontrarian: dikkatli ol)
    → ICT konsepti: kalabalık hep yanılır.

  Kaynak 3 — Binance Top Trader Long/Short (zaten data_fetcher'da)
    Ek kaynak olarak burada da kullanılabilir.
"""

from __future__ import annotations

import logging
from typing import Optional

import requests

logger = logging.getLogger("market.coinglass")

_BINANCE_FAPI = "https://fapi.binance.com"
_FNG_URL = "https://api.alternative.me/fng/"

_SYMBOL_MAP = {
    "BTC/USDT": "BTCUSDT", "ETH/USDT": "ETHUSDT", "SOL/USDT": "SOLUSDT",
    "BNB/USDT": "BNBUSDT", "AVAX/USDT": "AVAXUSDT", "LINK/USDT": "LINKUSDT",
    "DOT/USDT": "DOTUSDT", "XRP/USDT": "XRPUSDT", "DOGE/USDT": "DOGEUSDT",
    "ADA/USDT": "ADAUSDT", "ARB/USDT": "ARBUSDT",
}


def _sym(symbol: str) -> str:
    return _SYMBOL_MAP.get(symbol, symbol.replace("/", ""))


# ══════════════════════════════════════════════════════════════════════
#  1. BİNANCE FORCED ORDERS — LİKİDASYON ANALİZİ
#     Public endpoint: API key gerekmez.
# ══════════════════════════════════════════════════════════════════════

def fetch_liquidation_history(symbol: str, limit: int = 100) -> dict:
    """
    Son forced (likide) emirleri çekip long/short dağılımını hesaplar.

    Binance endpoint: GET /fapi/v1/allForceOrders
    Tamamen public — API key gerekmez.

    Returns:
        long_liq_usd:   Son N emir içindeki LONG tasfiye toplamı (USD)
        short_liq_usd:  SHORT tasfiye toplamı
        liq_ratio:      long/short oranı (>1.5 → fazla long tasfiye = bearish baskı)
        dominant_side:  "LONG" | "SHORT" | "NEUTRAL"
        liq_score:      -2.0..+2.0 (confluence için)
        order_count:    Çekilen emir sayısı
    """
    empty = {
        "long_liq_usd": 0.0, "short_liq_usd": 0.0,
        "liq_ratio": 1.0, "dominant_side": "NEUTRAL",
        "liq_score": 0.0, "order_count": 0,
    }

    try:
        url = _BINANCE_FAPI + "/fapi/v1/allForceOrders"
        r = requests.get(url, params={"symbol": _sym(symbol), "limit": limit}, timeout=10)
        if r.status_code != 200:
            logger.debug("allForceOrders %s HTTP %s", symbol, r.status_code)
            return empty

        orders = r.json()
        if not isinstance(orders, list) or not orders:
            return empty

        long_usd = 0.0
        short_usd = 0.0

        for o in orders:
            qty = float(o.get("origQty", 0) or 0)
            price = float(o.get("averagePrice", 0) or o.get("price", 0) or 0)
            usd = qty * price
            side = o.get("side", "")
            # Forced SELL = long pozisyon tasfiyesi
            # Forced BUY  = short pozisyon tasfiyesi
            if side == "SELL":
                long_usd += usd
            elif side == "BUY":
                short_usd += usd

        if long_usd + short_usd == 0:
            return empty

        ratio = round(long_usd / short_usd, 3) if short_usd > 0 else 9.9

        if ratio >= 2.5:
            dominant = "LONG"; score = -2.0   # Aşırı long tasfiyesi → bearish
        elif ratio >= 1.5:
            dominant = "LONG"; score = -1.0
        elif ratio <= 0.4:
            dominant = "SHORT"; score = 2.0   # Short squeeze → bullish
        elif ratio <= 0.67:
            dominant = "SHORT"; score = 1.0
        else:
            dominant = "NEUTRAL"; score = 0.0

        return {
            "long_liq_usd": round(long_usd, 0),
            "short_liq_usd": round(short_usd, 0),
            "liq_ratio": ratio,
            "dominant_side": dominant,
            "liq_score": score,
            "order_count": len(orders),
        }

    except Exception as e:
        logger.debug("Liquidation fetch hatası %s: %s", symbol, e)
        return empty


# ══════════════════════════════════════════════════════════════════════
#  2. FEAR & GREED INDEX
#     alternative.me — API key gerekmez, tamamen ücretsiz.
# ══════════════════════════════════════════════════════════════════════

def fetch_fear_greed(limit: int = 3) -> dict:
    """
    Kripto Fear & Greed Index — 0 (aşırı korku) → 100 (aşırı açgözlülük).

    ICT/SMC yorum:
      0-25  Aşırı Korku   → kontrarian LONG fırsatı
      25-45 Korku         → hafif bullish önyargı
      45-55 Nötr          → sinyal yok
      55-75 Açgözlülük    → hafif dikkat
      75-100 Aşırı Açgözlülük → kontrarian SHORT fırsatı / TP yak

    Returns:
        value: int (0-100)
        label: str ("Extreme Fear" vb.)
        fng_score: float -2.0..+2.0 (confluence için)
        trend_3d: "IMPROVING" | "WORSENING" | "STABLE"
        values_3d: list[int]
    """
    empty = {
        "value": 50, "label": "Neutral",
        "fng_score": 0.0, "trend_3d": "STABLE", "values_3d": [],
    }

    try:
        r = requests.get(_FNG_URL, params={"limit": limit}, timeout=8)
        if r.status_code != 200:
            return empty

        data = r.json().get("data", [])
        if not data:
            return empty

        values = [int(d["value"]) for d in data]
        latest = values[0]
        label = data[0].get("value_classification", "Neutral")

        # Skor: kontrarian mantık
        if latest <= 15:
            score = 2.0    # Aşırı korku = çok bullish fırsat
        elif latest <= 25:
            score = 1.5
        elif latest <= 40:
            score = 0.75
        elif latest <= 55:
            score = 0.0    # Nötr
        elif latest <= 70:
            score = -0.5
        elif latest <= 85:
            score = -1.0
        else:
            score = -1.5   # Aşırı açgözlülük = dikkat

        # 3 günlük trend
        if len(values) >= 2:
            delta = values[0] - values[-1]
            if delta > 5:
                trend = "WORSENING"   # Açgözlülüğe doğru gidiyor
            elif delta < -5:
                trend = "IMPROVING"   # Korkudan çıkıyor (bullish)
            else:
                trend = "STABLE"
        else:
            trend = "STABLE"

        return {
            "value": latest,
            "label": label,
            "fng_score": round(score, 2),
            "trend_3d": trend,
            "values_3d": values,
        }

    except Exception as e:
        logger.debug("Fear&Greed fetch hatası: %s", e)
        return empty


# ══════════════════════════════════════════════════════════════════════
#  3. TAM ANALİZ (tek çağrı — confluence ile uyumlu arayüz)
# ══════════════════════════════════════════════════════════════════════

def fetch_coinglass_data(symbol: str) -> dict:
    """
    Tüm ücretsiz likidite & sentiment verilerini tek seferinde çeker.

    Confluence'a geçilecek `liq_score`:
      liq (forced orders) + fng (fear&greed) ağırlıklı kombinasyonu.

    Returns:
        liquidation: dict   (Binance forced orders analizi)
        fear_greed:  dict   (Alternative.me F&G)
        available:   bool   (her zaman True — API key gerekmez)
        liq_score:   float  (-2..+2)
    """
    liq = fetch_liquidation_history(symbol)
    fng = fetch_fear_greed(limit=3)

    # Birleşik skor: %60 forced orders + %40 fear&greed
    combined = round(
        liq.get("liq_score", 0.0) * 0.60 +
        fng.get("fng_score", 0.0) * 0.40,
        2,
    )
    combined = max(-2.0, min(2.0, combined))

    return {
        "liquidation": liq,
        "fear_greed": fng,
        "heatmap": {},       # CoinGlass gerektiriyor, şimdilik boş
        "oi_summary": {},
        "available": True,   # API key olmadan da çalışır
        "liq_score": combined,
    }
