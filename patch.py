import re

with open('backtest_forex.py', 'r') as f:
    content = f.read()

content = content.replace('import pandas as pd', 'import pandas as pd\nimport yfinance as yf')

old_symbols = 'SYMBOLS    = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT",\n              "AVAX/USDT", "LINK/USDT", "DOT/USDT", "XRP/USDT"]'
new_symbols = 'SYMBOLS    = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "USDCHF=X", "NZDUSD=X"]'
content = content.replace(old_symbols, new_symbols)

content = content.replace('MIN_SCORE  = 4.5', 'MIN_SCORE  = 4.0')
content = content.replace('COMMISSION = 0.0004', 'COMMISSION = 0.0')
content = content.replace('SLIPPAGE   = 0.0005', 'SLIPPAGE   = 0.0001')

vol_ok_orig = 'def _vol_ok(df_slice: pd.DataFrame) -> bool:\n    """Giriş barının hacmi 20-bar ortalamasının üzerinde mi?"""\n    try:\n        v = df_slice["volume"]\n        avg = float(v.iloc[-21:-1].mean())\n        cur = float(v.iloc[-1])\n        return avg > 0 and cur >= avg * VOL_MULT\n    except Exception:\n        return True  # Hata = filtre atla'
vol_ok_new = 'def _vol_ok(df_slice: pd.DataFrame) -> bool:\n    """Forex for yfinance has 0 volume, bypass"""\n    return True'
content = content.replace(vol_ok_orig, vol_ok_new)

content = content.replace('df = ohlcv(sym, TIMEFRAME, BARS)', 'df = forex_ohlcv(sym, TIMEFRAME, BARS)')
content = content.replace('.replace("/USDT", "")', '.replace("=X", "")')

forex_ohlcv = """
def forex_ohlcv(sym, tf="4h", lim=2500):
    try:
        # fetch up to 730 days of 1h data to get max history
        df = yf.Ticker(sym).history(period="730d", interval="1h", auto_adjust=True)
        if df.empty: return pd.DataFrame()
        df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
        df.columns = df.columns.str.lower()
        df = df[["open", "high", "low", "close", "volume"]]
        if tf == "4h":
            df = df.resample("4h").agg({"open":"first", "high":"max", "low":"min", "close":"last", "volume":"sum"}).dropna()
        return df.iloc[:-1].astype(float)
    except Exception as e:
        print(f"Error fetching {sym}: {e}")
        return pd.DataFrame()

# ═══════════════════════════════════════════════════════════════════════
"""

content = content.replace('# ═══════════════════════════════════════════════════════════════════════\n#  ANA ÇALIŞMA', forex_ohlcv + '# ═══════════════════════════════════════════════════════════════════════\n#  ANA ÇALIŞMA')

with open('backtest_forex.py', 'w') as f:
    f.write(content)
