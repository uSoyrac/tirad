#!/usr/bin/env python3
"""
direction_test.py — "ML YÖNÜ tahmin edebilir mi?" KESİN testi
═══════════════════════════════════════════════════════════════════════
Elimizdeki TÜM veri (fiyat/hacim/funding/order-flow/vov...) en güçlü ML'e verilir,
hedef: sonraki K-bar hareketinin YÖNÜ (yukarı/aşağı). Walk-forward OOS doğruluk.
>%55 = ML yönü biliyor (kurtarır). ~%50 = yazı-tura (kurtarmaz, edge payoff'tan gelir).
"""
import os, json, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
from signal_lab import load_all, rsi, macd, atr, adx, ema, sma, roc, supertrend, bollinger
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

TOP5=["BTC","ETH","SOL","BNB","XRP"]; K=6   # 6 bar = 1 gün ileri yön

def feats(df, micro):
    c=df["close"].to_numpy(float); h=df["high"].to_numpy(float); l=df["low"].to_numpy(float); v=df["volume"].to_numpy(float)
    _,_,mh=macd(c); a=atr(df,14); ad,pdi,mdi=adx(df,14); e50=ema(c,50); e200=ema(c,200); vs=sma(v,20)
    m,bu,bl=bollinger(c,20,2); atrp=a/(c+1e-9)
    F={"rsi":rsi(c,14),"macd_h":mh/(c+1e-9),"adx":ad,"pdi":pdi,"mdi":mdi,"atrp":atrp,
       "vol_ratio":v/(vs+1e-9),"ema50d":(c-e50)/(e50+1e-9),"ema200d":(c-e200)/(e200+1e-9),
       "roc_s":roc(c,6),"roc_l":roc(c,42),"st_dir":supertrend(df,10,3),
       "bb_pos":(c-m)/(bu-bl+1e-9),"vov":pd.Series(atrp).rolling(30).std().to_numpy()}
    if micro is not None:
        idx=df.index
        nt=micro.set_index("ts")["num_trades"].reindex(idx).to_numpy()
        tb=micro.set_index("ts")["taker_buy_ratio"].reindex(idx).to_numpy()
        F["nt_z"]=(nt-pd.Series(nt).rolling(30).mean().to_numpy())/(pd.Series(nt).rolling(30).std().to_numpy()+1e-9)
        F["taker"]=tb-0.5
    return F

def main():
    dfs=load_all("mktdata","4h")
    X_all=[]; y_all=[]; ts_all=[]
    for c in TOP5:
        df=dfs[c]; cl=df["close"].to_numpy(float)
        mic=None
        if os.path.exists(f"microdata/{c}_micro.csv"):
            mic=pd.read_csv(f"microdata/{c}_micro.csv"); mic["ts"]=pd.to_datetime(mic["ts"])
        F=feats(df,mic); cols=list(F)
        fwd=np.full(len(cl),np.nan)
        fwd[:-K]=cl[K:]/cl[:-K]-1.0          # K-bar ileri getiri
        for i in range(250,len(cl)-K):
            row=[F[k][i] for k in cols]
            if any(not np.isfinite(x) for x in row) or not np.isfinite(fwd[i]): continue
            X_all.append(row); y_all.append(1 if fwd[i]>0 else 0); ts_all.append(df.index[i])
    X=np.array(X_all); y=np.array(y_all); ts=np.array(ts_all)
    order=np.argsort(ts); X,y=X[order],y[order]
    print("="*70); print(f"  ML YÖN TAHMİNİ — {len(X)} örnek, {X.shape[1]} feature (TÜM veri)"); print("="*70)
    print(f"  Hedef: {K}-bar (1 gün) ileri yön (yukarı=%{y.mean()*100:.0f})")
    # walk-forward 4 fold OOS doğruluk
    n=len(X); start=int(n*0.4); b=np.linspace(start,n,5).astype(int); accs=[]; aucs=[]
    for k in range(4):
        a_,bb=b[k],b[k+1]
        clf=HistGradientBoostingClassifier(max_depth=4,max_iter=300,learning_rate=0.05,l2_regularization=1.0,min_samples_leaf=100,random_state=42)
        clf.fit(X[:a_],y[:a_]); p=clf.predict_proba(X[a_:bb])[:,1]; pred=(p>=0.5).astype(int)
        acc=(pred==y[a_:bb]).mean()*100; auc=roc_auc_score(y[a_:bb],p)
        accs.append(acc); aucs.append(auc)
        print(f"  Fold {k+1}: OOS doğruluk %{acc:.1f}  AUC {auc:.3f}")
    print(f"  ─────────────────────────────")
    print(f"  ORTALAMA OOS doğruluk: %{np.mean(accs):.1f}  (yazı-tura = %50)  AUC {np.mean(aucs):.3f} (rastgele=0.50)")
    verdict = "ML YÖNÜ BİLİYOR ✓ (kurtarır)" if np.mean(accs)>=55 else "ML YÖNÜ BİLEMİYOR — ~yazı-tura (kurtarmaz; edge payoff asimetrisinden gelir)"
    print(f"  >>> SONUÇ: {verdict}")

if __name__=="__main__":
    main()
