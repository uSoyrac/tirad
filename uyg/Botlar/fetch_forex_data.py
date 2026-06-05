import yfinance as yf
import pandas as pd
import os

PAIRS = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X"]

DIR_4H = "/Users/uygar/trade/uyg/src/mktdata_forex_4h"
DIR_1D = "/Users/uygar/trade/uyg/src/mktdata_forex_1d"
os.makedirs(DIR_4H, exist_ok=True)
os.makedirs(DIR_1D, exist_ok=True)

for pair in PAIRS:
    print(f"Fetching {pair}...")
    
    # Fetch 4H equivalent (fetch 1h up to 730 days and resample to 4h)
    df = yf.Ticker(pair).history(period="730d", interval="1h", auto_adjust=True)
    if not df.empty:
        df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
        df.columns = df.columns.str.lower()
        df = df[["open", "high", "low", "close", "volume"]]
        
        # 4H
        df_4h = df.resample("4h").agg({"open":"first", "high":"max", "low":"min", "close":"last", "volume":"sum"}).dropna()
        df_4h.index.name = "ts"
        df_4h.to_csv(f"{DIR_4H}/{pair}.csv")
        
        # 1D
        df_1d = df.resample("1D").agg({"open":"first", "high":"max", "low":"min", "close":"last", "volume":"sum"}).dropna()
        df_1d.index.name = "ts"
        df_1d.to_csv(f"{DIR_1D}/{pair}.csv")

print("Done fetching.")
