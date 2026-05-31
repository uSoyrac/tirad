#!/usr/bin/env python3
"""
funding_test.py — YENİ-BİLGİ testi: funding rate meta-label edge'ini artırıyor mu?
Funding (8h, türev pozisyonlama) → 4H barlara causal hizalanır; funding feature'ları
v2+vov meta-label'a EKLENİR; walk-forward OOS lift ölçülür. OHLCV-dışı gerçek bilgi.
"""
import os, json, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
from meta_features_v2 import FEATURES_V2, wf_lift

FUND_FEATS = ["fund", "fund_z", "fund_cum", "fund_dir"]

def load_funding():
    out = {}
    for f in os.listdir("funddata"):
        if f.endswith("_funding.csv"):
            c = f.split("_")[0]
            df = pd.read_csv(f"funddata/{f}"); df["ts"] = pd.to_datetime(df["ts"])
            df = df.sort_values("ts").reset_index(drop=True)
            df["fund_z"] = (df["funding"] - df["funding"].rolling(30).mean()) / (df["funding"].rolling(30).std() + 1e-9)
            df["fund_cum"] = df["funding"].rolling(10).sum()
            out[c] = df
    return out

def main():
    rows = json.load(open("/tmp/meta_dataset_v2vov.json"))
    fund = load_funding()
    # her trade'e entry_ts'te (causal: <= entry_ts son funding) funding feature ekle
    by_coin = {}
    for r in rows:
        by_coin.setdefault(r["coin"], []).append(r)
    added = 0
    for c, rs in by_coin.items():
        if c not in fund:
            for r in rs: r["fund"]=r["fund_z"]=r["fund_cum"]=r["fund_dir"]=np.nan
            continue
        fdf = fund[c]; ft = fdf["ts"].values
        ets = pd.to_datetime([r["entry_ts"] for r in rs]).values
        idx = np.searchsorted(ft, ets, side="right") - 1     # <= entry_ts son funding (causal)
        for r, i in zip(rs, idx):
            if i < 0:
                r["fund"]=r["fund_z"]=r["fund_cum"]=r["fund_dir"]=np.nan; continue
            fv = float(fdf["funding"].iloc[i])
            r["fund"] = fv
            r["fund_z"] = float(fdf["fund_z"].iloc[i]) if np.isfinite(fdf["fund_z"].iloc[i]) else np.nan
            r["fund_cum"] = float(fdf["fund_cum"].iloc[i]) if np.isfinite(fdf["fund_cum"].iloc[i]) else np.nan
            r["fund_dir"] = fv * r["dir"]                    # long+pozitif funding = kalabalık long
            added += 1
    print("="*76); print(f"  FUNDING (yeni-bilgi) TESTİ — {added} trade'e funding eklendi"); print("="*76)
    r1 = wf_lift(rows, FEATURES_V2)
    print(f"  v2+vov (19 feat):        base {r1['base_e']:+.3f}R → meta {r1['sel_e']:+.3f}R  ({r1['pos']}/{r1['tot']} coin+)")
    r2 = wf_lift(rows, FEATURES_V2 + FUND_FEATS)
    print(f"  v2+vov+FUNDING (23 feat): base {r2['base_e']:+.3f}R → meta {r2['sel_e']:+.3f}R  ({r2['pos']}/{r2['tot']} coin+)")
    lift = r2["sel_e"] - r1["sel_e"]
    print(f"\n  >>> FUNDING lift: {lift:+.3f}R  → {'YENİ BİLGİ EDGE ARTIRDI ✓ (OHLCV tavanı kırıldı)' if lift>0.01 else 'funding anlamlı edge eklemedi'}")
    # funding-only meta (sadece funding feature'larıyla) — funding tek başına öngörücü mü?
    r3 = wf_lift(rows, ["dir","sl_dist"] + FUND_FEATS)
    print(f"  (referans: sadece funding+dir+sl → meta {r3['sel_e']:+.3f}R)")

if __name__ == "__main__":
    main()
