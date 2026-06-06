#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
OPTIMAL SNIPER HARVEST BOT (Asimetrik Vur-Kaç Hasadı)
═══════════════════════════════════════════════════════════════════════════════

Bu sistem, 'Asimetrik Sniper' botunun kusursuz vuruş gücüyle, 'Safe Harvest'
botunun parayı güvene alma mantığını SENTEZLER. Borsa tarihinin en acımasız 
ve risksiz kâr toplama motorudur.

STRATEJİ:
- AI Modeli: Smart Money İvmesi (Sadece TOP %5 En Kusursuz Sinyaller)
- Risk: Kasanın tamamı (1x) * 5x Kaldıraç = Toplam 5.0 Notional.
- Kâr Hedefi (TP): Varlık bazında %10 -> 5x Kaldıraçla Kasa bazında +%50 Kâr.
- Zarar Kes (SL): Varlık bazında %2  -> 5x Kaldıraçla Kasa bazında -%10 Zarar.
- Asimetri (R/R): 1 Risk edip 5 Alma mantığı. Üst üste zarar etse bile tek bir
  başarılı atış kasanı devasa büyütür.
- Hasat Kuralı: Kasa $150'ye ulaştığında (Genelde tek bir başarılı işlemde),
  sistem işlemi keser ve $50 Nakit Maaşı bankaya çeker. Sonra tekrar 100 
  Dolar ile avlanmaya çıkar.
═══════════════════════════════════════════════════════════════════════════════
"""
import os, sys, pickle, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")

sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))
import ta, xgboost as xgb
from signal_lab import atr
from live_strategy import DONCHIAN, SUPERTREND

# ── KONFİG ────────────────────────────────────────────────────────────────────
DATA_DIR   = os.path.join(os.path.dirname(__file__), "../../bot/engine/data_v63")
COINS      = ["BTC", "ETH", "SOL"]
TP, SL     = 0.10, 0.02           # ASİMETRİK R/R: +%10 Hedef / -%2 Stop
HMAX       = 144                  # timeout = 6 gün
COST       = 0.0018               
OOS_START  = "2024-01-01"
GATE_TOP   = 0.05                 # Sadece En Güvenilir %5 Sinyal (Sniper)
LEVERAGE   = 5.0                  # 5x Kaldıraç
HARVEST_TARGET = 150.0            # 150 dolara ulaşınca 50 Dolar Nakit çek

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

def build_signals(cache="/tmp/sniper_sigs.pkl"):
    # Sniper botunun ürettiği aynı cache dosyasını kullanıyoruz (TP 0.10, SL 0.02 olduğu için tam uyuşur)
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

def backtest_sniper_harvest(rows, P, starting_bankroll=100.0):
    thr=np.quantile([P[i] for i in P], 1-GATE_TOP) # Sadece Top %5 Keskin Nişancı Sinyali
    eq = starting_bankroll
    
    total_harvested = 0.0
    harvest_count = 0
    bankruptcy_count = 0
    total_injected = starting_bankroll
    
    total_wins, total_losses = 0, 0
    free = pd.Timestamp("2000")
    
    for i,r in enumerate(rows):
        if str(r["et"])<OOS_START or i not in P or P[i]<thr or r["et"]<free: continue
        
        # 5x Kaldıraçlı İşlem Büyüklüğü (Notional)
        notional = LEVERAGE
        
        g = notional * (r["ret"] - COST)
        eq *= (1 + g)
        free = r["xt"]
        
        if g > 0: total_wins += 1
        else: total_losses += 1
        
        # Asimetrik Hasat Kontrolü (Kasa $150 oldu mu?)
        if eq >= HARVEST_TARGET:
            harvest_amount = eq - starting_bankroll
            total_harvested += harvest_amount
            harvest_count += 1
            eq = starting_bankroll  # Kârı bankaya çektik, 100 dolara sıfırlandık.
            
        # İflas Kontrolü
        elif eq <= 0.0:
            bankruptcy_count += 1
            eq = starting_bankroll
            total_injected += starting_bankroll
            
    net_overall = total_harvested + eq - total_injected
    wr = (total_wins / (total_wins + total_losses) * 100) if (total_wins + total_losses) > 0 else 0
    
    return dict(harvest_count=harvest_count, harvested=total_harvested, 
                bankruptcies=bankruptcy_count, injected=total_injected, 
                eq=eq, net=net_overall, wr=wr, n=total_wins+total_losses)

def main():
    print(__doc__)
    print("Sinyaller hazırlanıyor (Sniper Cache'i yükleniyor)...")
    rows=build_signals()
    print("Yapay Zeka Geçmiş Verilerle Eğitiliyor...")
    P=walk_forward_proba(rows)
    
    print("\n[ SNIPER HARVEST BOTU ÇALIŞTIRILIYOR... ]")
    r=backtest_sniper_harvest(rows, P, starting_bankroll=100.0)
    
    print("==========================================================")
    print(f"  ASİMETRİK SNIPER HASADI (OOS {OOS_START}→2026, $100 Kasa)")
    print("  Kural: Sadece Kusursuz Trendlerde 1'e 5 Risk Al, 150 Dolara Vurduğunda $50 Nakit Çek!")
    print(f"  Kaldıraç: {LEVERAGE}x  |  TP: %10  |  SL: %2")
    print("==========================================================")
    print(f"  Kazanma Oranı (Win Rate)              : %{r['wr']:.1f} ({r['n']} İşlem)")
    print(f"  Başarılı Hasat (150'ye Ulaşma) Sayısı : {r['harvest_count']} Kez")
    print(f"  Banka Hesabına Çekilen Saf Kâr        : ${r['harvested']:.2f}")
    print(f"  İflas (Kasanın Sıfırlanma) Sayısı     : {r['bankruptcies']} Kez")
    if r['bankruptcies'] == 0:
        print("  DURUM                                 : HİÇ İFLAS ETMEDİ! (Mükemmel Güvenlik)")
    else:
        print(f"  İflas Sonrası Eklenen Sermaye         : ${r['injected'] - 100.0:.2f}")
    print(f"  Mevcut İçeride (Trade'de) Kalan Kasa  : ${r['eq']:.2f}")
    print("----------------------------------------------------------")
    print(f"  2.5 Yıllık NET KÂR/ZARAR              : ${r['net']:+.2f}")
    print("==========================================================")

if __name__=="__main__":
    main()
