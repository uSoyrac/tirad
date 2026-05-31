#!/usr/bin/env python3
"""time_test.py — Seans/takvim etkisi: saat/gün/hafta-sonu/US-seansı edge'i artırıyor mu?"""
import json, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
from meta_features_v2 import FEATURES_V2, wf_lift

TIME=["hour","bar_of_day","dow","weekend","us_session","sess_sin","sess_cos"]

def main():
    rows=json.load(open("/tmp/meta_dataset_v2vov.json"))
    for r in rows:
        ts=pd.Timestamp(r["entry_ts"]); h=ts.hour; d=ts.dayofweek
        r["hour"]=float(h); r["bar_of_day"]=float(h//4); r["dow"]=float(d)
        r["weekend"]=1.0 if d>=5 else 0.0
        r["us_session"]=1.0 if 14<=h<22 else 0.0          # ~US borsa saatleri (UTC)
        r["sess_sin"]=np.sin(2*np.pi*h/24); r["sess_cos"]=np.cos(2*np.pi*h/24)  # döngüsel saat
    print("="*72); print(f"  SEANS/TAKVİM ETKİSİ TESTİ — {len(rows)} trade"); print("="*72)
    base=wf_lift(rows,FEATURES_V2)['sel_e']
    print(f"  baseline v2+vov: {base:+.3f}R")
    for f in TIME:
        e=wf_lift(rows,FEATURES_V2+[f])['sel_e']
        print(f"  +{f:11}: {e:+.3f}R ({e-base:+.3f}) {'✓' if e-base>0.005 else ''}")
    alln=wf_lift(rows,FEATURES_V2+TIME)['sel_e']
    print(f"  +HEPSİ:      {alln:+.3f}R ({alln-base:+.3f})")
    # saat bazında ham WR/beklenti (seans gerçekten farklı mı?)
    print(f"\n  4H-bar (UTC saat) bazında ham beklenti:")
    R=np.array([r["r_mult"] for r in rows]); H=np.array([pd.Timestamp(r["entry_ts"]).hour for r in rows])
    for h in [0,4,8,12,16,20]:
        m=R[H==h]
        if len(m): print(f"    saat {h:02d}:00 → {len(m):>4} işlem, WR%{(m>0).mean()*100:.0f}, ort{m.mean():+.3f}R")
    keep=[f for f in TIME if wf_lift(rows,FEATURES_V2+[f])['sel_e']-base>0.005]
    print(f"\n  >>> {'Seans EDGE EKLEDİ: '+str(keep) if keep else 'Seans/takvim OOS lift EKLEMEDİ (zayıf/arbitrajlanmış).'}")

if __name__=="__main__":
    main()
