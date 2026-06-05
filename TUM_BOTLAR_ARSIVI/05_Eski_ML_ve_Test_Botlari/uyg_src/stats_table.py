#!/usr/bin/env python3
"""stats_table.py — Son 12 ay, top-5, leak-free: per-coin + tutma süresi + long/short detaylı tablo."""
import json, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
from signal_lab import load_all
from meta_features_v2 import FEATURES_V2
from bot_v2 import build_context, precompute, candidate
from live_strategy import SL_ATR, TP_R
from sklearn.ensemble import HistGradientBoostingClassifier

TOP5=["BTC","ETH","SOL","BNB","XRP"]; WIN="2025-06-01"

def main():
    dfs=load_all("mktdata","4h"); ctx=build_context(dfs)
    pcs={c:precompute(c,dfs[c],ctx) for c in TOP5}
    rows=[r for r in json.load(open("/tmp/meta_dataset_v2vov.json")) if r["coin"] in TOP5 and r["entry_ts"]<WIN]
    X=np.array([[r.get(f,np.nan) for f in FEATURES_V2] for r in rows],float); y=np.array([r["win"] for r in rows])
    clf=HistGradientBoostingClassifier(max_depth=3,max_iter=200,learning_rate=0.05,l2_regularization=1.0,min_samples_leaf=60,random_state=42).fit(X,y)
    model={"model":clf,"features":FEATURES_V2,"threshold":0.35}
    n=max(len(pcs[c]["C"]) for c in TOP5); t0=int(pcs["BTC"]["idx"].searchsorted(pd.Timestamp(WIN)))
    eq=100.0; peak=100.0; mdd=0.0; pos={}; T=[]
    RISK=0.0075  # muhafazakar
    for t in range(t0,n-1):
        for c in list(pos.keys()):
            p=pos[c]; pc=pcs[c]
            if t>=len(pc["C"]): pos.pop(c); continue
            hi,lo=pc["H"][t],pc["L"][t]; dd=p["d"]; xp=None
            if dd==1:
                if lo<=p["sl"]: xp=p["sl"]
                elif hi>=p["tp"]: xp=p["tp"]
            else:
                if hi>=p["sl"]: xp=p["sl"]
                elif lo<=p["tp"]: xp=p["tp"]
            if xp is not None:
                r=dd*(xp-p["entry"])/p["entry"]/p["sl_dist"]-0.0007*2/p["sl_dist"]
                eq+=p["risk_amt"]*r; peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak if peak>0 else 0)
                T.append({"coin":c,"dir":"LONG" if dd==1 else "SHORT","r":r,"bars":t-p["t0"],"win":r>0}); pos.pop(c)
        for c in TOP5:
            pc=pcs[c]
            if c in pos or len(pos)>=5 or t>=len(pc["C"])-1: continue
            dec=candidate(pc,t,model)
            if dec:
                br=pc["btc_reg"][t]
                if np.isfinite(br) and ((dec["d"]==1 and br<0.5) or (dec["d"]==-1 and br>=0.5)): continue
                entry=float(pc["O"][t+1])
                pos[c]={**dec,"entry":entry,"risk_amt":eq*RISK,"t0":t,"sl":entry-dec["d"]*SL_ATR*pc["atr"][t],"tp":entry+dec["d"]*TP_R*SL_ATR*pc["atr"][t]}
    df=pd.DataFrame(T)
    print("="*72); print("  SON 12 AY · TOP-5 · 4H · LEAK-FREE — DETAYLI TABLO"); print("="*72)
    print(f"\n  GENEL: {len(df)} işlem | WR %{df['win'].mean()*100:.0f} | beklenti {df['r'].mean():+.3f}R | $100→${eq:.0f} | MaxDD %{mdd*100:.0f}")
    print(f"  Ort. tutma süresi: {df['bars'].mean()*4:.0f} saat ({df['bars'].mean():.1f} bar) | LONG {len(df[df.dir=='LONG'])} / SHORT {len(df[df.dir=='SHORT'])}")
    print(f"\n  {'COIN':6}{'işlem':>7}{'WR%':>6}{'avgR':>8}{'toplamR':>9}{'tutma(s)':>10}")
    for c in TOP5:
        d=df[df.coin==c]
        if len(d): print(f"  {c:6}{len(d):>7}{d['win'].mean()*100:>6.0f}{d['r'].mean():>+8.3f}{d['r'].sum():>+9.1f}{d['bars'].mean()*4:>10.0f}")
    print(f"\n  {'YÖN':6}{'işlem':>7}{'WR%':>6}{'avgR':>8}")
    for dr in ["LONG","SHORT"]:
        d=df[df.dir==dr]
        if len(d): print(f"  {dr:6}{len(d):>7}{d['win'].mean()*100:>6.0f}{d['r'].mean():>+8.3f}")
    # kazanan/kaybeden büyüklük
    w=df[df.win]; l=df[~df.win]
    print(f"\n  Kazananlar: {len(w)} işlem, ort {w['r'].mean():+.2f}R | Kaybedenler: {len(l)} işlem, ort {l['r'].mean():+.2f}R")
    print(f"  → Düşük WR ama pozitif: kazanan {w['r'].mean():+.1f}R koşar, kaybeden {l['r'].mean():+.1f}R'de kesilir (asimetri)")

if __name__=="__main__":
    main()
