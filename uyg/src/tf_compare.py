#!/usr/bin/env python3
"""tf_compare.py — Aynı sistem (donchian+supertrend agreement) 1H vs 4H vs 1D. Kâr artar mı?"""
import numpy as np, pandas as pd, warnings, os
warnings.filterwarnings("ignore")
from signal_lab import simulate, metrics, donchian, supertrend, atr

TOP5=["BTC","ETH","SOL","BNB","XRP"]
BPY={"1h":24*365,"4h":6*365,"1d":365}

def agree_sig(df):
    h=df["high"].to_numpy(float); l=df["low"].to_numpy(float); c=df["close"].to_numpy(float)
    dh,dl=donchian(df,40); st=supertrend(df,10,3)
    pos=np.zeros(len(c))
    for i in range(40,len(c)):
        don=1 if c[i]>dh[i-1] else (-1 if c[i]<dl[i-1] else 0)
        if don!=0 and don==st[i]: pos[i]=don
    return pos

def main():
    print("="*74); print("  ZAMAN DİLİMİ KARŞILAŞTIRMASI — donchian+supertrend agreement, top-5"); print("="*74)
    print(f"  {'TF':>4}{'işlem':>7}{'freq/yr':>9}{'WR%':>6}{'beklenti':>10}{'OOS test':>10}{'~yıllık ret':>13}")
    W0=pd.Timestamp("2025-05-01")            # son ~1 yıl penceresi (adil kıyas)
    for tf in ["1h","4h","1d"]:
        pool=[]; span=0
        ok=True
        for c in TOP5:
            p=f"mktdata/{c}_USDT_{tf}_1y.csv" if tf in ("1h","1d") else f"mktdata/{c}_USDT_{tf}.csv"
            if not os.path.exists(p): ok=False; break
            df=pd.read_csv(p); df["ts"]=pd.to_datetime(df["ts"]); df=df.set_index("ts").sort_index()
            df=df[df.index>=W0]               # son 1 yıl
            tr=simulate(df, agree_sig(df), sl_atr=2.0, tp_r=2.75)
            pool+=tr; span=max(span,len(df))
        if not ok:
            print(f"  {tf:>4}  (veri yok)"); continue
        m=metrics(pool)
        # OOS test (son %40)
        pool.sort(key=lambda x:x["exit_ts"]); te=metrics(pool[int(len(pool)*0.6):])
        freq=m["n"]/(span/BPY[tf])
        # kaba yıllık getiri: freq × beklenti × %1 risk (bileşiksiz ilk-mertebe)
        ann=freq*m["avg_r"]*0.01*100
        print(f"  {tf:>4}{m['n']:>7}{freq:>9.0f}{m['wr']:>6.1f}{m['avg_r']:>+10.3f}{te.get('avg_r',0):>+10.3f}{ann:>+12.0f}%")
    print(f"\n  Not: 'beklenti' işlem başı R (maliyet dahil). 'yıllık ret' = freq×beklenti×%1risk (kaba, bileşiksiz).")
    print(f"  Yüksek frekans × düşük beklenti vs düşük frekans × yüksek beklenti dengesi burada görünür.")

if __name__=="__main__":
    main()
