#!/usr/bin/env python3
"""
monthly_sim.py — Son 12 ay, $100, top-5, AY-AY (leak-free)
Model SADECE pencere-öncesi (2025-06 öncesi) veriyle eğitilir. Top-5 + BTC-rejim + meta v2+vov.
"""
import json, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
from signal_lab import load_all, metrics
from meta_features_v2 import FEATURES_V2
from bot_v2 import build_context, precompute, candidate
from live_strategy import SL_ATR, TP_R
from sklearn.ensemble import HistGradientBoostingClassifier

TOP5=["BTC","ETH","SOL","BNB","XRP"]
WIN_START="2025-06-01"

def run(pcs, model, risk_mult, max_pos=5, btc_align=True):
    n=max(len(pcs[c]["C"]) for c in TOP5)
    idxBTC=pcs["BTC"]["idx"]
    t0=int(idxBTC.searchsorted(pd.Timestamp(WIN_START)))
    eq=100.0; peak=100.0; mdd=0.0; pos={}; trades=[]; monthly={}
    for t in range(t0,n-1):
        ts=pcs["BTC"]["idx"][t] if t<len(idxBTC) else None
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
        for c in TOP5:
            pc=pcs[c]
            if c in pos or len(pos)>=max_pos or t>=len(pc["C"])-1: continue
            dec=candidate(pc,t,model)
            if dec:
                if btc_align:
                    br=pc["btc_reg"][t]
                    if np.isfinite(br) and ((dec["d"]==1 and br<0.5) or (dec["d"]==-1 and br>=0.5)): continue
                entry=float(pc["O"][t+1]); ra=eq*dec["risk_pct"]*risk_mult
                pos[c]={**dec,"entry":entry,"risk_amt":ra,"sl":entry-dec["d"]*SL_ATR*pc["atr"][t],"tp":entry+dec["d"]*TP_R*SL_ATR*pc["atr"][t]}
        if ts is not None: monthly[str(ts)[:7]]=eq
        if eq<=0: break
    m=metrics(trades)
    return eq,mdd*100,m,monthly

def main():
    dfs=load_all("mktdata","4h"); ctx=build_context(dfs)
    pcs={c:precompute(c,dfs[c],ctx) for c in TOP5}
    rows=[r for r in json.load(open("/tmp/meta_dataset_v2vov.json")) if r["coin"] in TOP5]
    train=[r for r in rows if r["entry_ts"]<WIN_START]      # SIZINTISIZ: pencere-öncesi
    X=np.array([[r.get(f,np.nan) for f in FEATURES_V2] for r in train],float); y=np.array([r["win"] for r in train])
    clf=HistGradientBoostingClassifier(max_depth=3,max_iter=200,learning_rate=0.05,l2_regularization=1.0,min_samples_leaf=60,random_state=42).fit(X,y)
    model={"model":clf,"features":FEATURES_V2,"threshold":0.35}
    print("="*72)
    print(f"  SON 12 AY · $100 · TOP-5 · AY-AY (model {len(train)} pre-2025-06 trade ile eğitildi)")
    print("="*72)
    for rm,lab in [(0.5,"Muhafazakar (risk≈%0.75/işlem)"),(1.0,"Orta (risk≈%1.5/işlem)")]:
        eq,mdd,m,monthly=run(pcs,model,rm)
        print(f"\n  ── {lab} ──")
        prev=100.0
        for mo in sorted(monthly):
            v=monthly[mo]; ch=(v/prev-1)*100; prev=v
            bar="█"*max(0,int(min(v,400)/20))
            print(f"    {mo}:  ${v:7.2f}  ({ch:+5.1f}%)  {bar}")
        print(f"    ─────────────────────────────")
        print(f"    SONUÇ: $100 → ${eq:.2f} ({eq/100:.2f}x)  |  {m['n']} işlem, WR %{m.get('wr',0):.0f}, beklenti {m.get('avg_r',0):+.3f}R, MaxDD %{mdd:.0f}")

if __name__=="__main__":
    main()
