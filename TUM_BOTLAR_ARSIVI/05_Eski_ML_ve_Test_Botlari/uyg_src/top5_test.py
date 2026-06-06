#!/usr/bin/env python3
"""
top5_test.py — TOP-5 odaklı edge + en mantıklı kombinasyon (BTC-rejim hizalama)
═══════════════════════════════════════════════════════════════════════
Sadece BTC/ETH/SOL/BNB/XRP. Karşılaştırır:
  (a) top-5 standalone meta edge (wf_lift)
  (b) v2+vov bot replay — 20-coin model
  (c) + BTC-rejim hizalama filtresi (sadece BTC ana trendi yönünde işlem)
  (d) top-5-only retrain model
"""
import os, json, pickle, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
from signal_lab import load_all, atr, metrics
from meta_features_v2 import FEATURES_V2, wf_lift
from bot_v2 import build_context, precompute, candidate, feature_row
from live_strategy import SL_ATR, TP_R, BASE_RISK, MAX_RISK
from sklearn.ensemble import HistGradientBoostingClassifier

TOP5 = ["BTC","ETH","SOL","BNB","XRP"]

def replay5(pcs, model, coins, start_frac=0.60, max_pos=4, risk_mult=0.5, btc_align=False):
    n=max(len(pcs[c]["C"]) for c in coins); t0=int(n*start_frac)
    eq=100.0; peak=100.0; mdd=0.0; pos={}; trades=[]
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
                trades.append({"r_mult":r}); pos.pop(c)
        for c in coins:
            pc=pcs[c]
            if c in pos or len(pos)>=max_pos or t>=len(pc["C"])-1: continue
            dec=candidate(pc,t,model)
            if dec:
                if btc_align:                       # BTC ana trendi yönünde değilse atla
                    br=pc["btc_reg"][t]
                    if np.isfinite(br) and ((dec["d"]==1 and br<0.5) or (dec["d"]==-1 and br>=0.5)): continue
                entry=float(pc["O"][t+1]); ra=eq*dec["risk_pct"]*risk_mult
                pos[c]={**dec,"entry":entry,"risk_amt":ra,"sl":entry-dec["d"]*SL_ATR*pc["atr"][t],"tp":entry+dec["d"]*TP_R*SL_ATR*pc["atr"][t]}
        if eq<=0: break
    m=metrics(trades); yr=(n-t0)/(6*365); x=eq/100; cagr=(x**(1/yr)-1)*100 if x>0 else -100
    return {"n":m.get("n",0),"wr":m.get("wr",0),"e":m.get("avg_r",0),"x":x,"mdd":mdd*100,"cagr":cagr,"freq":m.get("n",0)/yr}

def main():
    dfs_all=load_all("mktdata","4h"); ctx=build_context(dfs_all)   # context 20-coin'den (xs_rank evreni geniş daha iyi)
    pcs={c:precompute(c,dfs_all[c],ctx) for c in TOP5}
    rows=json.load(open("/tmp/meta_dataset_v2vov.json"))
    rows5=[r for r in rows if r["coin"] in TOP5]
    print("="*78); print(f"  TOP-5 ANALİZİ (BTC/ETH/SOL/BNB/XRP) — {len(rows5)} trade (20-coin'de {len(rows)})"); print("="*78)

    # (a) top-5 standalone meta edge — 20-coin model context'i wf_lift kendi eğitir
    r_full=wf_lift(rows, FEATURES_V2)
    r_5=wf_lift(rows5, FEATURES_V2)
    print(f"  [a] Standalone meta OOS:  20-coin {r_full['sel_e']:+.3f}R   |   top-5 {r_5['sel_e']:+.3f}R ({r_5['pos']}/{r_5['tot']} coin+)")

    model20=pickle.load(open("meta_model_v2.pkl","rb"))
    # (d) top-5-only retrain
    X5=np.array([[r.get(f,np.nan) for f in FEATURES_V2] for r in rows5],float); y5=np.array([r["win"] for r in rows5])
    clf5=HistGradientBoostingClassifier(max_depth=3,max_iter=200,learning_rate=0.05,l2_regularization=1.0,min_samples_leaf=60,random_state=42)
    clf5.fit(X5,y5); model5={"model":clf5,"features":FEATURES_V2,"threshold":0.35}

    print(f"\n  Bot replay (top-5, son %40 OOS, risk_mult=0.5, maxPos=4):")
    print(f"  {'varyant':28}{'işlem':>7}{'freq/yr':>8}{'WR%':>6}{'E(R)':>7}{'x':>6}{'MDD%':>7}{'CAGR%':>7}")
    for lab,model,ba in [("(b) 20-coin model",model20,False),
                          ("(c) + BTC-rejim hizalama",model20,True),
                          ("(d) top-5 retrain model",model5,False),
                          ("(d+c) top-5 retrain+BTC",model5,True)]:
        r=replay5(pcs,model,TOP5,risk_mult=0.5,max_pos=4,btc_align=ba)
        print(f"  {lab:28}{r['n']:>7}{r['freq']:>8.0f}{r['wr']:>6.1f}{r['e']:>+7.3f}{r['x']:>6.1f}{r['mdd']:>7.1f}{r['cagr']:>7.0f}")

if __name__=="__main__":
    main()
