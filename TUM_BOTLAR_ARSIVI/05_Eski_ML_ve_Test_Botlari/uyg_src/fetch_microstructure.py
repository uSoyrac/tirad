#!/usr/bin/env python3
"""
fetch_microstructure.py — Kline'lardan İŞLEM SAYISI + TAKER BUY hacmi (order-flow imzası)
OHLCV'de olmayan ama ücretsiz: katılım (trade count) + agresif alım oranı (taker buy / volume).
Çıktı: microdata/{COIN}_micro.csv  (ts, num_trades, taker_buy_ratio)
"""
import os, time, json, urllib.request, urllib.parse, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
OUT="microdata"
COINS=["BTC","ETH","SOL","BNB","XRP","ADA","AVAX","DOGE","LINK","DOT",
       "LTC","ATOM","NEAR","APT","ARB","OP","INJ","FIL","ETC","UNI"]
BASE="https://fapi.binance.com/fapi/v1/klines"

def fetch(sym, start_ms):
    rows=[]; cur=start_ms; tf_ms=4*3600*1000
    while True:
        q=urllib.parse.urlencode({"symbol":sym,"interval":"4h","startTime":cur,"limit":1500})
        try:
            req=urllib.request.Request(f"{BASE}?{q}", headers={"User-Agent":"Mozilla/5.0"})
            d=json.loads(urllib.request.urlopen(req,timeout=20).read())
        except Exception as e:
            print(f"   retry {str(e)[:40]}",flush=True); time.sleep(2); continue
        if not d: break
        # kline alanları: [0]openTime ... [5]vol [8]numTrades [9]takerBuyBase
        for k in d:
            vol=float(k[5]); tb=float(k[9])
            rows.append((int(k[0]), int(k[8]), tb/vol if vol>0 else 0.5))
        cur=d[-1][0]+tf_ms
        if len(d)<1500 or cur>int(time.time()*1000): break
        time.sleep(0.15)
    return rows

def main():
    os.makedirs(OUT,exist_ok=True)
    start=int(pd.Timestamp("2021-01-01").timestamp()*1000)
    for c in COINS:
        try: rows=fetch(f"{c}USDT", start)
        except Exception as e: print(f"{c} SKIP {str(e)[:40]}",flush=True); continue
        if not rows: print(f"{c} boş",flush=True); continue
        df=pd.DataFrame(rows,columns=["ts","num_trades","taker_buy_ratio"]).drop_duplicates("ts")
        df["ts"]=pd.to_datetime(df["ts"],unit="ms"); df=df.sort_values("ts")
        df.to_csv(f"{OUT}/{c}_micro.csv",index=False)
        print(f"{c} {len(df)} bar  taker_buy ort %{df['taker_buy_ratio'].mean()*100:.1f}",flush=True)
    print("TAMAM",flush=True)

if __name__=="__main__": main()
