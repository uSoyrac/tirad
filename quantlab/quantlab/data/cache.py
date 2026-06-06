"""Parquet-backed OHLCV cache.

Canonical in-memory shape for every OHLCV frame in this project:
    - index: tz-naive UTC DatetimeIndex named "ts", strictly increasing, unique
    - columns: open, high, low, close, volume (float64)

Loading order for a (symbol, timeframe): parquet cache -> seed CSV -> ccxt fetch.
Resampling to a higher timeframe is done here so the higher-TF agent always sees
exactly the same source bars as the primary TF.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

OHLCV_COLS = ["open", "high", "low", "close", "volume"]
_TF_TO_PANDAS = {"1h": "1h", "4h": "4h", "1d": "1D", "1w": "1W"}


def _validate(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in OHLCV_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"OHLCV frame missing columns: {missing}")
    df = df[OHLCV_COLS].astype("float64")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("OHLCV frame must have a DatetimeIndex")
    df = df[~df.index.duplicated(keep="last")].sort_index()
    if not df.index.is_monotonic_increasing:
        raise ValueError("OHLCV index must be monotonic increasing")
    df.index.name = "ts"
    return df


def read_csv_ohlcv(path: str | Path) -> pd.DataFrame:
    """Read a seed CSV with schema: ts,open,high,low,close,volume."""
    df = pd.read_csv(path)
    df["ts"] = pd.to_datetime(df["ts"], utc=False)
    return _validate(df.set_index("ts"))


def _cache_path(cache_dir: Path, symbol: str, timeframe: str) -> Path:
    safe = symbol.replace("/", "_")
    return Path(cache_dir) / f"{safe}_{timeframe}.parquet"


def save(df: pd.DataFrame, cache_dir: Path, symbol: str, timeframe: str) -> Path:
    path = _cache_path(cache_dir, symbol, timeframe)
    path.parent.mkdir(parents=True, exist_ok=True)
    _validate(df).to_parquet(path)
    return path


def resample(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Resample base bars up to a higher timeframe (right-labelled, closed-left).

    No look-ahead: a higher-TF bar is only complete after its window closes;
    consumers must shift before using it at decision time.
    """
    rule = _TF_TO_PANDAS.get(timeframe)
    if rule is None:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    out = df.resample(rule, label="left", closed="left").agg(agg).dropna(how="any")
    return _validate(out)


def load_ohlcv(
    symbol: str,
    timeframe: str,
    *,
    cache_dir: str | Path,
    start=None,
    end=None,
    seed_csv: str | Path | None = None,
    base_timeframe: str = "4h",
) -> pd.DataFrame:
    """Return OHLCV for (symbol, timeframe), reading cache -> seed CSV (-> resample).

    Network fetch lives in fetch.py and is called explicitly by scripts; this
    function stays offline-safe so tests and reruns never hit an exchange.
    """
    cache_dir = Path(cache_dir)
    path = _cache_path(cache_dir, symbol, timeframe)
    if path.exists():
        df = _validate(pd.read_parquet(path))
    elif seed_csv is not None:
        base = read_csv_ohlcv(seed_csv)
        save(base, cache_dir, symbol, base_timeframe)
        df = base if timeframe == base_timeframe else resample(base, timeframe)
        if timeframe != base_timeframe:
            save(df, cache_dir, symbol, timeframe)
    else:
        raise FileNotFoundError(
            f"No cache at {path} and no seed_csv given. Run fetch first or set seed_csv."
        )

    if start is not None:
        df = df[df.index >= pd.Timestamp(start)]
    if end is not None:
        # inclusive of the end date
        df = df[df.index <= pd.Timestamp(end) + pd.Timedelta(days=1)]
    return df
