#!/usr/bin/env python3
"""
aggressive_sim.py — AGRESİF/PİYANGO MODU: küçük stake + yüksek risk, gerçek edge üstünde
Soru: edge'imiz yüksek kaldıraçta pozitif-beklenti piyango mu, yoksa sadece ruin mi?
Leak-free top-5 trade R-akışını bootstrap eder; risk-fraksiyonu (kaldıraç proxy'si)
süpürür; P(hedefe ulaşma) vs P(ruin) + beklenen değer raporlar.
"""
import json, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
from signal_lab import load_all
from meta_features_v2 import FEATURES_V2
from bot_v2 import build_context, precompute, candidate
from live_strategy import SL_ATR, TP_R
from sklearn.ensemble import HistGradientBoostingClassifier

TOP5=["BTC","ETH","SOL","BNB","XRP"]; CUT="2024-04-01"

def collect_R():
    dfs=load_all("mktdata","4h"); ctx=build_context(dfs)
    pcs={c:precompute(c,dfs[c],ctx) for c in TOP5}
    rows=[r for r in json.load(open("/tmp/meta_dataset_v2vov.json")) if r["coin"] in TOP5 and r["entry_ts"]<CUT]
    X=np.array([[r.get(f,np.nan) for f in FEATURES_V2] for r in rows],float); y=np.array([r["win"] for r in rows])
    clf=HistGradientBoostingClassifier(max_depth=3,max_iter=200,learning_rate=0.05,l2_regularization=1.0,min_samples_leaf=60,random_state=42).fit(X,y)
    model={"model":clf,"features":FEATURES_V2,"threshold":0.35}
    n=max(len(pcs[c]["C"]) for c in TOP5); t0=int(pcs["BTC"]["idx"].searchsorted(pd.Timestamp(CUT)))
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

def lottery(R, risk, target_mult, ruin=0.10, n=30000, maxsteps=3000, seed=42):
    rng=np.random.default_rng(seed); succ=ru=to=0; times=[]
    for _ in range(n):
        eq=1.0; steps=0; done=False
        while steps<maxsteps:
            r=R[rng.integers(len(R))]; eq*=(1+risk*r); steps+=1
            if eq>=target_mult: succ+=1; times.append(steps); done=True; break
            if eq<=ruin: ru+=1; done=True; break
        if not done: to+=1
    return succ/n*100, ru/n*100, (np.median(times) if times else None)

def main():
    R0=collect_R()
    # GERÇEK maliyet: küçük hesapta size-slippage ihmal ama funding drag gerçek
    # ~1.5 gün tutma × %0.03/8h funding ≈ %0.135 notional; SL ~%3 → ~0.045R drag/işlem
    FUND_DRAG=0.05
    R=R0-FUND_DRAG
    print("="*76); print(f"  AGRESİF/PİYANGO MODU — GERÇEK-maliyetli edge (leak-free top-5, {len(R)} işlem)"); print("="*76)
    print(f"  Ham beklenti {R0.mean():+.3f}R  →  funding-düzeltilmiş GERÇEK beklenti {R.mean():+.3f}R  (WR %{(R0>0).mean()*100:.0f})")
    print(f"  Risk-fraksiyonu = işlem başına kasanın riske attığın yüzdesi (yüksek = yüksek kaldıraç)")
    for tgt in [5, 10, 20]:
        print(f"\n  HEDEF {tgt}x  (örn $10→${10*tgt}):  P(ulaş) / P(ruin) / medyan işlem")
        print(f"  {'risk%':>6}{'P(ulaş)%':>10}{'P(ruin)%':>10}{'medyan':>9}{'EV (kabaca)':>14}")
        for risk in [0.05,0.10,0.20,0.30,0.50]:
            pw,pr,mt=lottery(R,risk,tgt)
            # kabaca EV: P(ulaş)*tgt - (kaybedişlerde ~ortalama -%80 stake) ; basitleştirilmiş
            ev = (pw/100)*tgt + (1-pw/100)*0.1 - 1   # ulaşırsa tgt katı, ruin'de ~%10 kalır, stake=1
            tl=f"{int(mt)}işl" if mt else "-"
            flag=" ✓+EV" if ev>0 else ""
            print(f"  {risk*100:>6.0f}{pw:>10.1f}{pr:>10.1f}{tl:>9}{ev:>+14.2f}{flag}")
    print(f"\n  Not: 'risk%30' ≈ 4 ardışık kayıpta kasanın ~%76'sı gider (yüksek-kaldıraç gerçeği).")
    print(f"  EV>0 = piyango pozitif beklentili (çok deneme yaparsan kârlısın); EV<0 = sistemli kayıp.")

if __name__=="__main__":
    main()
