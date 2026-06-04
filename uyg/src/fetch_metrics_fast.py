#!/usr/bin/env python3
"""Fast concurrent fetch of Binance futures OI + top-trader LS metrics
from data.binance.vision daily dumps, aggregated to 4H bars.
Same output schema as fetch_metrics.py but parallelized per-day per-coin."""
import io, os, sys, zipfile, datetime as dt, warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import pandas as pd
warnings.filterwarnings("ignore")

BASE = "https://data.binance.vision/data/futures/um/daily/metrics"
OUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metricsdata")
COINS = "BTC ETH SOL BNB XRP ADA AVAX DOGE DOT LINK LTC UNI ATOM NEAR APT ARB OP FIL INJ ETC".split()
START = dt.date(2024, 6, 1)
END = dt.date(2026, 5, 29)

def daterange(a, b):
    d = a
    while d <= b:
        yield d
        d += dt.timedelta(days=1)

def fetch_day(symbol, day, sess):
    ds = day.isoformat()
    url = f"{BASE}/{symbol}/{symbol}-metrics-{ds}.zip"
    try:
        r = sess.get(url, timeout=30)
    except Exception:
        return None
    if r.status_code != 200:
        return None
    try:
        z = zipfile.ZipFile(io.BytesIO(r.content))
        return pd.read_csv(z.open(z.namelist()[0]))
    except Exception:
        return None

def aggregate_4h(df):
    df = df.copy()
    df["create_time"] = pd.to_datetime(df["create_time"], utc=True)
    df = df.sort_values("create_time").set_index("create_time")
    num = df.select_dtypes("number")
    g = num.resample("4h", label="left", closed="left", origin="epoch")
    out = pd.DataFrame({
        "oi": g["sum_open_interest"].last(),
        "oi_value": g["sum_open_interest_value"].last(),
        "toptrader_ls_ratio": g["sum_toptrader_long_short_ratio"].mean(),
        "ls_ratio": g["count_long_short_ratio"].mean(),
        "taker_buy_sell_ratio": g["sum_taker_long_short_vol_ratio"].mean(),
    })
    return out.dropna(how="all")

def run_coin(coin):
    symbol = f"{coin}USDT"
    days = list(daterange(START, END))
    sess = requests.Session()
    frames = {}
    with ThreadPoolExecutor(max_workers=16) as ex:
        futs = {ex.submit(fetch_day, symbol, d, sess): d for d in days}
        for f in as_completed(futs):
            d = futs[f]
            res = f.result()
            if res is not None and len(res):
                frames[d] = res
    if not frames:
        print(f"{coin}: NO DATA", flush=True)
        return
    raw = pd.concat([frames[k] for k in sorted(frames)], ignore_index=True)
    agg = aggregate_4h(raw)
    agg.index.name = "ts"
    agg.index = agg.index.tz_convert(None)
    path = os.path.join(OUTDIR, f"{coin}_metrics_4h.csv")
    agg.to_csv(path, float_format="%.6f")
    print(f"{coin}: days={len(frames)} 4h_bars={len(agg)} "
          f"range={agg.index[0]}..{agg.index[-1]}", flush=True)

def main():
    os.makedirs(OUTDIR, exist_ok=True)
    targets = sys.argv[1:] if len(sys.argv) > 1 else COINS
    for coin in targets:
        run_coin(coin)
    print("ALL DONE", flush=True)

if __name__ == "__main__":
    main()
