"""Veri katmanı — OHLCV yükleme (stdlib çekirdek).

Motor list[Candle] ister. İki kaynak:
- load_csv(): csv modülü ile, ağ bağımsız.
- fetch_ohlcv(): ccxt (lazy import) — kurulu değilse/erişim yoksa yükseltir,
  çağıran "bu kaynak alınamadı" diyebilsin.

CSV başlığı şu sütunları içermeli: timestamp, open, high, low, close, volume.
"""

from __future__ import annotations

import csv
from typing import List, Sequence

from .types import Candle

REQUIRED = ["timestamp", "open", "high", "low", "close"]


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


def fetch_ohlcv(
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    limit: int = 500,
    exchange: str = "binance",
) -> List[Candle]:
    """Public OHLCV çek (anahtarsız). ccxt yoksa/erişim yoksa yükseltir."""
    import ccxt  # lazy: çekirdek ccxt'siz çalışsın

    ex_cls = getattr(ccxt, exchange, None)
    if ex_cls is None:
        raise ValueError(f"Bilinmeyen borsa: {exchange}")
    ex = ex_cls({"enableRateLimit": True})
    rows = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    return from_records(rows)
