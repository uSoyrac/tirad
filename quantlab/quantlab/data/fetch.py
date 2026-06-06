"""Network OHLCV fetch via ccxt, paginated, written straight into the parquet cache.

Kept separate from cache.py so the rest of the system stays offline-safe: nothing
in a backtest run touches the network unless a script explicitly calls fetch_ohlcv.
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from . import cache

_TF_MS = {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}


def top_up(symbol: str, timeframe: str, *, cache_dir, seed_csv=None,
           exchange: str = "binance") -> "pd.DataFrame":
    """Incrementally extend the cached OHLCV to NOW via ccxt, then return the merged frame.

    The quantlab bots read a parquet cache that is frozen at the seed CSV's last bar
    (e.g. 2026-05-31) — so on a live server their 'as-of' never advances and they look
    stale. This tops the cache up: load cache (seeding from CSV if needed), fetch only the
    bars after the last cached timestamp, merge, save. Network-dependent; call from a live
    runner, never inside a backtest loop.
    """
    import ccxt

    base = cache.load_ohlcv(symbol, timeframe, cache_dir=cache_dir, seed_csv=seed_csv) \
        if (cache_dir and (Path(cache_dir) / f"{symbol.replace('/', '_')}_{timeframe}.parquet").exists()
            or seed_csv) else None
    last = base.index[-1] if base is not None and len(base) else None
    step = _TF_MS.get(timeframe)
    ex = getattr(ccxt, exchange)({"enableRateLimit": True})
    since = int((pd.Timestamp(last).timestamp() * 1000) + step) if last is not None else None
    rows: list[list[float]] = []
    cursor = since
    while True:
        batch = ex.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor, limit=1000)
        if not batch:
            break
        rows.extend(batch)
        cursor = batch[-1][0] + step
        if len(batch) < 1000:
            break
        time.sleep(ex.rateLimit / 1000)
    if rows:
        new = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
        new["ts"] = pd.to_datetime(new["ts"], unit="ms", utc=False)
        new = new.set_index("ts")
        merged = pd.concat([base, new]) if base is not None else new
        merged = cache._validate(merged)
        cache.save(merged, Path(cache_dir), symbol, timeframe)
        return merged
    return base


def fetch_ohlcv(
    symbol: str,
    timeframe: str,
    *,
    exchange: str = "binance",
    since=None,
    until=None,
    cache_dir: str | Path = "data_cache",
    limit: int = 1000,
) -> pd.DataFrame:
    """Fetch OHLCV from an exchange, paginating forward, and cache it as parquet.

    Returns the canonical OHLCV frame. Requires network + ccxt; call from scripts,
    not from inside a backtest loop.
    """
    import ccxt  # local import: keep import-time side effects out of the hot path

    ex = getattr(ccxt, exchange)({"enableRateLimit": True})
    since_ms = int(pd.Timestamp(since).timestamp() * 1000) if since is not None else None
    until_ms = int(pd.Timestamp(until).timestamp() * 1000) if until is not None else None
    step = _TF_MS.get(timeframe)
    if step is None:
        raise ValueError(f"unsupported timeframe: {timeframe}")

    rows: list[list[float]] = []
    cursor = since_ms
    while True:
        batch = ex.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor, limit=limit)
        if not batch:
            break
        rows.extend(batch)
        cursor = batch[-1][0] + step
        if until_ms is not None and cursor >= until_ms:
            break
        if len(batch) < limit:
            break
        time.sleep(ex.rateLimit / 1000)

    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df = df.drop_duplicates("ts")
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=False)
    df = df.set_index("ts")
    if until_ms is not None:
        df = df[df.index <= pd.Timestamp(until_ms, unit="ms")]
    cache.save(df, Path(cache_dir), symbol, timeframe)
    return df
