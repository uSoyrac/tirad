#!/usr/bin/env python3
"""
GRID SEARCH OPTIMIZER FOR KELLY HARVEST
"""
import os, sys, pickle, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")

sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))
import ta, xgboost as xgb
from signal_lab import atr
from live_strategy import DONCHIAN, SUPERTREND

DATA_DIR   = os.path.join(os.path.dirname(__file__), "../../bot/engine/data_v63")
COINS      = ["BTC", "ETH", "SOL"]
TP, SL     = 0.05, 0.025
HMAX       = 72
COST       = 0.0018               
OOS_START  = "2024-01-01"
GATE_TOP   = 0.20

FEATS = ["rsi","macd","adx","atrp","bbpct","ema50d","ema200d","roc","cci","stochk","ci","er","volr","d","hour", "ts_accel", "tbr_accel"]

def _feats(df):
    o,cl,hi,lo,vol = df["open"],df["close"],df["high"],df["low"],df["volume"]
    mid=cl.rolling(20).mean(); sd=cl.rolling(20).std(); a=atr(df,14)
    tr=pd.concat([hi-lo,(hi-cl.shift()).abs(),(lo-cl.shift()).abs()],axis=1).max(axis=1)
    ci=100*np.log10(tr.rolling(14).sum()/(hi.rolling(14).max()-lo.rolling(14).min()))/np.log10(14)
    er=(cl-cl.shift(10)).abs()/(cl.diff().abs().rolling(10).sum()+1e-9)
    d4=cl.resample("4h").last(); e4=ta.trend.EMAIndicator(d4,50).ema_indicator()
    htf=np.sign(d4-e4).reindex(df.index,method="ffill").to_numpy()
    
    trade_size = df["volume"] / (df["number_of_trades"] + 1e-9)
    ts_accel = trade_size.diff().diff()
    taker_buy_ratio = df["taker_buy_base_asset_volume"] / (df["volume"] + 1e-9)
    tbr_accel = taker_buy_ratio.diff().diff()
    
    return dict(rsi=ta.momentum.RSIIndicator(cl,14).rsi().to_numpy(),
        macd=(ta.trend.MACD(cl).macd_diff()/cl).to_numpy(),
        adx=ta.trend.ADXIndicator(hi,lo,cl,14).adx().to_numpy(), atrp=(pd.Series(a)/cl).to_numpy(),
        bbpct=((cl-(mid-2*sd))/((mid+2*sd)-(mid-2*sd)+1e-9)).to_numpy(),
        ema50d=((cl-ta.trend.EMAIndicator(cl,50).ema_indicator())/cl).to_numpy(),
        ema200d=((cl-ta.trend.EMAIndicator(cl,200).ema_indicator())/cl).to_numpy(),
        roc=ta.momentum.ROCIndicator(cl,10).roc().to_numpy(),
        cci=ta.trend.CCIIndicator(hi,lo,cl,20).cci().to_numpy(),
        stochk=ta.momentum.StochasticOscillator(hi,lo,cl,14,3).stoch().to_numpy(),
        ci=ci.to_numpy(), er=er.to_numpy(), volr=(vol/vol.rolling(20).mean()).to_numpy(), htf4h=htf,
        ts_accel=ts_accel.to_numpy(), tbr_accel=tbr_accel.to_numpy())

def build_signals(cache="/tmp/smartmoney_sigs.pkl"):
    if os.path.exists(cache): return pickle.load(open(cache,"rb"))
    rows=[]
    for c in COINS:
        file_path = f"{DATA_DIR}/{c}_USDT.csv"
        if not os.path.exists(file_path): continue
        df=pd.read_csv(file_path,parse_dates=["ts"]).set_index("ts").sort_index()
        if len(df) > 1 and (df.index[1] - df.index[0]).seconds < 3600:
            df = df.resample("1h").agg({
                "open": "first", "high": "max", "low": "min", "close": "last",
                "volume": "sum", "quote_asset_volume": "sum", "number_of_trades": "sum",
                "taker_buy_base_asset_volume": "sum"
            }).dropna()
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
                elif kk=="htf4h": x.append(float(d)*F["htf4h"][t] if np.isfinite(F["htf4h"][t]) else 0.0)
                else: v=F[kk][t]; x.append(float(v) if t<len(F[kk]) and np.isfinite(v) else np.nan)
            rows.append(dict(c=c,et=idx[t],xt=idx[ek],ret=ret,win=int(ret>0),x=x))
    rows.sort(key=lambda r:str(r["et"])); pickle.dump(rows,open(cache,"wb")); return rows

def walk_forward_proba(rows, test_years=("2024","2025","2026")):
    P={}
    for y in test_years:
        tr=[r for r in rows if str(r["et"])[:4]<y]; te=[r for r in rows if str(r["et"])[:4]==y]
        if len(tr)<300 or not te: continue
        clf=xgb.XGBClassifier(n_estimators=250,max_depth=4,learning_rate=0.05,subsample=0.8,
            colsample_bytree=0.8,eval_metric="logloss",random_state=42).fit(
            np.array([r["x"] for r in tr]), np.array([r["win"] for r in tr]))
        for i,r in enumerate(rows):
            if str(r["et"])[:4]==y: P[i]=float(clf.predict_proba(np.array([r["x"]]))[:,1][0])
    return P

def backtest_kelly_harvest(rows, P, starting_bankroll=100.0, target_harvest=120.0, max_lev=8.0):
    thr=np.quantile([P[i] for i in P], 1-GATE_TOP)
    eq = starting_bankroll
    
    total_harvested = 0.0
    harvest_count = 0
    bankruptcy_count = 0
    
    free = pd.Timestamp("2000")
    
    for i,r in enumerate(rows):
        if str(r["et"])<OOS_START or i not in P or P[i]<thr or r["et"]<free: continue
        
        prob = P[i]
        kelly_fraction = max(0.1, prob - ((1.0 - prob) / 2.0))
        
        dynamic_leverage = min(max_lev, kelly_fraction * 15.0)
        notional = dynamic_leverage
        
        g = notional * (r["ret"] - COST)
        eq *= (1 + g)
        free = r["xt"]
        
        if eq >= target_harvest:
            harvest_amount = eq - starting_bankroll
            total_harvested += harvest_amount
            harvest_count += 1
            eq = starting_bankroll
            
        elif eq <= 0.0:
            bankruptcy_count += 1
            eq = starting_bankroll
            
    return dict(harvest_count=harvest_count, harvested=total_harvested, 
                bankruptcies=bankruptcy_count, eq=eq)

def main():
    rows=build_signals()
    P=walk_forward_proba(rows)
    
    harvest_targets = [110.0, 115.0, 120.0, 130.0, 150.0]
    max_leverages = [5.0, 8.0, 10.0, 12.0, 15.0]
    
    results = []
    
    for ht in harvest_targets:
        for ml in max_leverages:
            r = backtest_kelly_harvest(rows, P, target_harvest=ht, max_lev=ml)
            results.append((ht, ml, r['harvest_count'], r['harvested'], r['bankruptcies'], r['eq']))
            
    # Sadece İFLAS ETMEYEN (bankruptcies == 0) kombinasyonları kâra göre sıralayalım
    valid = [x for x in results if x[4] == 0]
    valid.sort(key=lambda x: x[3], reverse=True)
    
    print("\n" + "="*70)
    print(" EN İYİ 'SIFIR İFLAS' HASAT KOMBİNASYONLARI (GRID SEARCH)")
    print("="*70)
    print(f"{'Hasat Hedefi':<15} | {'Max Kaldıraç':<15} | {'Maaş Sayısı':<15} | {'Toplam Kâr ($)':<15}")
    print("-"*70)
    
    for i, v in enumerate(valid[:10]):
        print(f"${v[0]:<14.1f} | {v[1]:<14.1f} | {v[2]:<15} | ${v[3]:<14.2f}")
        
    if not valid:
        print("Sıfır iflas veren kombinasyon bulunamadı (Çok riskli).")

if __name__=="__main__":
    main()
