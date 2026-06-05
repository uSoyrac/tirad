#!/usr/bin/env python3
"""
faz2_features.py — KOŞULLU EDGE ANALİZİ (kullanıcının fikri: gerçek-trend vs chop)
═══════════════════════════════════════════════════════════════════════
Soru: "Hangi indikatör/veri kombinasyonu bizi en pozitif edge'e taşır?"
Özellikle: yatay piyasada SAHTE trend sinyalini elemek (chop filtresi).

Yöntem: her DOLAN trade'e, sinyal barında (look-ahead'siz) hesaplanan rejim/
türev özelliklerini ekle; sonra her özellik için "yüksek vs düşük" dilimlerde
WR/beklentiyi ölç. Hangi özellik kazananı kaybedenden ayırıyor + beklentiyi
pozitife çeviriyor? Overfit'e karşı zaman-yarısı stabilitesi kontrolü.

Aday özellikler (hepsi kullanıcının "oran/türev/range" sezgisinin karşılığı):
  ER     — Kaufman Efficiency Ratio (gerçek trend≈1, chop≈0)   ← ana hipotez
  ADX    — trend gücü
  CHOP   — Choppiness Index (yüksek=yatay)
  VROC   — hacim türevi (volume rate-of-change)                ← kullanıcı fikri
  OBVSL  — OBV eğimi (akış yönü/ivmesi)
  ATRP   — ATR% (volatilite rejimi)
  EMADIST— EMA200'e uzaklık (trend ekstansiyonu / aşırılık)
  BTCREG — BTC kendi EMA200 üstünde mi (risk-on, smart-money proxy)
"""
import os, sys, json, argparse, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
from edge_engine import simulate_fills, edge_metrics, load_df

# ── Vektörel özellik hesapları (full seri, look-ahead'siz sampling sig_i'de) ──
def feat_arrays(df):
    o = df["open"].to_numpy(float); h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float); c = df["close"].to_numpy(float)
    v = df["volume"].to_numpy(float); n = len(c)

    # Efficiency Ratio (N=10)
    N = 10
    er = np.full(n, np.nan)
    absdiff = np.abs(np.diff(c, prepend=c[0]))
    for i in range(N, n):
        denom = absdiff[i-N+1:i+1].sum()
        er[i] = abs(c[i]-c[i-N])/denom if denom > 0 else 0.0

    # ATR(14) Wilder + ADX(14)
    tr = np.maximum(h-l, np.maximum(np.abs(h-np.roll(c,1)), np.abs(l-np.roll(c,1))))
    tr[0] = h[0]-l[0]
    P = 14
    atr = pd.Series(tr).ewm(alpha=1/P, adjust=False).mean().to_numpy()
    up = h-np.roll(h,1); dn = np.roll(l,1)-l
    plus_dm = np.where((up>dn)&(up>0), up, 0.0); plus_dm[0]=0
    minus_dm = np.where((dn>up)&(dn>0), dn, 0.0); minus_dm[0]=0
    pdi = 100*pd.Series(plus_dm).ewm(alpha=1/P,adjust=False).mean().to_numpy()/np.where(atr==0,np.nan,atr)
    mdi = 100*pd.Series(minus_dm).ewm(alpha=1/P,adjust=False).mean().to_numpy()/np.where(atr==0,np.nan,atr)
    dx = 100*np.abs(pdi-mdi)/np.where((pdi+mdi)==0,np.nan,(pdi+mdi))
    adx = pd.Series(dx).ewm(alpha=1/P,adjust=False).mean().to_numpy()

    # Choppiness Index(14)
    Nc=14
    atr_sum = pd.Series(tr).rolling(Nc).sum().to_numpy()
    hh = pd.Series(h).rolling(Nc).max().to_numpy(); ll = pd.Series(l).rolling(Nc).min().to_numpy()
    rng = hh-ll
    chop = 100*np.log10(np.where(rng>0, atr_sum/np.where(rng==0,np.nan,rng), np.nan))/np.log10(Nc)

    # Volume ROC(N=5) ve OBV slope(10)
    vroc = (v-np.roll(v,5))/np.where(np.roll(v,5)==0,np.nan,np.roll(v,5))
    obv = np.cumsum(np.sign(np.diff(c, prepend=c[0]))*v)
    obvsl = np.full(n,np.nan)
    W=10
    x = np.arange(W)
    for i in range(W,n):
        y = obv[i-W:i]
        obvsl[i] = np.polyfit(x,y,1)[0]/ (np.abs(y).mean()+1e-9)

    atrp = atr/np.where(c==0,np.nan,c)
    ema200 = pd.Series(c).ewm(span=200,adjust=False).mean().to_numpy()
    emadist = (c-ema200)/np.where(ema200==0,np.nan,ema200)

    return {"ER":er, "ADX":adx, "CHOP":chop, "VROC":vroc, "OBVSL":obvsl,
            "ATRP":atrp, "EMADIST":np.abs(emadist)}


def btc_regime_map(data_dir, tf):
    path=f"{data_dir}/BTC_USDT_{tf}.csv"
    if not os.path.exists(path): return {}
    df=load_df(path); ema=df["close"].ewm(span=200,adjust=False).mean()
    return {str(ts):bool(a) for ts,a in zip(df.index, df["close"]>ema)}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data", default="mktdata"); ap.add_argument("--tf", default="4h")
    ap.add_argument("--entry", default="mid"); ap.add_argument("--timeout", type=int, default=12)
    args=ap.parse_args()
    cache=f"sigcache_{os.path.basename(args.data)}"
    cfg=dict(entry_mode=args.entry, timeout=args.timeout, runaway=False)

    coins=sorted(f.split("_")[0] for f in os.listdir(args.data) if f.endswith(f"_{args.tf}.csv"))
    coins=[c for c in coins if os.path.exists(f"{cache}/{c}_{args.tf}.json")]
    dfs={c:load_df(f"{args.data}/{c}_USDT_{args.tf}.csv") for c in coins}
    sigs={c:json.load(open(f"{cache}/{c}_{args.tf}.json")) for c in coins}
    feats={c:feat_arrays(dfs[c]) for c in coins}
    btcreg=btc_regime_map(args.data, args.tf)

    # dolan trade'leri topla + her birine sinyal-barı özelliklerini ekle
    trades=[]
    for c in coins:
        tr,_=simulate_fills(dfs[c], sigs[c], **cfg)
        idx=dfs[c].index
        for t in tr:
            i=t["sig_i"]
            for fk,arr in feats[c].items():
                t[fk]=float(arr[i]) if i<len(arr) and np.isfinite(arr[i]) else np.nan
            ts=str(idx[i]) if i<len(idx) else ""
            t["BTCREG"]=btcreg.get(ts, None)
            t["coin"]=c
            trades.append(t)
    base=edge_metrics(trades)
    print("="*90)
    print(f"  KOŞULLU EDGE ANALİZİ — {args.data}/  N={base['n']} dolan trade  (fill={args.entry} t={args.timeout})")
    print(f"  BASELINE: WR={base['wr']:.1f}%  beklenti={base['avg_r']:+.3f}R  PF={base['pf']:.2f}")
    print("="*90)

    FK=["ER","ADX","CHOP","VROC","OBVSL","ATRP","EMADIST"]
    print(f"\n  ÖZELLİK DİLİM ANALİZİ (alt %33 / orta / üst %33 → WR & beklenti):")
    print(f"  {'feat':8}{'low WR/avgR':>20}{'mid WR/avgR':>20}{'high WR/avgR':>20}{'ayrışma':>10}")
    ranked=[]
    for fk in FK:
        vals=np.array([t[fk] for t in trades], float)
        ok=np.isfinite(vals)
        if ok.sum()<30: continue
        q1,q2=np.nanpercentile(vals[ok],[33,66])
        buckets=[("low",vals<=q1),("mid",(vals>q1)&(vals<=q2)),("high",vals>q2)]
        cells=[]; hi_avg=lo_avg=None
        for name,mask in buckets:
            seg=[t for t,m in zip(trades,mask) if m]
            sm=edge_metrics(seg)
            cells.append(f"{sm.get('wr',0):.0f}%/{sm.get('avg_r',0):+.2f}")
            if name=="high": hi_avg=sm.get("avg_r",0)
            if name=="low": lo_avg=sm.get("avg_r",0)
        sep=(hi_avg-lo_avg) if hi_avg is not None and lo_avg is not None else 0
        ranked.append((fk,sep,hi_avg,lo_avg))
        print(f"  {fk:8}{cells[0]:>20}{cells[1]:>20}{cells[2]:>20}{sep:>+10.3f}")

    # BTC rejim
    on=[t for t in trades if t.get("BTCREG") is True]; off=[t for t in trades if t.get("BTCREG") is False]
    mo,mf=edge_metrics(on),edge_metrics(off)
    print(f"  {'BTCREG':8}{'OFF(risk-off)':>10} WR={mf.get('wr',0):.0f}%/avgR={mf.get('avg_r',0):+.2f}   "
          f"ON(risk-on) WR={mo.get('wr',0):.0f}%/avgR={mo.get('avg_r',0):+.2f}")

    # en ayrıştırıcı özelliği gate olarak uygula
    ranked.sort(key=lambda x:-abs(x[1]))
    print(f"\n  EN AYRIŞTIRICI ÖZELLİKLER (|yüksek-düşük beklenti farkı|):")
    for fk,sep,hi,lo in ranked[:4]:
        print(f"    {fk:8} ayrışma={sep:+.3f}  (üst dilim avgR={hi:+.3f}, alt dilim avgR={lo:+.3f})")

    if ranked:
        bf,sep,hi,lo=ranked[0]
        vals=np.array([t[bf] for t in trades],float)
        thr=np.nanpercentile(vals[np.isfinite(vals)],66)
        # gate yönü: yüksek mi düşük mü daha iyi
        if hi>=lo:
            gated=[t for t in trades if np.isfinite(t[bf]) and t[bf]>thr]; dirn=f"{bf}>{thr:.3f}"
        else:
            thr=np.nanpercentile(vals[np.isfinite(vals)],33)
            gated=[t for t in trades if np.isfinite(t[bf]) and t[bf]<thr]; dirn=f"{bf}<{thr:.3f}"
        gm=edge_metrics(gated)
        print(f"\n  >>> GATE TESTİ: en iyi özellik '{dirn}' filtresi uygula:")
        print(f"      N={gm['n']} (baz {base['n']})  WR={gm['wr']:.1f}% (baz {base['wr']:.1f})  "
              f"beklenti={gm['avg_r']:+.3f}R (baz {base['avg_r']:+.3f})  PF={gm['pf']:.2f}")
        gated.sort(key=lambda x:x["exit_ts"]); h2=len(gated)//2
        for lab,seg in [("ilk yarı",gated[:h2]),("son yarı",gated[h2:])]:
            sm=edge_metrics(seg); yr=(seg[0]["exit_ts"][:7],seg[-1]["exit_ts"][:7]) if seg else ("","")
            print(f"      {lab} [{yr[0]}→{yr[1]}]: N={sm['n']} WR={sm['wr']:.1f}% avgR={sm['avg_r']:+.3f} PF={sm['pf']:.2f}")
        verdict = "POZİTİF ✓" if gm["avg_r"]>0 else "hâlâ negatif"
        print(f"      → gate sonrası beklenti: {verdict}")


if __name__ == "__main__":
    main()
