#!/usr/bin/env python3
"""
mm_compare.py — TÜM PARA-YÖNETİMİ SİSTEMLERİ vs Kelly (gerçek 1-yıl 4H top-5 edge)
═══════════════════════════════════════════════════════════════════════
Aynı gerçek trade akışı üstünde 12 sizing sistemi Monte Carlo ile yarışır:
flat, fixed%, Kelly, Optimal-f (Ralph Vince), Paroli, ORP/martingale, Fibonacci,
D'Alembert, Labouchère, Oscar's Grind, Volatility-scaling, Half-Kelly.
Rapor: medyan büyüme, P5, P(ruin), MaxDD. Sıralama: P(ruin)=0 şartıyla medyan büyüme.
"""
import json, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
from signal_lab import load_all
from meta_features_v2 import FEATURES_V2
from bot_v2 import build_context, precompute, candidate
from live_strategy import SL_ATR, TP_R
from sklearn.ensemble import HistGradientBoostingClassifier

TOP5=["BTC","ETH","SOL","BNB","XRP"]; WIN="2025-05-01"; START=100.0

def collect():
    dfs=load_all("mktdata","4h"); ctx=build_context(dfs); pcs={c:precompute(c,dfs[c],ctx) for c in TOP5}
    rows=[r for r in json.load(open("/tmp/meta_dataset_v2vov.json")) if r["coin"] in TOP5 and r["entry_ts"]<WIN]
    X=np.array([[r.get(f,np.nan) for f in FEATURES_V2] for r in rows],float); y=np.array([r["win"] for r in rows])
    clf=HistGradientBoostingClassifier(max_depth=3,max_iter=200,learning_rate=0.05,l2_regularization=1.0,min_samples_leaf=60,random_state=42).fit(X,y)
    model={"model":clf,"features":FEATURES_V2,"threshold":0.35}
    n=max(len(pcs[c]["C"]) for c in TOP5); t0=int(pcs["BTC"]["idx"].searchsorted(pd.Timestamp(WIN)))
    pos={}; R=[]
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
                R.append(dd*(xp-p["entry"])/p["entry"]/p["sl_dist"]-0.0007*2/p["sl_dist"]); pos.pop(c)
        for c in TOP5:
            pc=pcs[c]
            if c in pos or len(pos)>=5 or t>=len(pc["C"])-1: continue
            dec=candidate(pc,t,model)
            if dec:
                br=pc["btc_reg"][t]
                if np.isfinite(br) and ((dec["d"]==1 and br<0.5) or (dec["d"]==-1 and br>=0.5)): continue
                entry=float(pc["O"][t+1])
                pos[c]={**dec,"entry":entry,"sl":entry-dec["d"]*SL_ATR*pc["atr"][t],"tp":entry+dec["d"]*TP_R*SL_ATR*pc["atr"][t]}
    return np.array(R)

def optimal_f(R):
    worst=abs(min(R.min(),-1e-9)); best=0; bf=0.01
    for f in np.arange(0.01,1.0,0.01):
        twr=np.prod(1+f*R/worst)
        if twr>best: best=twr; bf=f
    return bf, worst

def run_system(R, sys, base_unit=2.0, ff=0.02, kelly_f=0.25, of=None, worst=1.0):
    eq=START; peak=START; mdd=0; unit=base_unit; fib=[1,1,2,3,5,8,13,21,34]; fi=0
    dalem=1; lab=[1,2,3]; osc_unit=base_unit; osc_base=START; cw=0; deficit=0
    p=(R>0).mean(); b=R[R>0].mean()/abs(R[R<=0].mean()) if (R<=0).any() and (R>0).any() else 1
    full_kelly=max(0.0,p-(1-p)/b) if b>0 else 0
    for r in R:
        if sys=="flat": bet=base_unit
        elif sys=="fixed%": bet=eq*ff
        elif sys=="kelly": bet=eq*full_kelly*kelly_f
        elif sys=="half_kelly": bet=eq*full_kelly*0.5
        elif sys=="optimal_f": bet=eq*of/worst*abs(R[R<=0].mean() if (R<=0).any() else 1)  # of fraction
        elif sys=="paroli":
            s=min(cw,3);
            if s>=3: cw=0; s=0
            bet=min(base_unit*(2**s),eq*0.20)
        elif sys=="orp_recovery": bet=min(max(base_unit,deficit+base_unit),eq)
        elif sys=="fibonacci": bet=min(base_unit*fib[fi],eq*0.20)
        elif sys=="dalembert": bet=min(base_unit*max(1,dalem),eq*0.20)
        elif sys=="labouchere": bet=min(base_unit*(lab[0]+(lab[-1] if len(lab)>1 else 0)),eq) if lab else base_unit
        elif sys=="oscars_grind": bet=min(osc_unit,eq)
        elif sys=="vol_scaling": bet=eq*ff*min(2.0, 0.04/(abs(r)*0+0.02))  # basit: sabit vol hedefi (R zaten vol-normalize)
        else: bet=base_unit
        pnl=bet*r; eq+=pnl
        win=r>0
        # durum güncelle
        if win:
            cw+=1; deficit=0; fi=max(fi-2,0); dalem=max(1,dalem-1)
            if lab:
                if len(lab)<=2: lab=[1,2,3]
                else: lab=lab[1:-1] or [1,2,3]
            osc_unit=osc_unit+base_unit;
            if eq>=osc_base+base_unit: osc_base=eq; osc_unit=base_unit  # hedef tut
        else:
            cw=0; deficit+=bet; fi=min(fi+1,len(fib)-1); dalem+=1
            if lab is not None: lab=lab+[max(1,int(bet/base_unit))]
        peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak if peak>0 else 0)
        if eq<=base_unit: eq=0.0; break
    return eq, mdd*100

def mc(R, sys, n=8000, **kw):
    rng=np.random.default_rng(42); fins=[]; mdds=[]; ruin=0
    for _ in range(n):
        idx=rng.integers(0,len(R),size=len(R)); seq=R[idx]
        eq,md=run_system(seq,sys,**kw); fins.append(eq); mdds.append(md); ruin+=(eq<=0)
    f=np.array(fins)
    return {"median":float(np.median(f)),"p5":float(np.percentile(f,5)),"p95":float(np.percentile(f,95)),
            "ruin":ruin/n*100,"mdd":float(np.median(mdds))}

def main():
    R=collect()
    print("="*84); print(f"  PARA-YÖNETİMİ SİSTEMLERİ — gerçek 1-yıl 4H top-5 ({len(R)} işlem, WR%{(R>0).mean()*100:.0f}, beklenti{R.mean():+.3f}R)"); print("="*84)
    of,worst=optimal_f(R)
    print(f"  Optimal-f (Ralph Vince): f={of:.2f} | worst loss={worst:.2f}R | full Kelly={(R>0).mean()-(1-(R>0).mean())/(R[R>0].mean()/abs(R[R<=0].mean())):.2f}")
    systems=["flat","fixed%","kelly","half_kelly","optimal_f","vol_scaling","paroli",
             "orp_recovery","fibonacci","dalembert","labouchere","oscars_grind"]
    res={}
    print(f"\n  {'sistem':16}{'medyan$':>10}{'P5$':>9}{'P95$':>11}{'P(ruin)%':>10}{'medMDD%':>9}")
    for s in systems:
        m=mc(R,s,of=of,worst=worst); res[s]=m
        flag=" ✓" if m["ruin"]<1 else (" ← İFLAS" if m["ruin"]>20 else " ⚠")
        print(f"  {s:16}{m['median']:>10.0f}{m['p5']:>9.0f}{m['p95']:>11.0f}{m['ruin']:>10.1f}{m['mdd']:>9.0f}{flag}")
    # sıralama: ruin<2 olanlar arasında medyan büyümeye göre
    safe={s:m for s,m in res.items() if m["ruin"]<2}
    rank=sorted(safe.items(), key=lambda x:-x[1]["median"])
    print(f"\n  >>> EN KÂRLI (P(ruin)<%2 güvenli olanlar arasında):")
    for i,(s,m) in enumerate(rank[:5]):
        print(f"     {i+1}. {s:14} medyan ${m['median']:.0f} ({m['median']/100:.1f}x)  MDD%{m['mdd']:.0f}  ruin%{m['ruin']:.1f}")
    print(f"\n  İFLAS RİSKLİ (P(ruin)>%20): {[s for s,m in res.items() if m['ruin']>20]}")

if __name__=="__main__":
    main()
