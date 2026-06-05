#!/usr/bin/env python3
"""
fetch_multiyear.py — Çok-yıllık gerçek OHLCV indirici (Binance spot, ccxt)
Edge'i istatistiksel güçle + rejim çeşitliliğiyle ölçmek için geniş veri.
Çıktı: mktdata/{COIN}_USDT_{TF}.csv  (ts,open,high,low,close,volume)
"""
import os, sys, time
import ccxt
import pandas as pd

TF = os.getenv("TF", "4h")
SINCE = os.getenv("SINCE", "2021-01-01T00:00:00Z")
OUT = "mktdata"
# Tier-1 likit evren (AGENT.md "top 20" ruhu). Olmayan/kısa olanlar atlanır.
COINS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "DOGE", "LINK",
         "DOT", "LTC", "ATOM", "NEAR", "APT", "ARB", "OP", "INJ", "FIL", "ETC", "UNI"]


def fetch_one(ex, symbol, tf, since_ms):
    all_rows = []
    cur = since_ms
    limit = 1000
    tf_ms = ex.parse_timeframe(tf) * 1000
    while True:
        try:
            batch = ex.fetch_ohlcv(symbol, tf, since=cur, limit=limit)
        except Exception as e:
            print(f"   ! {symbol} retry ({type(e).__name__})", flush=True)
            time.sleep(2); continue
        if not batch:
            break
        all_rows += batch
        cur = batch[-1][0] + tf_ms
        if len(batch) < limit:
            break
        if cur > ex.milliseconds():
            break
        time.sleep(ex.rateLimit / 1000.0)
    return all_rows


def main():
    os.makedirs(OUT, exist_ok=True)
    ex = ccxt.binance({"enableRateLimit": True, "timeout": 20000})
    since_ms = ex.parse8601(SINCE)
    print(f"Çekim: TF={TF} since={SINCE} → {OUT}/", flush=True)
    summary = []
    for c in COINS:
        sym = f"{c}/USDT"
        try:
            rows = fetch_one(ex, sym, TF, since_ms)
        except Exception as e:
            print(f"{c:6} SKIP ({type(e).__name__}: {str(e)[:50]})", flush=True); continue
        if not rows or len(rows) < 200:
            print(f"{c:6} yetersiz ({len(rows) if rows else 0} bar)", flush=True); continue
        df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
        df["ts"] = pd.to_datetime(df["ts"], unit="ms")
        df = df.drop_duplicates("ts").sort_values("ts")
        path = f"{OUT}/{c}_USDT_{TF}.csv"
        df.to_csv(path, index=False)
        yrs = (df["ts"].iloc[-1] - df["ts"].iloc[0]).days / 365.0
        print(f"{c:6} {len(df):>6} bar  {df['ts'].iloc[0].date()}→{df['ts'].iloc[-1].date()} ({yrs:.1f}y)", flush=True)
        summary.append((c, len(df), yrs))
    print(f"\nTAMAM: {len(summary)} coin indirildi → {OUT}/", flush=True)


if __name__ == "__main__":
    main()
