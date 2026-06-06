#!/usr/bin/env python3
"""fetch_news.py — GDELT'ten günlük kripto haber TONU + HACMİ (2021-2026), causal sentiment."""
import urllib.request, urllib.parse, json, time, warnings
import pandas as pd
warnings.filterwarnings("ignore")

def get(u, retries=6):
    for i in range(retries):
        try:
            req=urllib.request.Request(u, headers={"User-Agent":"Mozilla/5.0"})
            return urllib.request.urlopen(req, timeout=30).read()
        except Exception as e:
            if "429" in str(e): time.sleep(10); continue
            return None
    return None

def fetch_mode(query, mode, start, end):
    q=urllib.parse.urlencode({"query":query,"mode":mode,
        "startdatetime":start,"enddatetime":end,"format":"json"})
    r=get(f"https://api.gdeltproject.org/api/v2/doc/doc?{q}")
    if not r: return {}
    try:
        tl=json.loads(r).get("timeline",[])
        if not tl: return {}
        return {p["date"][:8]: p["value"] for p in tl[0]["data"]}
    except Exception: return {}

def main():
    # 6-aylık chunk'larla 2021→2026
    chunks=[("20210101000000","20210701000000"),("20210701000000","20220101000000"),
            ("20220101000000","20220701000000"),("20220701000000","20230101000000"),
            ("20230101000000","20230701000000"),("20230701000000","20240101000000"),
            ("20240101000000","20240701000000"),("20240701000000","20250101000000"),
            ("20250101000000","20250701000000"),("20250701000000","20260101000000"),
            ("20260101000000","20260601000000")]
    tone={}; vol={}
    for s,e in chunks:
        t=fetch_mode("bitcoin OR cryptocurrency","timelinetone",s,e); tone.update(t); time.sleep(2)
        v=fetch_mode("bitcoin OR cryptocurrency","timelinevol",s,e); vol.update(v); time.sleep(2)
        print(f"  {s[:6]}: ton {len(t)} gün, hacim {len(v)} gün", flush=True)
    dates=sorted(set(tone)|set(vol))
    df=pd.DataFrame({"date":[pd.to_datetime(d) for d in dates],
                     "tone":[tone.get(d) for d in dates],
                     "vol":[vol.get(d) for d in dates]})
    df.to_csv("news_gdelt.csv",index=False)
    print(f"✅ news_gdelt.csv — {len(df)} gün ({df['date'].min().date()}→{df['date'].max().date()}), ton ort {df['tone'].mean():.2f}", flush=True)

if __name__=="__main__": main()
