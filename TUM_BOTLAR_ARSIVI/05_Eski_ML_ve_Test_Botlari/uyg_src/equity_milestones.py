#!/usr/bin/env python3
"""equity_milestones.py — Son 2 yıl: zirve + $200/$300/$500/$1000 aşma tarihleri (leak-free)."""
import json, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
from signal_lab import load_all
from meta_features_v2 import FEATURES_V2
from bot_v2 import build_context, precompute, candidate
from live_strategy import SL_ATR, TP_R
from sklearn.ensemble import HistGradientBoostingClassifier

TOP5=["BTC","ETH","SOL","BNB","XRP"]; CUT="2024-04-01"

def run(pcs, model, risk_mult):
    n=max(len(pcs[c]["C"]) for c in TOP5); t0=int(pcs["BTC"]["idx"].searchsorted(pd.Timestamp(CUT)))
    eq=100.0; peak=100.0; peak_ts=CUT; mdd=0; pos={}; curve=[]
    miles={200:None,300:None,500:None,1000:None}
    for t in range(t0,n-1):
        ts=str(pcs["BTC"]["idx"][t])[:10]
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
                eq+=p["risk_amt"]*r
                if eq>peak: peak=eq; peak_ts=str(pc["idx"][t])[:10]
                mdd=max(mdd,(peak-eq)/peak if peak>0 else 0)
                for m in miles:
                    if miles[m] is None and eq>=m: miles[m]=str(pc["idx"][t])[:10]
                curve.append((ts,eq)); pos.pop(c)
        for c in TOP5:
            pc=pcs[c]
            if c in pos or len(pos)>=5 or t>=len(pc["C"])-1: continue
            dec=candidate(pc,t,model)
            if dec:
                br=pc["btc_reg"][t]
                if np.isfinite(br) and ((dec["d"]==1 and br<0.5) or (dec["d"]==-1 and br>=0.5)): continue
                entry=float(pc["O"][t+1])
                pos[c]={**dec,"entry":entry,"risk_amt":eq*dec["risk_pct"]*risk_mult,
                        "sl":entry-dec["d"]*SL_ATR*pc["atr"][t],"tp":entry+dec["d"]*TP_R*SL_ATR*pc["atr"][t]}
        if eq<=0: break
    return eq, peak, peak_ts, mdd*100, miles

def main():
    dfs=load_all("mktdata","4h"); ctx=build_context(dfs); pcs={c:precompute(c,dfs[c],ctx) for c in TOP5}
    rows=[r for r in json.load(open("/tmp/meta_dataset_v2vov.json")) if r["coin"] in TOP5 and r["entry_ts"]<CUT]
    X=np.array([[r.get(f,np.nan) for f in FEATURES_V2] for r in rows],float); y=np.array([r["win"] for r in rows])
    clf=HistGradientBoostingClassifier(max_depth=3,max_iter=200,learning_rate=0.05,l2_regularization=1.0,min_samples_leaf=60,random_state=42).fit(X,y)
    model={"model":clf,"features":FEATURES_V2,"threshold":0.35}
    print("="*80); print("  SON 2 YIL (2024-04→2026-05) — ZİRVE + KİLOMETRE TAŞI TARİHLERİ (leak-free)"); print("="*80)
    for rm,lab in [(0.5,"Muhafazakar (~%0.75/işlem)"),(1.0,"Orta (~%1.5)"),(2.0,"Agresif (~%3)")]:
        eq,peak,pts,mdd,miles=run(pcs,model,rm)
        print(f"\n  ── {lab} ──")
        print(f"    Son kasa: ${eq:.0f} ({eq/100:.1f}x) | ZİRVE: ${peak:.0f} ({pts}) | MaxDD %{mdd:.0f}")
        ms=" | ".join(f"${m}→{d}" for m,d in miles.items() if d) or "hiçbiri aşılmadı"
        print(f"    Kilometre taşları (ilk aşma): {ms}")

if __name__=="__main__":
    main()
