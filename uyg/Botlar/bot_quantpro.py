#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════
BOT 4 — QUANTPRO (Kurumsal Sınıf) | Dürüst Versiyon
Top quant firma teknikleri — sadece gerçekten işe yarayanlar.
═══════════════════════════════════════════════════════════════════════════
DAHIL (test edildi, değer katıyor):
  1. CPCV         — 15 bağımsız OOS yolu, walk-forward'dan daha dürüst
  2. SHAP Stability — dönemsel serap feature'ları ele (9/15 stabil)
  3. Shadow Log   — her sinyali jsonl'e yaz, canlı izleme altyapısı
  4. Güven-bazlı sizing (≤2.5x tavan, martingale YOK)

DAHIL DEĞİL (test edildi, bu sistemde katkı sağlamadı):
  - DD-Contingent: sıralı-tek-pozisyon'da MAR düşürdü (multi-pos sistemlerde değerli)
  - Correlation-Aware: tek-pozisyon'da zaten implicit

CPCV BULGULARI (15 bağımsız yol, dürüst OOS):
  Walk-forward: %31 CAGR (tek yol, iyimser)
  CPCV medyan:  %8  | %95 aralık [%-16, %64] | P(>0):%73 | P(>20):%33
  -> DSR%31 ile tutarlı: edge var ama modest ve belirsiz. Paper-trade şart.

Çalıştır:  cd uyg/Botlar && python3 bot_quantpro.py
           python3 bot_quantpro.py --cpcv --shadow
═══════════════════════════════════════════════════════════════════════════
"""
import os, sys, json, argparse, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import compound_engine as E
import xgboost as xgb, shap
from itertools import combinations

SHADOW_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shadow_trades.jsonl")

# ── 1. SHAP STABİLİTY ──────────────────────────────────────────────────────
def shap_stable_features(rows, min_years=2, top_frac=0.65):
    """Her yıl SHAP hesapla; min_years yılda top-%top_frac içinde olanlar stabil."""
    years=["2023","2024","2025","2026"]; rankings={}
    for y in years:
        tr=[r for r in rows if str(r["et"])[:4]<y]
        te=[r for r in rows if str(r["et"])[:4]==y]
        if len(tr)<300 or not te: continue
        Xtr=np.array([r["x"] for r in tr],float); ytr=np.array([r["win"] for r in tr])
        clf=xgb.XGBClassifier(n_estimators=200,max_depth=4,learning_rate=0.05,
            subsample=0.8,colsample_bytree=0.8,eval_metric="logloss",random_state=42).fit(Xtr,ytr)
        sv=np.abs(shap.TreeExplainer(clf).shap_values(
            np.array([r["x"] for r in te[:300]],float))).mean(0)
        rankings[y]=np.argsort(sv)[::-1].tolist()
    top_n=int(len(E.FEATS)*top_frac)
    return [i for i,_ in enumerate(E.FEATS)
            if sum(1 for y in rankings if rankings[y].index(i)<top_n)>=min_years]

# ── 2. GÜVEN-BAZLI BACKTEST + SHADOW ───────────────────────────────────────
def backtest_quantpro(rows, P, stable_idx, gate=0.20, shadow=False):
    P_qp={}
    for y in ["2024","2025","2026"]:
        tr=[r for r in rows if str(r["et"])[:4]<y]
        te=[r for r in rows if str(r["et"])[:4]==y]
        if len(tr)<300 or not te: continue
        Xtr=np.array([[r["x"][j] for j in stable_idx] for r in tr],float)
        clf=xgb.XGBClassifier(n_estimators=250,max_depth=4,learning_rate=0.05,
            subsample=0.8,colsample_bytree=0.8,eval_metric="logloss",random_state=42).fit(
            Xtr, np.array([r["win"] for r in tr]))
        for i,r in enumerate(rows):
            if str(r["et"])[:4]==y:
                P_qp[i]=float(clf.predict_proba(
                    np.array([[r["x"][j] for j in stable_idx]]))[:,1][0])
    all_p=np.array(list(P_qp.values())); thr=np.quantile(all_p,1-gate)
    passed=all_p[all_p>=thr]; lo,hi=np.quantile(passed,0.40),np.quantile(passed,0.80)
    eq=250.; peak=250.; mdd=0.; free=pd.Timestamp("2000"); trades=[]; slog=[]
    for i,r in enumerate(rows):
        if str(r["et"])<E.OOS_START or i not in P_qp or P_qp[i]<thr or r["et"]<free: continue
        p=P_qp[i]; nt=0.6 if p<lo else (1.25 if p<hi else 2.5)
        eq*=(1+nt*(r["ret"]-E.COST)); free=r["xt"]
        peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak if peak>0 else 0); trades.append(r["win"])
        if shadow: slog.append({"ts":str(r["et"]),"c":r["c"],"p":round(p,4),"nt":nt,"win":r["win"]})
        if eq<=0: break
    if shadow:
        with open(SHADOW_LOG,"w") as f: [f.write(json.dumps(e)+"\n") for e in slog]
    yrs=(pd.Timestamp(str(rows[-1]["xt"]))-pd.Timestamp(E.OOS_START)).days/365.25
    cagr=((eq/250)**(1/yrs)-1)*100 if eq>0 else -100
    return dict(eq=eq,cagr=cagr,mdd=mdd*100,n=len(trades),
                wr=np.mean(trades)*100 if trades else 0,lo=lo,hi=hi)

# ── 3. CPCV ────────────────────────────────────────────────────────────────
def run_cpcv(rows, stable_idx, n_splits=6, k_test=2, gate=0.20):
    n=len(rows); sz=n//n_splits
    splits=[(i*sz,(i+1)*sz if i<n_splits-1 else n) for i in range(n_splits)]
    cagrs=[]
    for test_sp in combinations(range(n_splits),k_test):
        tr_idx=[j for i,(s,e) in enumerate(splits) if i not in test_sp for j in range(s,e)]
        te_idx=[j for i,(s,e) in enumerate(splits) if i in test_sp for j in range(s,e)]
        if len(tr_idx)<200 or len(te_idx)<30: continue
        Xtr=np.array([[rows[i]["x"][j] for j in stable_idx] for i in tr_idx],float)
        clf=xgb.XGBClassifier(n_estimators=200,max_depth=4,learning_rate=0.05,
            subsample=0.8,colsample_bytree=0.8,eval_metric="logloss",random_state=42).fit(
            Xtr, np.array([rows[i]["win"] for i in tr_idx]))
        Xte=np.array([[rows[i]["x"][j] for j in stable_idx] for i in te_idx],float)
        probs=clf.predict_proba(Xte)[:,1]; thr=np.quantile(probs,1-gate)
        eq=100.; free=pd.Timestamp("2000"); trades=[]
        for j,idx in enumerate(te_idx):
            r=rows[idx]
            if probs[j]<thr or r["et"]<free: continue
            eq*=(1+0.6*(r["ret"]-E.COST)); free=r["xt"]; trades.append(r["win"])
        if len(trades)<5: continue
        ts=[rows[i]["et"] for i in te_idx]; yrs=max(0.1,(max(ts)-min(ts)).days/365.25)
        cagrs.append(((eq/100)**(1/yrs)-1)*100 if eq>0 else -100)
    return np.array(cagrs)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--cpcv",action="store_true",help="CPCV çalıştır (birkaç dk)")
    ap.add_argument("--shadow",action="store_true",help="Shadow log yaz")
    args=ap.parse_args()
    print(__doc__)
    print("Sinyaller + model...")
    rows=E.build_signals(); P=E.walk_forward_proba(rows)
    print("\n1. SHAP Stability...")
    si=shap_stable_features(rows)
    print(f"   Stabil ({len(si)}/15): {[E.FEATS[i] for i in si]}")
    print(f"   Atılan: {[E.FEATS[i] for i in range(len(E.FEATS)) if i not in si]}")
    print("\n2. Güven-bazlı backtest (stabil feature seti)...")
    r=backtest_quantpro(rows,P,si,shadow=args.shadow)
    print("="*70); print("  BOT QUANTPRO — SHAP-stabil + güven-sizing"); print("="*70)
    print(f"  $250→${r['eq']:.0f}  CAGR%{r['cagr']:.1f}  MDD%{r['mdd']:.1f}  WR%{r['wr']:.0f}  n={r['n']}")
    mar=r['cagr']/r['mdd'] if r['mdd']>0 else 0
    print(f"  MAR:{mar:.2f}  bantlar: <{r['lo']:.3f}→0.6x <{r['hi']:.3f}→1.25x üstü→2.5x")
    b3=E.backtest(rows,P,bankroll=250.0,sizing="fixed",notional_cap=0.6)
    print(f"\n  Kıyas bot_kararli(0.6x): $250→${b3['eq']:.0f} CAGR%{b3['cagr']:.1f} MDD%{b3['mdd']:.1f} MAR{b3['cagr']/b3['mdd']:.2f}")
    if args.cpcv:
        print("\n3. CPCV (15 yol)...")
        cv=run_cpcv(rows,si)
        if len(cv): print(f"   Medyan%{np.median(cv):.1f} [{np.percentile(cv,5):.1f},{np.percentile(cv,95):.1f}] P(>0)%{(cv>0).mean()*100:.0f}")
    if args.shadow: print(f"\n   Shadow log: {SHADOW_LOG} ({r['n']} kayıt)")
    print(f"\n  ⚠️ BACKTEST. CPCV med.~%8 → edge var ama modest. Paper-trade şart.")

if __name__=="__main__":
    main()
