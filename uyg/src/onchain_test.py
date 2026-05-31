#!/usr/bin/env python3
"""
onchain_test.py — ON-CHAIN yeni-bilgi testi: stablecoin arz akışı (likidite rejimi)
═══════════════════════════════════════════════════════════════════════
DefiLlama'dan toplam stablecoin dolaşımı (8.5y, ücretsiz). Flow = arz büyüme hızı
= kriptoya para giriş/çıkış (smart-money likidite). OHLCV'de YOK.
Feature: stbl_g7 (7g büyüme), stbl_g30 (30g), stbl_z (z-skor). Meta-label'a eklenip OOS lift.
"""
import json, urllib.request, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
from meta_features_v2 import FEATURES_V2, wf_lift

STBL = ["stbl_g7","stbl_g30","stbl_z","stbl_g7_dir"]

def fetch_stablecoin():
    req=urllib.request.Request("https://stablecoins.llama.fi/stablecoincharts/all?stablecoin=1",
                               headers={"User-Agent":"Mozilla/5.0"})
    d=json.loads(urllib.request.urlopen(req,timeout=20).read())
    ts=pd.to_datetime([int(x["date"]) for x in d], unit="s")
    val=[float(x["totalCirculatingUSD"]["peggedUSD"]) for x in d]
    s=pd.Series(val, index=ts).sort_index()
    df=pd.DataFrame({"supply":s})
    df["g7"]=s.pct_change(7); df["g30"]=s.pct_change(30)
    df["z"]=(df["g7"]-df["g7"].rolling(90).mean())/(df["g7"].rolling(90).std()+1e-9)
    return df

def main():
    rows=json.load(open("/tmp/meta_dataset_v2vov.json"))
    sd=fetch_stablecoin(); st=sd.index.values
    ets=pd.to_datetime([r["entry_ts"] for r in rows]).values
    idx=np.searchsorted(st, ets, side="right")-1     # causal: <= entry_ts son stablecoin günü
    for r,i in zip(rows, idx):
        if i<0: r.update({k:np.nan for k in STBL}); continue
        g7=sd["g7"].iloc[i]; g30=sd["g30"].iloc[i]; z=sd["z"].iloc[i]
        r["stbl_g7"]=float(g7) if np.isfinite(g7) else np.nan
        r["stbl_g30"]=float(g30) if np.isfinite(g30) else np.nan
        r["stbl_z"]=float(z) if np.isfinite(z) else np.nan
        r["stbl_g7_dir"]=(float(g7) if np.isfinite(g7) else 0.0)*r["dir"]  # büyüyen likidite + long uyumu
    print("="*76); print(f"  ON-CHAIN STABLECOIN AKIŞI TESTİ — {sum(1 for r in rows if np.isfinite(r.get('stbl_g7',np.nan)))} trade"); print("="*76)
    base=wf_lift(rows,FEATURES_V2)['sel_e']
    print(f"  baseline v2+vov: {base:+.3f}R")
    for f in STBL:
        e=wf_lift(rows,FEATURES_V2+[f])['sel_e']
        print(f"  +{f:12}: {e:+.3f}R ({e-base:+.3f}) {'✓' if e-base>0.005 else ''}")
    alls=wf_lift(rows,FEATURES_V2+STBL)['sel_e']
    print(f"  +HEPSİ:        {alls:+.3f}R ({alls-base:+.3f})")
    keep=[f for f in STBL if wf_lift(rows,FEATURES_V2+[f])['sel_e']-base>0.005]
    if keep:
        eg=wf_lift(rows,FEATURES_V2+keep)['sel_e']
        print(f"\n  >>> Pozitif {keep}: birlikte {eg:+.3f}R ({eg-base:+.3f}) → {'ON-CHAIN EDGE EKLEDİ ✓' if eg-base>0.005 else 'sönüyor'}")
    else:
        print(f"\n  >>> Stablecoin akışı bu trend sistemine OOS lift eklemedi.")

if __name__=="__main__":
    main()
