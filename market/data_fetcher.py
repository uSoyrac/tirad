"""
Piyasa verisi çekme: Binance (kripto) + yfinance (BIST hisseleri)
Anti-repainting: Sadece kapanmış mumlar kullanılır
"""
import os
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import ccxt
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# Binance timeframe → ccxt karşılığı
CCXT_TF_MAP = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w",
}

# yfinance için interval → period karşılığı
YF_INTERVAL_MAP = {
    "1h": ("1h", "60d"),
    "4h": ("1h", "60d"),   # 4h için 1h çekip resample
    "1d": ("1d", "2y"),
    "1w": ("1wk", "5y"),
}


class BinanceFetcher:
    def __init__(self):
        self.exchange = ccxt.binance({
            "apiKey": os.getenv("BINANCE_API_KEY", ""),
            "secret": os.getenv("BINANCE_SECRET_KEY", ""),
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        })

    def fetch_ohlcv(self, symbol: str, timeframe: str = "4h", limit: int = 300) -> pd.DataFrame:
        """OHLCV verisi çeker. Son (açık) mumu KALDIRIR — anti-repainting."""
        tf = CCXT_TF_MAP.get(timeframe, timeframe)
        try:
            raw = self.exchange.fetch_ohlcv(symbol, tf, limit=limit + 1)
            df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            df.set_index("timestamp", inplace=True)
            df = df.iloc[:-1]  # Son açık mumu çıkar — anti-repainting garantisi
            return df.astype(float)
        except Exception as e:
            logger.error(f"OHLCV fetch error {symbol}/{timeframe}: {e}")
            return pd.DataFrame()

    def fetch_funding_rate(self, symbol: str) -> Optional[float]:
        try:
            data = self.exchange.fetch_funding_rate(symbol)
            return data.get("fundingRate")
        except Exception as e:
            logger.warning(f"Funding rate fetch error {symbol}: {e}")
            return None

    def fetch_open_interest(self, symbol: str) -> Optional[float]:
        try:
            data = self.exchange.fetch_open_interest(symbol)
            return data.get("openInterest") or data.get("openInterestValue")
        except Exception as e:
            logger.warning(f"Open interest fetch error {symbol}: {e}")
            return None

    def get_top_volume_symbols(self, n: int = 30) -> list[str]:
        """Binance'te hacme göre en yüksek N futures sembolü döndürür."""
        try:
            tickers = self.exchange.fetch_tickers()
            usdt_pairs = {
                k: v for k, v in tickers.items()
                if k.endswith("/USDT") and v.get("quoteVolume")
            }
            sorted_pairs = sorted(usdt_pairs.items(), key=lambda x: x[1]["quoteVolume"], reverse=True)
            return [s[0] for s in sorted_pairs[:n]]
        except Exception as e:
            logger.error(f"Top volume fetch error: {e}")
            return []


class BISTFetcher:
    """Borsa İstanbul hisse verisi — yfinance ile (.IS uzantısı)"""

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1d", limit: int = 300) -> pd.DataFrame:
        """BIST hisse verisi. Anti-repainting: sadece kapanmış seanslar."""
        interval_map = {
            "1h": "1h", "4h": "1h", "1d": "1d", "1w": "1wk",
        }
        interval = interval_map.get(timeframe, "1d")
        period = "60d" if interval == "1h" else "2y"

        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval, auto_adjust=True)
            if df.empty:
                logger.warning(f"BIST veri yok: {symbol}")
                return pd.DataFrame()

            df.index = pd.to_datetime(df.index, utc=True)
            df.columns = df.columns.str.lower()
            df = df[["open", "high", "low", "close", "volume"]].copy()

            # 4H için 1H veriyi resample et
            if timeframe == "4h" and interval == "1h":
                df = df.resample("4h").agg({
                    "open": "first", "high": "max",
                    "low": "min", "close": "last", "volume": "sum"
                }).dropna()

            # Son tamamlanmamış mumu çıkar
            now_utc = datetime.now(timezone.utc)
            if interval == "1d":
                df = df[df.index.date < now_utc.date()]
            else:
                df = df[df.index < now_utc - timedelta(minutes=5)]

            return df.tail(limit).astype(float)
        except Exception as e:
            logger.error(f"BIST fetch error {symbol}: {e}")
            return pd.DataFrame()

    def get_bist100_info(self) -> dict:
        """BIST 100 endeks son değeri"""
        try:
            xu100 = yf.Ticker("XU100.IS")
            info = xu100.fast_info
            return {
                "last_price": info.last_price,
                "day_change_pct": (info.last_price / info.previous_close - 1) * 100
                if info.previous_close else None,
            }
        except Exception as e:
            logger.warning(f"BIST100 info error: {e}")
            return {}


class MarketDataFetcher:
    """Birleşik veri çekici — hem kripto hem BIST"""

    def __init__(self):
        self.binance = BinanceFetcher()
        self.bist = BISTFetcher()

    def fetch(self, symbol: str, timeframe: str = "4h", limit: int = 300) -> pd.DataFrame:
        if symbol.endswith(".IS"):
            return self.bist.fetch_ohlcv(symbol, timeframe, limit)
        return self.binance.fetch_ohlcv(symbol, timeframe, limit)

    def fetch_crypto_extras(self, symbol: str) -> dict:
        return {
            "funding_rate": self.binance.fetch_funding_rate(symbol),
            "open_interest": self.binance.fetch_open_interest(symbol),
        }

    def get_top_crypto_by_volume(self, n: int = 20) -> list[str]:
        return self.binance.get_top_volume_symbols(n)
