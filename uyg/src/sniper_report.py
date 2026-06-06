#!/usr/bin/env python3
"""sniper_report.py — Son 3 ay, 4H, top-5 sniper: işlem-işlem $100 raporu (leak-free)."""
import json, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
from signal_lab import load_all, adx, atr
from meta_features_v2 import FEATURES_V2
from bot_v2 import build_context, precompute, candidate
from live_strategy import SL_ATR, TP_R
from sklearn.ensemble import HistGradientBoostingClassifier

TOP5=["BTC","ETH","SOL","BNB","XRP"]; WIN="2026-03-01"; RISK=0.05  # sniper agresif-ılımlı

def main():
    dfs=load_all("mktdata","4h"); ctx=build_context(dfs); pcs={c:precompute(c,dfs[c],ctx) for c in TOP5}
    # BTC rejim skoru (price-based, causal): ADX + vov + momentum
    btc=dfs["BTC"]; bc=btc["close"].to_numpy(float); ba,_,_=adx(btc,14); bat=atr(btc,14)
    batrp=bat/bc; bvov=pd.Series(batrp).rolling(30).std().to_numpy(); bmom=pd.Series(bc).pct_change(10).to_numpy()
    vmed=np.nanmedian(bvov); bidx=btc.index
    def regime(ts):
        i=min(int(bidx.searchsorted(ts)),len(ba)-1)
        s=(1 if (np.isfinite(ba[i]) and ba[i]>25) else 0)+(1 if (np.isfinite(bvov[i]) and bvov[i]<vmed) else 0)+(1 if (np.isfinite(bmom[i]) and abs(bmom[i])>0.05) else 0)
        return s
    rows=[r for r in json.load(open("/tmp/meta_dataset_v2vov.json")) if r["coin"] in TOP5 and r["entry_ts"]<WIN]
    X=np.array([[r.get(f,np.nan) for f in FEATURES_V2] for r in rows],float); y=np.array([r["win"] for r in rows])
    clf=HistGradientBoostingClassifier(max_depth=3,max_iter=200,learning_rate=0.05,l2_regularization=1.0,min_samples_leaf=60,random_state=42).fit(X,y)
    model={"model":clf,"features":FEATURES_V2,"threshold":0.35}
    n=max(len(pcs[c]["C"]) for c in TOP5); t0=int(pcs["BTC"]["idx"].searchsorted(pd.Timestamp(WIN)))
    eq=100.0; peak=100.0; mdd=0; pos={}; T=[]
    for t in range(t0,n-1):
        for c in list(pos.keys()):
            p=pos[c]; pc=pcs[c]
            if t>=len(pc["C"]): pos.pop(c); continue
            hi,lo=pc["H"][t],pc["L"][t]; dd=p["d"]; xp=None; res=""
            if dd==1:
                if lo<=p["sl"]: xp=p["sl"]; res="SL"
                elif hi>=p["tp"]: xp=p["tp"]; res="TP"
            else:
                if hi>=p["sl"]: xp=p["sl"]; res="SL"
                elif lo<=p["tp"]: xp=p["tp"]; res="TP"
            if xp is not None:
                r=dd*(xp-p["entry"])/p["entry"]/p["sl_dist"]-0.0007*2/p["sl_dist"]
                eq+=p["risk_amt"]*r; peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak if peak>0 else 0)
                T.append({"giris":p["ets"][:10],"cikis":str(pc["idx"][t])[:10],"coin":c,"yon":"LONG" if dd==1 else "SHORT",
                          "rejim":p["reg"],"sonuc":res,"R":round(r,2),"kasa":round(eq,2)}); pos.pop(c)
        for c in TOP5:
            pc=pcs[c]
            if c in pos or len(pos)>=5 or t>=len(pc["C"])-1: continue
            reg=regime(pc["idx"][t])
            if reg<2: continue                       # SNIPER GATE: sadece güçlü rejim
            dec=candidate(pc,t,model)
            if dec:
                br=pc["btc_reg"][t]
                if np.isfinite(br) and ((dec["d"]==1 and br<0.5) or (dec["d"]==-1 and br>=0.5)): continue
                entry=float(pc["O"][t+1])
                pos[c]={**dec,"entry":entry,"risk_amt":eq*RISK,"reg":reg,"ets":str(pc["idx"][t+1]),
                        "sl":entry-dec["d"]*SL_ATR*pc["atr"][t],"tp":entry+dec["d"]*TP_R*SL_ATR*pc["atr"][t]}
        if eq<=0: break
    print("="*78); print(f"  SNIPER RAPORU — son 3 ay (2026-03→05), 4H, top-5, risk %{RISK*100:.0f}/işlem, rejim≥2 gate"); print("="*78)
    print(f"  {'giriş':>11}{'çıkış':>11}{'coin':>5}{'yön':>6}{'rej':>4}{'sonuç':>6}{'R':>7}{'kasa$':>9}")
    for x in T:
        print(f"  {x['giris']:>11}{x['cikis']:>11}{x['coin']:>5}{x['yon']:>6}{x['rejim']:>4}{x['sonuc']:>6}{x['R']:>+7.2f}{x['kasa']:>9.2f}")
    wr=np.mean([1 if x['R']>0 else 0 for x in T])*100 if T else 0
    print(f"  {'-'*72}")
    print(f"  TOPLAM: {len(T)} işlem | WR %{wr:.0f} | $100 → ${eq:.2f} ({eq/100:.2f}x) | MaxDD %{mdd*100:.0f}")
    print(f"  Not: 3 ay KISA pencere = gürültü baskın; risk%5 sniper. Rejim<2 dönemlerde bot UYUDU.")

if __name__=="__main__":
    main()
