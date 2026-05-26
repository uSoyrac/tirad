"""
Multi-timeframe veri hazırlama: 1W / 1D / 4H / 1H
Her TF için kapanmış mumlar garanti edilir.
"""
import logging
from dataclasses import dataclass

import pandas as pd

from market.data_fetcher import MarketDataFetcher

logger = logging.getLogger(__name__)

TIMEFRAMES = ["1w", "1d", "4h", "1h"]
TF_LABELS = {"1w": "Weekly", "1d": "Daily", "4h": "4H", "1h": "1H"}


@dataclass
class MultiTFData:
    symbol: str
    weekly: pd.DataFrame
    daily: pd.DataFrame
    h4: pd.DataFrame
    h1: pd.DataFrame
    extras: dict  # funding_rate, open_interest vs.

    def get(self, tf: str) -> pd.DataFrame:
        return {
            "1w": self.weekly, "1d": self.daily,
            "4h": self.h4, "1h": self.h1,
        }.get(tf, pd.DataFrame())

    def is_complete(self) -> bool:
        return all([
            not self.weekly.empty, not self.daily.empty,
            not self.h4.empty, not self.h1.empty,
        ])


def build_multi_tf(symbol: str, fetcher: MarketDataFetcher) -> MultiTFData:
    """Tüm timeframe'ler için veri çeker ve MultiTFData döndürür."""
    logger.info(f"Building multi-TF data for {symbol}")

    is_bist = symbol.endswith(".IS")
    extras = {}
    if not is_bist:
        extras = fetcher.fetch_crypto_extras(symbol)

    weekly = fetcher.fetch(symbol, "1w", limit=100)
    daily = fetcher.fetch(symbol, "1d", limit=300)
    h4 = fetcher.fetch(symbol, "4h", limit=300)
    h1 = fetcher.fetch(symbol, "1h", limit=200)

    data = MultiTFData(
        symbol=symbol,
        weekly=weekly,
        daily=daily,
        h4=h4,
        h1=h1,
        extras=extras,
    )

    if not data.is_complete():
        missing = [tf for tf in TIMEFRAMES if data.get(tf).empty]
        logger.warning(f"{symbol}: Eksik TF verisi: {missing}")

    return data
