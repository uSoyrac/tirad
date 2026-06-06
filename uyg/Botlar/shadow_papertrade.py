#!/usr/bin/env python3
"""Shadow Paper-Trade — gerçek Binance API'den canlı veri çek, sahte emirle izle.
Gerçek para YOK. Amaç: slippage, spread, dolum gerçekliğini ölçmek (DSR%31 çözümü).
Çalışma: sürekli döngü, her 1H kapanışında sinyal kontrolü, log'a yaz."""
import sys, os, json, time, logging
from datetime import datetime
import numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0,"/Users/uygar/trade/uyg/src"); sys.path.insert(0,"/tmp")

SHADOW_LOG=os.path.expanduser("~/trade/uyg/Botlar/shadow_trades.jsonl")
SHADOW_STATE=os.path.expanduser("~/trade/uyg/Botlar/shadow_state.json")

import compound_engine as E

logging.basicConfig(level=logging.INFO,format="%(asctime)s %(message)s")
log=logging.getLogger("shadow")

def load_live_1h(symbol, limit=300):
    """Binance public API — API key GEREKMEZ."""
    import ccxt
    ex=ccxt.binance({"enableRateLimit":True,"options":{"defaultType":"future"}})
    bars=ex.fetch_ohlcv(symbol+"/USDT","1h",limit=limit)
    df=pd.DataFrame(bars,columns=["ts","open","high","low","close","volume"])
    df["ts"]=pd.to_datetime(df["ts"],unit="ms"); df.set_index("ts",inplace=True)
    return df

def load_state():
    if os.path.exists(SHADOW_STATE):
        return json.load(open(SHADOW_STATE))
    return {"eq":250.0,"peak":250.0,"positions":{},"n_trades":0,"n_wins":0}

def save_state(state): json.dump(state,open(SHADOW_STATE,"w"),indent=2,default=str)

def log_trade(entry):
    with open(SHADOW_LOG,"a") as f: f.write(json.dumps(entry,default=str)+"\n")

def gen_features(df):
    """Canlı veri üzerinde compound_engine feature'larını üret."""
    import ta
    cl=df["close"]; hi=df["high"]; lo=df["low"]; vol=df["volume"]
    from signal_lab import atr; from live_strategy import DONCHIAN,SUPERTREND
    don=np.asarray(DONCHIAN(df),float); st=np.asarray(SUPERTREND(df),float)
    F={}; a=atr(df,14); mid=cl.rolling(20).mean(); sd=cl.rolling(20).std()
    F["rsi"]=ta.momentum.RSIIndicator(cl,14).rsi().to_numpy()
    F["macd"]=(ta.trend.MACD(cl).macd_diff()/cl).to_numpy()
    F["adx"]=ta.trend.ADXIndicator(hi,lo,cl,14).adx().to_numpy()
    F["atrp"]=(a/cl).to_numpy()
    F["bbpct"]=((cl-(mid-2*sd))/((mid+2*sd)-(mid-2*sd)+1e-9)).to_numpy()
    F["ema50d"]=((cl-ta.trend.EMAIndicator(cl,50).ema_indicator())/cl).to_numpy()
    F["ema200d"]=((cl-ta.trend.EMAIndicator(cl,200).ema_indicator())/cl).to_numpy()
    F["roc"]=ta.momentum.ROCIndicator(cl,10).roc().to_numpy()
    F["cci"]=ta.trend.CCIIndicator(hi,lo,cl,20).cci().to_numpy()
    F["stochk"]=ta.momentum.StochasticOscillator(hi,lo,cl,14,3).stoch().to_numpy()
    tr=pd.concat([hi-lo,(hi-cl.shift()).abs(),(lo-cl.shift()).abs()],axis=1).max(axis=1)
    ci=100*np.log10(tr.rolling(14).sum()/(hi.rolling(14).max()-lo.rolling(14).min()))/np.log10(14)
    F["ci"]=ci.to_numpy()
    F["er"]=((cl-cl.shift(10)).abs()/(cl.diff().abs().rolling(10).sum()+1e-9)).to_numpy()
    F["volr"]=(vol/vol.rolling(20).mean()).to_numpy()
    return don, st, F

def run_once(clf, thr, gate_percentile=0.20):
    """Tek kontrol turu — her 1H kapanışında çağrılır."""
    state=load_state(); pos=state["positions"]
    now=datetime.utcnow()
    signals=[]
    for c in E.COINS:
        try:
            df=load_live_1h(c,limit=250); t=-2  # son tamamlanan bar
            don,st,F=gen_features(df)
            dd=int(don[t]); ss=int(st[t]); fired=[x for x in (dd,ss) if x!=0]
            if not fired or len(set(fired))>1: continue
            d=set(fired).pop()
            x=[float(F[k][t]) if np.isfinite(F[k][t]) else np.nan for k in E.FEATS[:-2]]
            x+=[float(d),float(df.index[t].hour)]
            proba=float(clf.predict_proba(np.array([x]))[:,1][0])
            if proba>=thr:
                entry=float(df["close"].iloc[-1])
                at=float(df["close"].iloc[-1])*float(F["atrp"][t])
                signals.append(dict(c=c,d=d,entry=entry,proba=proba,
                    sl=entry-d*E.SL_ATR*at,tp=entry*(1+d*E.TP),at=at,ts=str(now)))
        except Exception as e: log.warning(f"{c}: {e}")
    # pozisyon çıkışlarını kontrol et
    to_close=[]
    for c,p in list(pos.items()):
        try:
            df=load_live_1h(c,limit=10)
            cur=float(df["close"].iloc[-1]); d=p["d"]
            if (d==1 and cur<=p["sl"]) or (d==-1 and cur>=p["sl"]): to_close.append((c,"SL",p["sl"]))
            elif (d==1 and cur>=p["tp"]) or (d==-1 and cur<=p["tp"]): to_close.append((c,"TP",p["tp"]))
        except: pass
    for c,reason,xpx in to_close:
        p=pos.pop(c); g=p["d"]*(xpx-p["entry"])/p["entry"]/p["sl_dist"]-E.COST/p["sl_dist"]
        pnl=p["risk_usd"]*g; state["eq"]+=pnl; state["peak"]=max(state["peak"],state["eq"])
        win=1 if g>0 else 0; state["n_trades"]+=1; state["n_wins"]+=win
        entry=dict(type="EXIT",reason=reason,c=c,exit_px=xpx,pnl_usd=pnl,
                   g_R=g,eq=state["eq"],ts=str(now),win=win)
        log_trade(entry); log.info(f"EXIT {reason} {c}: ${pnl:+.2f} → kasa ${state['eq']:.2f}")
    # yeni sinyaller ekle
    if signals and len(pos)<5:
        sig=max(signals,key=lambda x:x["proba"])
        if sig["c"] not in pos:
            risk_usd=state["eq"]*0.015
            sl_dist=E.SL_ATR*sig["at"]/sig["entry"]
            pos[sig["c"]]=dict(d=sig["d"],entry=sig["entry"],sl=sig["sl"],tp=sig["tp"],
                               sl_dist=sl_dist,risk_usd=risk_usd,ts=str(now),proba=sig["proba"])
            entry=dict(type="ENTRY",c=sig["c"],d="LONG" if sig["d"]==1 else "SHORT",
                       entry=sig["entry"],sl=sig["sl"],tp=sig["tp"],proba=sig["proba"],
                       eq=state["eq"],ts=str(now))
            log_trade(entry); log.info(f"ENTRY {'LONG' if sig['d']==1 else 'SHORT'} {sig['c']} @ ${sig['entry']:.2f} p={sig['proba']:.3f}")
    state["positions"]=pos; save_state(state)
    wr=state["n_wins"]/max(1,state["n_trades"])*100
    log.info(f"Kasa: ${state['eq']:.2f} | {state['n_trades']} işlem | WR %{wr:.0f} | {len(pos)} açık")
    return state

def main(loop=False):
    print("=== SHADOW PAPER-TRADE ===")
    print("Gerçek para YOK. Sadece gözlem + log.")
    print(f"Trade log: {SHADOW_LOG}")
    print("Walk-forward model yükleniyor...")
    rows=E.build_signals(); P=E.walk_forward_proba(rows)
    thr=np.quantile([P[i] for i in P],1-0.20)
    # son dönem modeli
    import xgboost as xgb
    oos="2025-01-01"
    tr=[r for r in rows if str(r["et"])<oos]
    Xtr=np.array([r["x"] for r in tr],float); ytr=np.array([r["win"] for r in tr])
    clf=xgb.XGBClassifier(n_estimators=250,max_depth=4,learning_rate=0.05,
        subsample=0.8,colsample_bytree=0.8,eval_metric="logloss",random_state=42).fit(Xtr,ytr)
    thr=np.quantile(clf.predict_proba(Xtr)[:,1],1-0.20)
    print(f"Model hazır. Gate eşiği: {thr:.4f}")
    if not loop:
        state=run_once(clf,thr); print(f"Kasa: ${state['eq']:.2f}")
    else:
        print("Döngü modu: her saat başı kontrol. Ctrl+C ile dur.")
        while True:
            try: run_once(clf,thr)
            except Exception as e: log.error(f"Hata: {e}")
            time.sleep(3600)  # 1 saat bekle

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--loop",action="store_true",help="Sürekli çalış (her 1H)")
    a=p.parse_args()
    main(loop=a.loop)
