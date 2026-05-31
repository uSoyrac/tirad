#!/usr/bin/env python3
"""
regime_timing.py — MULTI-MOTOR: rejim dedektörü agresif botu tetikler mi?
═══════════════════════════════════════════════════════════════════════
Motor1 (rejim skoru: son edge performansı + BTC ADX + düşük-vov) yüksekken
Motor2 (agresif bot) girer, $1000 hedefe ulaşınca çek. Rejim-tetiklemeli vs
rastgele/her-zaman giriş kıyaslanır — GERÇEK kronolojik sıra (şanslı dönem korunur).
"""
import json, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
from signal_lab import load_all, adx, atr
from meta_features_v2 import FEATURES_V2
from bot_v2 import build_context, precompute, candidate
from live_strategy import SL_ATR, TP_R
from sklearn.ensemble import HistGradientBoostingClassifier

TOP5=["BTC","ETH","SOL","BNB","XRP"]; CUT="2024-04-01"

def collect_chrono():
    """Kronolojik trade akışı + her trade anında rejim sinyalleri (causal)."""
    dfs=load_all("mktdata","4h"); ctx=build_context(dfs); pcs={c:precompute(c,dfs[c],ctx) for c in TOP5}
    btc=dfs["BTC"]; btc_adx,_,_=adx(btc,14); btc_a=atr(btc,14)
    btc_atrp=btc_a/btc["close"].to_numpy(float); btc_vov=pd.Series(btc_atrp).rolling(30).std().to_numpy()
    bidx=btc.index
    rows=[r for r in json.load(open("/tmp/meta_dataset_v2vov.json")) if r["coin"] in TOP5 and r["entry_ts"]<CUT]
    X=np.array([[r.get(f,np.nan) for f in FEATURES_V2] for r in rows],float); y=np.array([r["win"] for r in rows])
    clf=HistGradientBoostingClassifier(max_depth=3,max_iter=200,learning_rate=0.05,l2_regularization=1.0,min_samples_leaf=60,random_state=42).fit(X,y)
    model={"model":clf,"features":FEATURES_V2,"threshold":0.35}
    n=max(len(pcs[c]["C"]) for c in TOP5); t0=int(pcs["BTC"]["idx"].searchsorted(pd.Timestamp(CUT)))
    pos={}; T=[]
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
                # rejim: giriş anındaki BTC ADX + vov
                bi=int(bidx.searchsorted(pc["idx"][p["t0"]]))
                bi=min(bi,len(btc_adx)-1)
                T.append({"r":r,"ts":str(pc["idx"][t]),"badx":float(btc_adx[bi]) if np.isfinite(btc_adx[bi]) else 20,
                          "bvov":float(btc_vov[bi]) if np.isfinite(btc_vov[bi]) else 0.01}); pos.pop(c)
        for c in TOP5:
            pc=pcs[c]
            if c in pos or len(pos)>=5 or t>=len(pc["C"])-1: continue
            dec=candidate(pc,t,model)
            if dec:
                br=pc["btc_reg"][t]
                if np.isfinite(br) and ((dec["d"]==1 and br<0.5) or (dec["d"]==-1 and br>=0.5)): continue
                entry=float(pc["O"][t+1])
                pos[c]={**dec,"entry":entry,"t0":t,"sl":entry-dec["d"]*SL_ATR*pc["atr"][t],"tp":entry+dec["d"]*TP_R*SL_ATR*pc["atr"][t]}
    return T

def regime_score(T):
    """Motor1: her trade anında rejim skoru = son8 edge perf + BTC ADX (yüksek=trend) + düşük vov."""
    R=np.array([t["r"] for t in T]); badx=np.array([t["badx"] for t in T]); bvov=np.array([t["bvov"] for t in T])
    recent=pd.Series(R).rolling(8).mean().shift(1).to_numpy()    # causal: önceki 8 işlem perf
    s=np.zeros(len(T))
    for i in range(len(T)):
        rec=recent[i] if np.isfinite(recent[i]) else 0
        s[i]= (1 if rec>0.2 else 0) + (1 if badx[i]>25 else 0) + (1 if (np.isfinite(bvov[i]) and bvov[i]<np.nanmedian(bvov)) else 0)
    return s  # 0-3

def harvest(T, gate, risk=0.5, K=20, target=10.0, start=1.0):
    """Agresif: gate=True olan başlangıçlardan, K işlem içinde target'a ulaş. Kronolojik."""
    R=np.array([t["r"] for t in T]); succ=ru=att=0
    i=0
    while i<len(T)-1:
        if not gate[i]: i+=1; continue
        att+=1; eq=start; j=i
        while j<min(i+K,len(T)):
            eq*=(1+risk*R[j]); j+=1
            if eq>=target: succ+=1; break
            if eq<=0.05: ru+=1; break
        i=j+1   # bu denemeden sonra devam
    return att, succ, ru

def main():
    T=collect_chrono()
    sc=regime_score(T)
    print("="*80); print(f"  MULTI-MOTOR REJİM ZAMANLAMASI — {len(T)} kronolojik işlem (2024-04→2026-05)"); print("="*80)
    print(f"  Motor1 rejim skoru dağılımı: " + str({int(k):int((sc==k).sum()) for k in range(4)}))
    print(f"\n  Hedef: $1→$10 (10x), risk %50, 20-işlem pencere. Rejim-gate vs her-zaman:")
    print(f"  {'gate':22}{'deneme':>8}{'başarı':>8}{'iflas':>8}{'P(başarı)%':>12}")
    for lab,gate in [("Her zaman (gate yok)", np.ones(len(T),bool)),
                     ("Rejim skoru >=1", sc>=1),
                     ("Rejim skoru >=2", sc>=2),
                     ("Rejim skoru =3 (en güçlü)", sc>=3)]:
        att,su,ru=harvest(T,gate)
        p=su/att*100 if att else 0
        print(f"  {lab:22}{att:>8}{su:>8}{ru:>8}{p:>12.1f}")
    # ek: yüksek-rejimde tek-işlem ort getiri (rejim gerçekten daha iyi mi?)
    R=np.array([t["r"] for t in T])
    print(f"\n  Rejim doğrulama — skor bazında SONRAKİ işlemin ort getirisi:")
    for k in range(4):
        nxt=[R[i] for i in range(len(T)-1) if sc[i]==k]
        if nxt: print(f"    skor={k}: sonraki işlem ort {np.mean(nxt):+.3f}R (n={len(nxt)})")
    print(f"\n  >>> Rejim-gate P(başarı)'yı her-zamandan YÜKSEK yapıyorsa → zamanlama işe yarıyor.")

if __name__=="__main__":
    main()
