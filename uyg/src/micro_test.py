#!/usr/bin/env python3
"""
micro_test.py — MİKROYAPI (order-flow) testi: işlem sayısı + taker-buy edge'i artırıyor mu?
Kullanıcı sezgisi: gerçek trendde katılım (trade count) ↑ ve agresif alım yönü teyit eder;
yatay/sahte harekette zayıf. Causal feature'lar meta-label'a eklenip walk-forward OOS lift.
"""
import os, json, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
from meta_features_v2 import FEATURES_V2, wf_lift

MICRO = ["nt_z","nt_roc","tbr_dev","tbr_dir","tbr_z"]

def load_micro():
    out={}
    for f in os.listdir("microdata"):
        if f.endswith("_micro.csv"):
            c=f.split("_")[0]
            df=pd.read_csv(f"microdata/{f}"); df["ts"]=pd.to_datetime(df["ts"]); df=df.sort_values("ts").reset_index(drop=True)
            nt=df["num_trades"]; tbr=df["taker_buy_ratio"]
            df["nt_z"]=(nt-nt.rolling(30).mean())/(nt.rolling(30).std()+1e-9)
            df["nt_roc"]=nt.pct_change(5)
            df["tbr_dev"]=tbr-0.5
            df["tbr_z"]=(tbr-tbr.rolling(30).mean())/(tbr.rolling(30).std()+1e-9)
            out[c]=df
    return out

def main():
    rows=json.load(open("/tmp/meta_dataset_v2vov.json"))
    micro=load_micro()
    by={}
    for r in rows: by.setdefault(r["coin"],[]).append(r)
    added=0
    for c,rs in by.items():
        if c not in micro:
            for r in rs: r.update({k:np.nan for k in MICRO}); continue
        m=micro[c]; mt=m["ts"].values
        ets=pd.to_datetime([r["entry_ts"] for r in rs]).values
        idx=np.searchsorted(mt, ets, side="left")-1   # sinyal barı (entry_ts'ten önceki kapalı bar), causal
        for r,i in zip(rs,idx):
            if i<0: r.update({k:np.nan for k in MICRO}); continue
            def g(col):
                v=m[col].iloc[i]; return float(v) if np.isfinite(v) else np.nan
            r["nt_z"]=g("nt_z"); r["nt_roc"]=g("nt_roc"); r["tbr_dev"]=g("tbr_dev"); r["tbr_z"]=g("tbr_z")
            td=g("tbr_dev"); r["tbr_dir"]=(td if np.isfinite(td) else 0.0)*r["dir"]  # alım agresyonu trade yönünü teyit ediyor mu
            added+=1
    print("="*78); print(f"  MİKROYAPI (order-flow) TESTİ — {added} trade'e işlem-sayısı+taker-buy eklendi"); print("="*78)
    base=wf_lift(rows,FEATURES_V2)['sel_e']
    print(f"  baseline v2+vov: {base:+.3f}R")
    for f in MICRO:
        e=wf_lift(rows,FEATURES_V2+[f])['sel_e']
        print(f"  +{f:9}: {e:+.3f}R ({e-base:+.3f}) {'✓' if e-base>0.005 else ''}")
    allm=wf_lift(rows,FEATURES_V2+MICRO)['sel_e']
    print(f"  +HEPSİ:    {allm:+.3f}R ({allm-base:+.3f})")
    keep=[f for f in MICRO if wf_lift(rows,FEATURES_V2+[f])['sel_e']-base>0.005]
    if keep:
        r=wf_lift(rows,FEATURES_V2+keep)
        print(f"\n  >>> Pozitif {keep}: birlikte {r['sel_e']:+.3f}R ({r['sel_e']-base:+.3f}, {r['pos']}/{r['tot']} coin+) → {'ORDER-FLOW EDGE EKLEDİ ✓' if r['sel_e']-base>0.005 else 'sönüyor'}")
    else:
        print(f"\n  >>> İşlem-sayısı/taker-buy bu trend sistemine OOS lift eklemedi.")

if __name__=="__main__":
    main()
