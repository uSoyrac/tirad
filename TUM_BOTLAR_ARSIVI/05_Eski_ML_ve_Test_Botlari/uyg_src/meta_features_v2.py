#!/usr/bin/env python3
"""
meta_features_v2.py — GENİŞLETİLMİŞ meta-label feature seti (edge büyütme)
═══════════════════════════════════════════════════════════════════════
v1 feature'lara (rsi/macd/adx/atr/vol/ema/roc/st/dir/sl) EKLER:
  xs_rank   — coin'in 20-coin evreninde göreceli güç percentile'i (relative strength)
  btc_reg   — BTC kendi EMA200 üstünde mi (risk-on rejim)
  btc_ret   — BTC son 10-bar getirisi (market beta bağlamı)
  trend_age — strateji yönünün kaç bardır aynı olduğu (trend olgunluğu)
  ext       — son 20-bar high/low'a uzaklık (ekstansiyon)
  volp      — ATR% rolling percentile (volatilite rejimi)
Hepsi causal. Sonra v1 vs v2 walk-forward OOS lift kıyaslanır.
"""
import json, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
from signal_lab import load_all, simulate, atr, ema, rsi, macd, sma, roc, supertrend, adx
import sig_donchian_breakout as D, sig_supertrend_regime as S
from sklearn.ensemble import HistGradientBoostingClassifier

STRATS = [("donchian", D.make_sig(40,"atr",0.25,0.0), 2.0, 2.5),
          ("supertrend", S.make_sig(10,3,25), 2.0, 3.0)]
V1 = ["rsi","macd_h","adx","atrp","vol_ratio","ema50d","ema200d","roc_s","roc_l","st_dir"]
V2_EXTRA = ["xs_rank","btc_reg","btc_ret","trend_age","ext","volp","vov"]
FEATURES_V2 = V1 + ["dir","sl_dist"] + V2_EXTRA

def coin_feats(df):
    c=df["close"].to_numpy(float); v=df["volume"].to_numpy(float)
    _,_,mh=macd(c); a=atr(df,14); ad,_,_=adx(df,14)
    e50=ema(c,50); e200=ema(c,200); vs=sma(v,20)
    hi20=pd.Series(df["high"]).rolling(20).max().to_numpy()
    lo20=pd.Series(df["low"]).rolling(20).min().to_numpy()
    ext=np.where(c>0,(c-(hi20+lo20)/2)/ (c+1e-9),0)
    atrp=a/(c+1e-9)
    volp=pd.Series(atrp).rolling(200).apply(lambda x: (x.iloc[-1]>=x).mean(), raw=False).to_numpy()
    vov=pd.Series(atrp).rolling(30).std().to_numpy()       # vol-of-vol (kazanan feature)
    return {"rsi":rsi(c,14),"macd_h":mh/(c+1e-9),"adx":ad,"atrp":atrp,"vol_ratio":v/(vs+1e-9),
            "ema50d":(c-e50)/(e50+1e-9),"ema200d":(c-e200)/(e200+1e-9),"roc_s":roc(c,6),
            "roc_l":roc(c,42),"st_dir":supertrend(df,10,3),"ext":ext,"volp":volp,"vov":vov}

def build_v2():
    dfs=load_all("mktdata","4h")
    # cross-sectional panel: tüm coin close'ları zaman-hizalı
    panel=pd.DataFrame({c:df["close"] for c,df in dfs.items()}).sort_index().ffill()
    ret30=panel.pct_change(30)                       # 30-bar getiri
    xs=ret30.rank(axis=1,pct=True)                   # her zaman: coin'in percentile rank'i
    btc=dfs["BTC"]; btc_e=btc["close"].ewm(span=200,adjust=False).mean()
    btc_reg=(btc["close"]>btc_e).astype(int); btc_ret=btc["close"].pct_change(10)
    feats={c:coin_feats(df) for c,df in dfs.items()}
    rows=[]
    for name,sig,sl,tp in STRATS:
        for c,df in dfs.items():
            pos=sig(df); fa=feats[c]; idx=df.index
            for t in simulate(df,pos,sl_atr=sl,tp_r=tp):
                fi=t["entry_i"]-1
                if fi<200 or fi>=len(df): continue
                ts=idx[fi]
                # trend_age: aynı yön kaç bar
                d=t["dir"]; age=0
                while fi-age>0 and np.sign(pos[fi-age])==np.sign(pos[fi]) and pos[fi]!=0: age+=1
                row={f:(float(fa[f][fi]) if f in fa and np.isfinite(fa[f][fi]) else np.nan) for f in V1}
                row["dir"]=d; row["sl_dist"]=t["sl_dist"]
                row["xs_rank"]=float(xs[c].get(ts,np.nan)) if ts in xs.index else np.nan
                row["btc_reg"]=float(btc_reg.get(ts,np.nan)) if ts in btc_reg.index else np.nan
                row["btc_ret"]=float(btc_ret.get(ts,np.nan)) if ts in btc_ret.index else np.nan
                row["trend_age"]=float(age); row["ext"]=float(fa["ext"][fi]) if np.isfinite(fa["ext"][fi]) else np.nan
                row["volp"]=float(fa["volp"][fi]) if np.isfinite(fa["volp"][fi]) else np.nan
                row["vov"]=float(fa["vov"][fi]) if np.isfinite(fa["vov"][fi]) else np.nan
                row.update({"r_mult":t["r_mult"],"win":1 if t["r_mult"]>0 else 0,
                            "entry_ts":t["entry_ts"],"coin":c})
                rows.append(row)
    rows.sort(key=lambda x:x["entry_ts"])
    return rows

def wf_lift(rows, feats, thr=0.35, folds=4):
    n=len(rows)
    X=np.array([[r.get(f,np.nan) for f in feats] for r in rows],float)
    y=np.array([r["win"] for r in rows]); rm=np.array([r["r_mult"] for r in rows])
    start=int(n*0.4); b=np.linspace(start,n,folds+1).astype(int)
    sel=[]; allr=[]; coins={}
    for k in range(folds):
        a,bb=b[k],b[k+1]
        clf=HistGradientBoostingClassifier(max_depth=3,max_iter=200,learning_rate=0.05,
            l2_regularization=1.0,min_samples_leaf=80,random_state=42)
        clf.fit(X[:a-20],y[:a-20]); pr=clf.predict_proba(X[a:bb])[:,1]
        for j in range(a,bb):
            allr.append(rm[j])
            if pr[j-a]>=thr: sel.append(rm[j]); coins.setdefault(rows[j]["coin"],[]).append(rm[j])
    sel=np.array(sel); allr=np.array(allr)
    pos=sum(1 for c,r in coins.items() if np.mean(r)>0)
    return {"base_e":allr.mean(),"sel_e":sel.mean() if len(sel) else 0,"sel_n":len(sel),
            "sel_wr":(sel>0).mean()*100 if len(sel) else 0,"pos":pos,"tot":len(coins)}

def main():
    rows=build_v2(); json.dump(rows,open("/tmp/meta_dataset_v2.json","w"))
    print("="*78); print(f"  META FEATURE GENİŞLETME — {len(rows)} trade"); print("="*78)
    print(f"  v1 ({len(V1)+2} feature): baseline meta-label")
    r1=wf_lift(rows, V1+["dir","sl_dist"])
    print(f"    OOS: base E={r1['base_e']:+.3f}R → meta E={r1['sel_e']:+.3f}R  (N={r1['sel_n']}, WR%{r1['sel_wr']:.0f}, {r1['pos']}/{r1['tot']} coin+)")
    print(f"  v2 ({len(FEATURES_V2)} feature: +xs_rank,btc_reg,btc_ret,trend_age,ext,volp)")
    r2=wf_lift(rows, FEATURES_V2)
    print(f"    OOS: base E={r2['base_e']:+.3f}R → meta E={r2['sel_e']:+.3f}R  (N={r2['sel_n']}, WR%{r2['sel_wr']:.0f}, {r2['pos']}/{r2['tot']} coin+)")
    lift=r2['sel_e']-r1['sel_e']
    print(f"\n  >>> v2 vs v1 edge farkı: {lift:+.3f}R  → {'YENİ FEATURE EDGE ARTIRDI ✓' if lift>0.005 else 'anlamlı artış yok'}")

if __name__=="__main__":
    main()
