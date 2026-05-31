"""Veri katmanı — OHLCV yükleme (stdlib çekirdek).

Motor list[Candle] ister. Kaynaklar:
- load_csv(): csv modülü ile, ağ bağımsız.
- fetch_binance(): stdlib urllib ile Binance public klines (ccxt GEREKMEZ).
- fetch_ohlcv(): genel giriş — Binance için stdlib yolu, diğer borsalar için
  ccxt (lazy import). Erişim yoksa yükseltir; çağıran "kaynak alınamadı" der.

CSV başlığı şu sütunları içermeli: timestamp, open, high, low, close, volume.
"""

from __future__ import annotations

import csv
import json
import urllib.request
from typing import Callable, List, Optional, Sequence

from .types import Candle

REQUIRED = ["timestamp", "open", "high", "low", "close"]

# Binance klines için zaman dilimi -> API interval
_BINANCE_INTERVALS = {
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w", "1M",
}

HttpGet = Callable[[str], str]


def _default_http_get(url: str, timeout: float = 10.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode()


def from_records(rows: Sequence[Sequence]) -> List[Candle]:
    """ccxt formatı [[ts,o,h,l,c,v], ...] -> list[Candle]."""
    out: List[Candle] = []
    for r in rows:
        ts = int(r[0])
        o, h, l, c = float(r[1]), float(r[2]), float(r[3]), float(r[4])
        v = float(r[5]) if len(r) > 5 and r[5] is not None else 0.0
        out.append(Candle(ts=ts, open=o, high=h, low=l, close=c, volume=v))
    if not out:
        raise ValueError("OHLCV boş.")
    return out


def load_csv(path: str) -> List[Candle]:
    out: List[Candle] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        missing = [c for c in REQUIRED if c not in cols]
        if missing:
            raise ValueError(f"CSV eksik sütun(lar): {missing}")
        for row in reader:
            try:
                out.append(Candle(
                    ts=int(float(row["timestamp"])),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume") or 0.0),
                ))
            except (TypeError, ValueError):
                continue  # bozuk satırı atla
    if not out:
        raise ValueError("CSV boş veya tüm satırlar geçersiz.")
    return out


def _to_binance_symbol(symbol: str) -> str:
    """'BTC/USDT' -> 'BTCUSDT'."""
    return symbol.replace("/", "").replace("-", "").upper()


def fetch_binance(
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    limit: int = 500,
    http_get: Optional[HttpGet] = None,
    base: str = "https://api.binance.com",
) -> List[Candle]:
    """Binance public klines'ı SADECE stdlib ile çek (anahtarsız, ccxt yok).

    http_get enjekte edilebilir → ağsız test edilebilir. Ağ erişimi yoksa
    altta urllib hatası yükselir; çağıran "kaynak alınamadı" diyebilsin.
    """
    if timeframe not in _BINANCE_INTERVALS:
        raise ValueError(f"Binance desteklemeyen interval: {timeframe}")
    get = http_get or _default_http_get
    url = (f"{base}/api/v3/klines?symbol={_to_binance_symbol(symbol)}"
           f"&interval={timeframe}&limit={int(limit)}")
    raw = json.loads(get(url))
    # klines: [openTime, open, high, low, close, volume, closeTime, ...]
    rows = [[k[0], k[1], k[2], k[3], k[4], k[5]] for k in raw]
    return from_records(rows)


def fetch_ohlcv(
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    limit: int = 500,
    exchange: str = "binance",
) -> List[Candle]:
    """Public OHLCV çek (anahtarsız).

    Binance: stdlib urllib yolu (ccxt gerekmez). Diğer borsalar: ccxt (lazy).
    Erişim yoksa yükseltir.
    """
    if exchange == "binance":
        return fetch_binance(symbol, timeframe, limit)

    import ccxt  # lazy: çekirdek ccxt'siz çalışsın

    ex_cls = getattr(ccxt, exchange, None)
    if ex_cls is None:
        raise ValueError(f"Bilinmeyen borsa: {exchange}")
    ex = ex_cls({"enableRateLimit": True})
    rows = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    return from_records(rows)
