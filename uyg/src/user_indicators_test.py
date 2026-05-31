#!/usr/bin/env python3
"""
user_indicators_test.py — Kullanıcının önerdiği indikatörleri meta-feature olarak test et:
OTT (Optimized Trend Tracker), TTM Squeeze, Fibonacci retracement mesafesi,
Market Structure Break recency. Hepsi causal; v2+vov üstüne OOS lift ölçülür.
"""
import json, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
from signal_lab import load_all, ema, atr, sma, bollinger
from meta_features_v2 import FEATURES_V2, wf_lift

NEW = ["ott_dist","ott_dir","squeeze","sq_mom","fib_dist","msb_age"]

def ott(c, period=2, percent=1.4):
    n=len(c); mavg=pd.Series(c).ewm(span=period,adjust=False).mean().to_numpy()
    fark=mavg*percent/100; longstop=mavg-fark; shortstop=mavg+fark
    ls=np.copy(longstop); ss=np.copy(shortstop); d=np.ones(n)
    for i in range(1,n):
        ls[i]=max(longstop[i],ls[i-1]) if mavg[i]>ls[i-1] else longstop[i]
        ss[i]=min(shortstop[i],ss[i-1]) if mavg[i]<ss[i-1] else shortstop[i]
        if mavg[i]>ss[i-1]: d[i]=1
        elif mavg[i]<ls[i-1]: d[i]=-1
        else: d[i]=d[i-1]
    ott_line=np.where(d==1,ls,ss)
    return (c-ott_line)/(c+1e-9), d

def indicators(df):
    c=df["close"].to_numpy(float); h=df["high"].to_numpy(float); l=df["low"].to_numpy(float)
    od,odir=ott(c)
    # TTM squeeze: Bollinger (20,2) Keltner (20,1.5*ATR) içinde mi
    m,bu,bl=bollinger(c,20,2.0); a=atr(df,20); km=sma(c,20); ku=km+1.5*a; kl=km-1.5*a
    squeeze=((bu<ku)&(bl>kl)).astype(float)          # 1=sıkışma (breakout yakın)
    sq_mom=(c-sma(c,20))/(a+1e-9)                     # squeeze momentum yönü
    # Fibonacci: son 50-bar swing'in 0.618 seviyesine uzaklık
    hh=pd.Series(h).rolling(50).max().to_numpy(); ll=pd.Series(l).rolling(50).min().to_numpy()
    fib618=ll+0.618*(hh-ll); fib_dist=(c-fib618)/(c+1e-9)
    # MSB recency: son higher-high/lower-low kırılımından bu yana bar
    hh20=pd.Series(h).rolling(20).max().shift(1).to_numpy()
    ll20=pd.Series(l).rolling(20).min().shift(1).to_numpy()
    brk=np.zeros(len(c))
    for i in range(1,len(c)):
        if c[i]>hh20[i] or c[i]<ll20[i]: brk[i]=0
        else: brk[i]=brk[i-1]+1
    return {"ott_dist":od,"ott_dir":odir,"squeeze":squeeze,"sq_mom":sq_mom,"fib_dist":fib_dist,"msb_age":brk}

def main():
    rows=json.load(open("/tmp/meta_dataset_v2vov.json"))
    dfs=load_all("mktdata","4h")
    ind={c:indicators(df) for c,df in dfs.items()}
    posmap={c:{str(ts):i for i,ts in enumerate(df.index)} for c,df in dfs.items()}
    for r in rows:
        c=r["coin"]; i=posmap[c].get(r["entry_ts"])
        if i is None or i<1:
            for k in NEW: r[k]=np.nan
            continue
        fi=i-1                                        # giriş-anı (sinyal barı), causal
        for k in NEW:
            v=ind[c][k][fi]; r[k]=float(v) if np.isfinite(v) else np.nan
    print("="*76); print("  KULLANICI İNDİKATÖRLERİ TESTİ (OTT/Squeeze/Fib/MSB) — v2+vov üstüne"); print("="*76)
    base=wf_lift(rows,FEATURES_V2)['sel_e']
    print(f"  baseline v2+vov: {base:+.3f}R")
    for f in NEW:
        e=wf_lift(rows,FEATURES_V2+[f])['sel_e']
        print(f"  +{f:9}: {e:+.3f}R  ({e-base:+.3f})  {'✓' if e-base>0.005 else ''}")
    allnew=wf_lift(rows,FEATURES_V2+NEW)['sel_e']
    print(f"  +HEPSİ:    {allnew:+.3f}R  ({allnew-base:+.3f})")
    # en iyi tekli(ler)i greedy ekle
    keep=[f for f in NEW if wf_lift(rows,FEATURES_V2+[f])['sel_e']-base>0.005]
    if keep:
        eg=wf_lift(rows,FEATURES_V2+keep)['sel_e']
        print(f"\n  >>> Pozitif olanlar {keep}: birlikte {eg:+.3f}R ({eg-base:+.3f}) → {'EDGE ARTTI ✓' if eg-base>0.005 else 'birlikte sönüyor'}")
    else:
        print(f"\n  >>> Hiçbiri OOS lift vermedi — bu indikatörler (OHLCV-türevi) edge eklemiyor.")

if __name__=="__main__":
    main()
