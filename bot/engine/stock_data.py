import yfinance as yf
import pandas as pd
import logging

logger = logging.getLogger("stock_data")

def fetch_stock_data(symbol: str, interval: str = "60m", period: str = "60d") -> pd.DataFrame:
    """
    yfinance üzerinden US Stock (Hisse) veya Forex verilerini çeker.
    SignalEngine ile uyumlu olması için sütunları ve indexi formatlar.
    
    Örn: symbol="AAPL", interval="60m"
    """
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()

        # UTC formatına veya naive timezone'a çevir (SignalEngine ile uyum için)
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df.columns = df.columns.str.lower()
        
        # Sadece gerekli sütunlar
        df = df[["open", "high", "low", "close", "volume"]].dropna()
        
        # DataFrame float tipinde olmalı
        return df.astype(float)
    except Exception as e:
        logger.warning(f"Hisse veri çekme hatası ({symbol}): {e}")
        return pd.DataFrame()
