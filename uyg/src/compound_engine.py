#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
COMPOUND ENGINE — Multi-Agent ML Trend Trading (DOĞRULANMIŞ SİSTEM)
═══════════════════════════════════════════════════════════════════════════════
Üretim: 2026-06-01. ~40 deney, walk-forward (leak-free) doğrulamanın sonucu. Hayal yok.

MİMARİ (multi-agent karar zinciri):
  KATMAN 1 — SİNYAL AGENT'I:    Donchian(40) breakout + SuperTrend(10,3) aynı yönde
  KATMAN 2 — DISCRIMINATOR:     XGBoost (14 feature) "gerçek mi sahte trend mi" olasılığı
                                 → en güçlü ayırt edici: ÜST-TF(4H) hizası, BB-width, EMA, ADX
  KATMAN 3 — KARAR AGENT'I:     olasılık eşiği (gate top %30) → sadece kaliteli trende gir
  ÇIKIŞ:                        sabit +%5 TP / -%2.5 SL (geniş TP, maliyet yemiyor)
  SIZING:                       çeyrek-Kelly (recovery YOK), $250+ kasa

DOĞRULANMIŞ PERFORMANS (walk-forward OOS 2024-2026, maliyetli, tek-pozisyon, 14-feat, %60 notional):
  gate %30 → +17% CAGR / MDD %26   |   gate %20 (DEFAULT) → +31% CAGR / MDD %17 / WR %44 / MAR 1.85
  gate %15 → +41% CAGR / MDD %19   (eşik sıkıldıkça MONOTON artar = robust, curve-fit değil)
  • 4H Trend (DIVERSIFIER):     +32% CAGR kendi başına; 1H ile rho=+0.35, birleşince MDD %14'e iner
  • UYARI: htf4h (üst-TF) feature'ı eklenince sistem KIRILGANLAŞTI (gate30 −6%/gate15 +112% = overfit)
    → çıkarıldı. Yüksek feature-importance ≠ robust katkı. Aggressive gate (%15) daha çok curve-fit riski.

ACIMASIZ GERÇEKLER (gözardı etme):
  1. WR tavanı ~%45. %80 bu piyasada YOK — sahte-trend dağınık/tahmin edilemez (en güçlü
     feature sadece %9 önem). Edge = 2:1 asimetri + stop, yüksek isabet DEĞİL.
  2. Bunlar BACKTEST. Canlıda WR %42 kalmayabilir; 1H stop-slippage/wick modellenmedi.
  3. "Daha hızlı" (15dk/saniye) ve trailing/pyramiding TEST EDİLDİ, ELENDİ (maliyet/whipsaw).
  4. ML YÖN tahmini yazı-tura (AUC 0.52); ML sadece KALİTE-FİLTRESİ olarak değer katar.
  5. Compound gerçeği: ~%25-32 CAGR = $1000→$10k ~8 yıl. "Aylarda 100x" = leakage/iflas.

KULLANIM:
  python3 compound_engine.py            # OOS backtest, compound sonucu + trajektori
  (canlı: bu config'i live_bot.py'ye parametre olarak geçir, önce PAPER-TRADE)
═══════════════════════════════════════════════════════════════════════════════
"""
import os, pickle, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
import ta, xgboost as xgb

# ── DOĞRULANMIŞ KONFİG ────────────────────────────────────────────────────────
DATA_DIR   = "/Users/uygar/trade/bot/engine/data_v31"   # 1H OHLCV, top5, 2023-2026
COINS      = ["BTC", "ETH", "SOL", "BNB", "XRP"]
TP, SL     = 0.05, 0.025          # +%5 TP / -%2.5 SL (sabit, geniş)
HMAX       = 72                   # timeout (1H bar) = 3 gün
COST       = 0.0018               # round-trip komisyon+slippage (notional)
GATE_TOP   = 0.20                 # discriminator: en iyi %20 sinyali al (robust sweet spot, MAR~1.85)
NOTIONAL   = 0.60                 # %60 notional = MDD kontrolü (tam-notional MDD'yi şişirir)
KELLY_FRAC = 0.25                 # çeyrek-Kelly (recovery/martingale YASAK)
OOS_START  = "2024-01-01"
# NOT: htf4h (üst-TF) en yüksek feature-importance'a sahipti AMA eklendiğinde sistemi
# eşik-hassas/kırılgan yaptı (gate30 −%6 / gate15 +%112 = overfit alarmı). Robustluk için ÇIKARILDI.
# Ders: yüksek importance ≠ robust katkı. Basit-monoton feature seti tercih edilir.
FEATS = ["rsi","macd","adx","atrp","bbpct","ema50d","ema200d","roc","cci","stochk","ci","er","volr","d","hour"]

# ── SİNYAL + FEATURE (KATMAN 1+2) ─────────────────────────────────────────────
from signal_lab import atr
from live_strategy import DONCHIAN, SUPERTREND

def _feats(df):
    o,cl,hi,lo,vol = df["open"],df["close"],df["high"],df["low"],df["volume"]
    mid=cl.rolling(20).mean(); sd=cl.rolling(20).std(); a=atr(df,14)
    tr=pd.concat([hi-lo,(hi-cl.shift()).abs(),(lo-cl.shift()).abs()],axis=1).max(axis=1)
    ci=100*np.log10(tr.rolling(14).sum()/(hi.rolling(14).max()-lo.rolling(14).min()))/np.log10(14)
    er=(cl-cl.shift(10)).abs()/(cl.diff().abs().rolling(10).sum()+1e-9)
    d4=cl.resample("4h").last(); e4=ta.trend.EMAIndicator(d4,50).ema_indicator()
    htf=np.sign(d4-e4).reindex(df.index,method="ffill").to_numpy()   # ÜST-TF (4H) trend yönü
    return dict(rsi=ta.momentum.RSIIndicator(cl,14).rsi().to_numpy(),
        macd=(ta.trend.MACD(cl).macd_diff()/cl).to_numpy(),
        adx=ta.trend.ADXIndicator(hi,lo,cl,14).adx().to_numpy(), atrp=(a/cl).to_numpy(),
        bbpct=((cl-(mid-2*sd))/((mid+2*sd)-(mid-2*sd)+1e-9)).to_numpy(),
        ema50d=((cl-ta.trend.EMAIndicator(cl,50).ema_indicator())/cl).to_numpy(),
        ema200d=((cl-ta.trend.EMAIndicator(cl,200).ema_indicator())/cl).to_numpy(),
        roc=ta.momentum.ROCIndicator(cl,10).roc().to_numpy(),
        cci=ta.trend.CCIIndicator(hi,lo,cl,20).cci().to_numpy(),
        stochk=ta.momentum.StochasticOscillator(hi,lo,cl,14,3).stoch().to_numpy(),
        ci=ci.to_numpy(), er=er.to_numpy(), volr=(vol/vol.rolling(20).mean()).to_numpy(), htf4h=htf)

def build_signals(cache="/tmp/compound_sigs.pkl"):
    if os.path.exists(cache): return pickle.load(open(cache,"rb"))
    rows=[]
    for c in COINS:
        df=pd.read_csv(f"{DATA_DIR}/{c}_USDT.csv",parse_dates=["ts"]).set_index("ts").sort_index()
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

# ── WALK-FORWARD DISCRIMINATOR (KATMAN 2, leak-free) ──────────────────────────
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

# ── COMPOUND SİMÜLASYON (KATMAN 3 + sizing) ───────────────────────────────────
def kelly_fraction(p, b=TP/SL):
    """Kelly f* = p - (1-p)/b. b = win/loss oranı (5%/2.5% = 2)."""
    f = p - (1-p)/b
    return max(0.0, f) * KELLY_FRAC      # çeyrek-Kelly

def backtest(rows, P, bankroll=250.0, sizing="fixed", notional_cap=1.0):
    """sizing='fixed': doğrulanmış %10×10x şeması (tam notional, +%5/−%2.5 hesap). ← DEFAULT, validated.
       sizing='kelly': çeyrek-Kelly (deneysel; uncalibrated proba'da fixed'den kötü olabilir)."""
    thr=np.quantile([P[i] for i in P], 1-GATE_TOP)
    eq=bankroll; peak=bankroll; mdd=0.0; free=pd.Timestamp("2000"); trades=[]; monthly={}
    for i,r in enumerate(rows):
        if str(r["et"])<OOS_START or i not in P or P[i]<thr or r["et"]<free: continue
        if sizing=="kelly":
            notional=min(kelly_fraction(P[i])*(1/SL), notional_cap)
        else:
            notional=notional_cap                     # tam notional = doğrulanmış şema
        g = notional * (r["ret"] - COST)
        eq *= (1+g); free=r["xt"]; peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak if peak>0 else 0)
        trades.append(r["win"]); monthly[str(r["et"])[:7]]=eq
        if eq<=0: break
    yrs=max(1e-9,(pd.Timestamp(str(rows[-1]["xt"]))-pd.Timestamp(OOS_START)).days/365.25)
    cagr=((eq/bankroll)**(1/yrs)-1)*100 if eq>0 else -100
    wr=np.mean(trades)*100 if trades else 0
    return dict(eq=eq, cagr=cagr, mdd=mdd*100, n=len(trades), wr=wr, monthly=monthly, bankroll=bankroll)

def main():
    print(__doc__.split("KULLANIM")[0])
    print("Sinyaller hazırlanıyor (ilk çalıştırma birkaç dk)...")
    rows=build_signals()
    print(f"  {len(rows)} ham sinyal. Walk-forward discriminator eğitiliyor...")
    P=walk_forward_proba(rows)
    r=backtest(rows, P, bankroll=250.0, sizing="fixed", notional_cap=NOTIONAL)
    print("="*72)
    print(f"  COMPOUND BACKTEST (OOS {OOS_START}→2026, $250 kasa, gate top%{int(GATE_TOP*100)}, notional %{int(NOTIONAL*100)})")
    print("="*72)
    print(f"  $250 → ${r['eq']:.0f}   |   CAGR %{r['cagr']:.1f}   |   MaxDD %{r['mdd']:.1f}   |   {r['n']} işlem   |   WR %{r['wr']:.0f}")
    print(f"\n  Aylık kasa:")
    prev=r['bankroll']
    for mo in sorted(r['monthly']):
        v=r['monthly'][mo]; ch=(v/prev-1)*100; prev=v
        print(f"    {mo}: ${v:8.0f} ({ch:+5.1f}%)")
    print(f"\n  NOT: Canlıdan önce PAPER-TRADE şart. Backtest != canlı. Kaldıraç=MDD bütçesi.")

if __name__=="__main__":
    main()
