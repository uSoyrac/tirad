#!/usr/bin/env python3
"""
news_test.py — HABER (GDELT sentiment) edge'i artırıyor mu? Kullanıcının abduction fikri.
Günlük haber tonu+hacmi CAUSAL (bir önceki gün) hizalanır; meta-label'a eklenir; walk-forward OOS.
Haber piyasa-geneli (BTC-led) → tüm coinlere uygulanır.
"""
import json, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
from meta_features_v2 import FEATURES_V2, wf_lift

NEWS=["n_tone","n_tone_z","n_tone_chg","n_vol_z","n_tone_dir"]

def load_news():
    df=pd.read_csv("news_gdelt.csv"); df["date"]=pd.to_datetime(df["date"]); df=df.sort_values("date").reset_index(drop=True)
    df["tone"]=df["tone"].ffill(); df["vol"]=df["vol"].ffill()
    df["tone_z"]=(df["tone"]-df["tone"].rolling(30).mean())/(df["tone"].rolling(30).std()+1e-9)
    df["tone_chg"]=df["tone"].diff(3)
    df["vol_z"]=(df["vol"]-df["vol"].rolling(30).mean())/(df["vol"].rolling(30).std()+1e-9)
    return df

def main():
    rows=json.load(open("/tmp/meta_dataset_v2vov.json"))
    nw=load_news(); nd=nw["date"].values
    ets=pd.to_datetime([r["entry_ts"] for r in rows])
    # CAUSAL: trade gününden ÖNCEKİ günün haberi (aynı-gün look-ahead yok)
    entry_day=ets.normalize().values
    idx=np.searchsorted(nd, entry_day, side="left")-1
    added=0
    for r,i in zip(rows,idx):
        if i<0: r.update({k:np.nan for k in NEWS}); continue
        tone=float(nw["tone"].iloc[i]); tz=nw["tone_z"].iloc[i]; tc=nw["tone_chg"].iloc[i]; vz=nw["vol_z"].iloc[i]
        r["n_tone"]=tone if np.isfinite(tone) else np.nan
        r["n_tone_z"]=float(tz) if np.isfinite(tz) else np.nan
        r["n_tone_chg"]=float(tc) if np.isfinite(tc) else np.nan
        r["n_vol_z"]=float(vz) if np.isfinite(vz) else np.nan
        r["n_tone_dir"]=(tone if np.isfinite(tone) else 0.0)*r["dir"]   # pozitif haber + long uyumu
        added+=1
    print("="*76); print(f"  HABER (GDELT sentiment) TESTİ — {added} trade'e haber tonu eklendi (causal)"); print("="*76)
    base=wf_lift(rows,FEATURES_V2)['sel_e']
    print(f"  baseline v2+vov: {base:+.3f}R")
    for f in NEWS:
        e=wf_lift(rows,FEATURES_V2+[f])['sel_e']
        print(f"  +{f:11}: {e:+.3f}R ({e-base:+.3f}) {'✓' if e-base>0.005 else ''}")
    alln=wf_lift(rows,FEATURES_V2+NEWS)['sel_e']
    print(f"  +HEPSİ:      {alln:+.3f}R ({alln-base:+.3f})")
    keep=[f for f in NEWS if wf_lift(rows,FEATURES_V2+[f])['sel_e']-base>0.005]
    if keep:
        r=wf_lift(rows,FEATURES_V2+keep)
        print(f"\n  >>> Pozitif {keep}: birlikte {r['sel_e']:+.3f}R ({r['sel_e']-base:+.3f}, {r['pos']}/{r['tot']} coin+) → {'HABER EDGE EKLEDİ ✓' if r['sel_e']-base>0.005 else 'sönüyor'}")
    else:
        print(f"\n  >>> Haber sentiment'i bu trend sistemine OOS lift eklemedi (muhtemelen zaten fiyatlanmış).")

if __name__=="__main__":
    main()
