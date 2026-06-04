#!/usr/bin/env python3
"""
Fetch Binance futures OI + top-trader long/short ratio history from
data.binance.vision (daily 5m metrics dumps) and aggregate to 4H bars.

Output: metricsdata/{COIN}_metrics_4h.csv
Columns: ts, oi, oi_value, toptrader_ls_ratio, ls_ratio, taker_buy_sell_ratio
  - oi / oi_value : bar-END value (last 5m sample in the 4H window)
  - *_ls_ratio / taker : bar MEAN over the 4H window

Aggregation: 5m -> 4H, UTC, bars labelled at window start (00,04,08,12,16,20).
Leak-free downstream: metric of a bar is fully observable at bar close.
"""
import io
import os
import sys
import time
import zipfile
import datetime as dt

import requests
import pandas as pd

BASE = "https://data.binance.vision/data/futures/um/daily/metrics"
OUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metricsdata")

COINS = "BTC ETH SOL BNB XRP ADA AVAX DOGE DOT LINK LTC UNI ATOM NEAR APT ARB OP FIL INJ ETC".split()

START = dt.date(2024, 6, 1)
END = dt.date(2026, 5, 30)  # latest published as of run

SESSION = requests.Session()


def daterange(a, b):
    d = a
    while d <= b:
        yield d
        d += dt.timedelta(days=1)


def fetch_day(symbol, day):
    """Return a DataFrame for one day, or None if missing (404)."""
    ds = day.isoformat()
    url = f"{BASE}/{symbol}/{symbol}-metrics-{ds}.zip"
    for attempt in range(3):
        try:
            r = SESSION.get(url, timeout=30)
        except Exception as e:
            if attempt == 2:
                print(f"  ERR {symbol} {ds}: {e}", file=sys.stderr)
                return None
            time.sleep(1.5)
            continue
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            if attempt == 2:
                print(f"  HTTP {r.status_code} {symbol} {ds}", file=sys.stderr)
                return None
            time.sleep(1.5)
            continue
        z = zipfile.ZipFile(io.BytesIO(r.content))
        df = pd.read_csv(z.open(z.namelist()[0]))
        return df
    return None


def aggregate_4h(df):
    """5m rows -> 4H bars. OI=last, ratios=mean. Bars labelled at window start."""
    df = df.copy()
    df["create_time"] = pd.to_datetime(df["create_time"], utc=True)
    df = df.sort_values("create_time").set_index("create_time")
    num = df.select_dtypes("number")
    # 4H windows aligned to 00:00 UTC, label = window start
    g = num.resample("4h", label="left", closed="left", origin="epoch")
    out = pd.DataFrame({
        "oi": g["sum_open_interest"].last(),
        "oi_value": g["sum_open_interest_value"].last(),
        "toptrader_ls_ratio": g["sum_toptrader_long_short_ratio"].mean(),
        "ls_ratio": g["count_long_short_ratio"].mean(),
        "taker_buy_sell_ratio": g["sum_taker_long_short_vol_ratio"].mean(),
    })
    out = out.dropna(how="all")
    return out


def run_coin(coin):
    symbol = f"{coin}USDT"
    frames = []
    n_days = 0
    first_day = None
    last_day = None
    for day in daterange(START, END):
        d = fetch_day(symbol, day)
        if d is None or len(d) == 0:
            continue
        frames.append(d)
        n_days += 1
        if first_day is None:
            first_day = day
        last_day = day
    if not frames:
        print(f"{coin}: NO DATA")
        return None
    raw = pd.concat(frames, ignore_index=True)
    agg = aggregate_4h(raw)
    agg.index.name = "ts"
    agg.index = agg.index.tz_convert(None)  # naive UTC to match mktdata
    path = os.path.join(OUTDIR, f"{coin}_metrics_4h.csv")
    agg.to_csv(path, float_format="%.6f")
    print(f"{coin}: days={n_days} 4h_bars={len(agg)} "
          f"range={agg.index[0]}..{agg.index[-1]} -> {path}")
    return agg


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    targets = COINS
    if len(sys.argv) > 1:
        targets = sys.argv[1:]
    for coin in targets:
        run_coin(coin)


if __name__ == "__main__":
    main()
