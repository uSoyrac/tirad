#!/usr/bin/env python3
"""fetch_funding.py — 20 coin funding rate geçmişi (yeni-bilgi: türev pozisyonlama)."""
import os, time, ccxt, pandas as pd, warnings
warnings.filterwarnings("ignore")
OUT="funddata"; COINS=["BTC","ETH","SOL","BNB","XRP","ADA","AVAX","DOGE","LINK","DOT",
       "LTC","ATOM","NEAR","APT","ARB","OP","INJ","FIL","ETC","UNI"]
def main():
    os.makedirs(OUT,exist_ok=True)
    ex=ccxt.binance({"enableRateLimit":True,"timeout":20000,"options":{"defaultType":"future"}})
    since=ex.parse8601("2021-01-01T00:00:00Z")
    for c in COINS:
        sym=f"{c}/USDT:USDT"; rows=[]; cur=since
        try:
            while True:
                b=ex.fetch_funding_rate_history(sym,since=cur,limit=1000)
                if not b: break
                rows+=[(x["timestamp"],x["fundingRate"]) for x in b]
                cur=b[-1]["timestamp"]+1
                if len(b)<1000 or cur>ex.milliseconds(): break
                time.sleep(ex.rateLimit/1000)
        except Exception as e:
            print(f"{c} SKIP {str(e)[:50]}",flush=True); continue
        if not rows: print(f"{c} boş",flush=True); continue
        df=pd.DataFrame(rows,columns=["ts","funding"]).drop_duplicates("ts")
        df["ts"]=pd.to_datetime(df["ts"],unit="ms"); df=df.sort_values("ts")
        df.to_csv(f"{OUT}/{c}_funding.csv",index=False)
        print(f"{c} {len(df)} funding ({df['ts'].iloc[0].date()}→{df['ts'].iloc[-1].date()})",flush=True)
    print("TAMAM",flush=True)
if __name__=="__main__": main()
