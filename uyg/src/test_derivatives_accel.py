#!/usr/bin/env python3
"""
test_derivatives_accel.py
Hypothesis: 2nd derivative (acceleration) of Open Interest (OI) and Funding Rate 
is a strong discriminator for fakeouts.
Based on compound_engine.py and oi_ls_test.py.
"""
import os, sys, warnings
import numpy as np
import pandas as pd
import ta
import xgboost as xgb
import pickle

warnings.filterwarnings("ignore")

DATA_DIR = "/Users/uygar/trade/bot/engine/data_v31"
METRICS_DIR = "metricsdata"
FUNDING_DIR = "funddata"
COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]

TP, SL = 0.05, 0.025
HMAX = 72
OOS_START = "2024-01-01"
GATE_TOP = 0.20

FEATS = ["rsi","macd","adx","atrp","bbpct","ema50d","ema200d","roc","cci",
         "stochk","ci","er","volr","d","hour", 
         "oi_accel", "funding_accel"]  # New features added

# Import baseline signals
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from signal_lab import atr
from live_strategy import DONCHIAN, SUPERTREND

def fetch_or_load_data(coin):
    """Loads OHLCV, Metrics (OI), and Funding data."""
    # 1. OHLCV
    ohlcv_path = f"{DATA_DIR}/{coin}_USDT.csv"
    if not os.path.exists(ohlcv_path):
        return None
    df = pd.read_csv(ohlcv_path, parse_dates=["ts"]).set_index("ts").sort_index()
    
    # 2. Metrics (OI)
    metrics_path = f"{METRICS_DIR}/{coin}_metrics_4h.csv"
    if os.path.exists(metrics_path):
        mdf = pd.read_csv(metrics_path, parse_dates=["ts"]).set_index("ts").sort_index()
        # Merge by taking the last known metric value for each OHLCV bar
        mdf = mdf.reindex(df.index, method="ffill")
        df["oi"] = mdf["oi"]
    else:
        # Fallback to zeros if metrics data is missing so the script can run
        df["oi"] = np.nan
        
    # 3. Funding
    funding_path = f"{FUNDING_DIR}/{coin}_funding.csv"
    if os.path.exists(funding_path):
        fdf = pd.read_csv(funding_path, parse_dates=["ts"]).set_index("ts").sort_index()
        fdf = fdf.reindex(df.index, method="ffill")
        df["funding"] = fdf["funding"]
    else:
        df["funding"] = np.nan
        
    return df

def _feats(df):
    o,cl,hi,lo,vol = df["open"],df["close"],df["high"],df["low"],df["volume"]
    mid=cl.rolling(20).mean(); sd=cl.rolling(20).std(); a=atr(df,14)
    tr=pd.concat([hi-lo,(hi-cl.shift()).abs(),(lo-cl.shift()).abs()],axis=1).max(axis=1)
    ci=100*np.log10(tr.rolling(14).sum()/(hi.rolling(14).max()-lo.rolling(14).min()))/np.log10(14)
    er=(cl-cl.shift(10)).abs()/(cl.diff().abs().rolling(10).sum()+1e-9)
    
    # Existing features
    feats_dict = dict(
        rsi=ta.momentum.RSIIndicator(cl,14).rsi().to_numpy(),
        macd=(ta.trend.MACD(cl).macd_diff()/cl).to_numpy(),
        adx=ta.trend.ADXIndicator(hi,lo,cl,14).adx().to_numpy(), atrp=(a/cl).to_numpy(),
        bbpct=((cl-(mid-2*sd))/((mid+2*sd)-(mid-2*sd)+1e-9)).to_numpy(),
        ema50d=((cl-ta.trend.EMAIndicator(cl,50).ema_indicator())/cl).to_numpy(),
        ema200d=((cl-ta.trend.EMAIndicator(cl,200).ema_indicator())/cl).to_numpy(),
        roc=ta.momentum.ROCIndicator(cl,10).roc().to_numpy(),
        cci=ta.trend.CCIIndicator(hi,lo,cl,20).cci().to_numpy(),
        stochk=ta.momentum.StochasticOscillator(hi,lo,cl,14,3).stoch().to_numpy(),
        ci=ci.to_numpy(), er=er.to_numpy(), volr=(vol/vol.rolling(20).mean()).to_numpy()
    )
    
    # New Features: 2nd derivative (acceleration) of OI and Funding
    # We take log(oi) to normalize scale, then diff twice, or just diff().diff()
    # Funding is a rate so simple diff().diff() is fine
    # Shift by 1 is implicit if we use closed bar, but to be safe and causal:
    # df values are up to current bar close. We will use them for next bar entry.
    
    if "oi" in df.columns:
        oi_s = df["oi"]
        feats_dict["oi_accel"] = oi_s.diff().diff().to_numpy()
    else:
        feats_dict["oi_accel"] = np.zeros(len(df))
        
    if "funding" in df.columns:
        fund_s = df["funding"]
        feats_dict["funding_accel"] = fund_s.diff().diff().to_numpy()
    else:
        feats_dict["funding_accel"] = np.zeros(len(df))
        
    return feats_dict

def build_signals():
    rows=[]
    for c in COINS:
        df = fetch_or_load_data(c)
        if df is None: continue
        
        O,H,L,C=(df[k].to_numpy() for k in ["open","high","low","close"])
        don,st=DONCHIAN(df),SUPERTREND(df); F=_feats(df); idx=df.index; n=len(C)
        for t in range(220,n-1):
            fired=[x for x in (int(don[t]),int(st[t])) if x!=0]
            if not fired or len(set(fired))>1: continue
            d=set(fired).pop(); entry=O[t+1]; tp=entry*(1+d*TP); sl=entry*(1-d*SL); ret=None; ek=min(t+HMAX,n-1)
            for k in range(t+1,min(t+1+HMAX,n)):
                if d==1:
                    if L[k]<=sl: ret=-SL;ek=k;break
                    if H[k]>=tp: ret=TP;ek=k;break
                else:
                    if H[k]>=sl: ret=-SL;ek=k;break
                    if L[k]<=tp: ret=TP;ek=k;break
            if ret is None: ret=d*(C[ek]-entry)/entry
            x=[]
            for kk in FEATS:
                if kk=="d": x.append(float(d))
                elif kk=="hour": x.append(float(idx[t].hour))
                else: 
                    v=F[kk][t]
                    x.append(float(v) if t<len(F[kk]) and np.isfinite(v) else 0.0)
            rows.append(dict(c=c,et=idx[t],xt=idx[ek],ret=ret,win=int(ret>0),x=x))
    rows.sort(key=lambda r:str(r["et"])); return rows

def analyze_feature_importance(clf):
    # Get feature importances
    importances = clf.feature_importances_
    imp_dict = {f: imp for f, imp in zip(FEATS, importances)}
    sorted_imp = sorted(imp_dict.items(), key=lambda item: item[1], reverse=True)
    
    print("\n--- Feature Importances ---")
    for feat, imp in sorted_imp:
        print(f"  {feat:<15}: {imp:.4f}")
    
    return sorted_imp

def walk_forward_proba(rows, test_years=("2024","2025","2026")):
    P={}
    feature_importances = []
    
    for y in test_years:
        tr=[r for r in rows if str(r["et"])[:4]<y]; te=[r for r in rows if str(r["et"])[:4]==y]
        if len(tr)<300 or not te: continue
        clf=xgb.XGBClassifier(n_estimators=250,max_depth=4,learning_rate=0.05,subsample=0.8,
            colsample_bytree=0.8,eval_metric="logloss",random_state=42).fit(
            np.array([r["x"] for r in tr]), np.array([r["win"] for r in tr]))
        
        print(f"\nModel trained for year {y}")
        analyze_feature_importance(clf)
        
        for i,r in enumerate(rows):
            if str(r["et"])[:4]==y: P[i]=float(clf.predict_proba(np.array([r["x"]]))[:,1][0])
    return P

def backtest(rows, P, bankroll=250.0):
    thr=np.quantile([P[i] for i in P], 1-GATE_TOP)
    eq=bankroll; peak=bankroll; mdd=0.0; trades=[]
    for i,r in enumerate(rows):
        if str(r["et"])<OOS_START or i not in P or P[i]<thr: continue
        g = 0.60 * (r["ret"] - 0.0018) # Notional 60%, Cost 0.18%
        eq *= (1+g); peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak if peak>0 else 0)
        trades.append(r["win"])
        if eq<=0: break
    
    yrs=max(1e-9,(pd.Timestamp(str(rows[-1]["xt"]))-pd.Timestamp(OOS_START)).days/365.25)
    cagr=((eq/bankroll)**(1/yrs)-1)*100 if eq>0 else -100
    wr=np.mean(trades)*100 if trades else 0
    return dict(eq=eq, cagr=cagr, mdd=mdd*100, n=len(trades), wr=wr)

def main():
    print("Building signals with OI/Funding acceleration features...")
    rows = build_signals()
    if not rows:
        print("No signals generated. Make sure data exists.")
        return
        
    print(f"Generated {len(rows)} signals. Running XGBoost...")
    P = walk_forward_proba(rows)
    
    if not P:
        print("Not enough data to train model.")
        return
        
    res = backtest(rows, P)
    print("\n" + "="*60)
    print("BACKTEST RESULT (With OI & Funding Accel)")
    print("="*60)
    print(f"CAGR : {res['cagr']:.2f}%")
    print(f"MaxDD: {res['mdd']:.2f}%")
    print(f"Win% : {res['wr']:.2f}%")
    print(f"Trades: {res['n']}")
    print("="*60)

if __name__ == "__main__":
    main()
