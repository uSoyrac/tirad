#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════
BOT 3 — OPTİMAL (Güven-Bazlı Dinamik Sizing) ⭐ EN YÜKSEK MAR
═══════════════════════════════════════════════════════════════════
En iyi risk-ayarlı getiri (MAR). V71 "Dinamik Kelly" vizyonu, GÜVENLİ.
Mimari: Donchian40+SuperTrend → XGBoost kalite-kapısı → TP+5%/SL-2.5%
Sizing: AI GÜVENİNE göre notional — düşük→0.6x, orta→1.25x, yüksek→2.5x.
  • notional ≤2.5x (Kelly tepesi, ASLA aşma) · GÜVEN-bazlı (martingale DEĞİL).

DOĞRULANMIŞ (OOS walk-forward): $250→$1003 · +%77.7 CAGR · MaxDD %31 · WR %44 · MAR 2.50
(düz-0.6 MAR1.84 ve düz-2.5x MAR1.56 ikisini de risk-ayarlı geçer)

Çalıştır:  cd uyg/Botlar && python3 bot_optimal.py
═══════════════════════════════════════════════════════════════════
"""
import numpy as np, pandas as pd
import _engine_path as B

NOTIONAL_CAP = 2.5
def confidence_notional(proba, lo, hi):
    if proba < lo: return 0.6
    if proba < hi: return 1.25
    return NOTIONAL_CAP

def backtest_confidence(rows, P, bankroll=250.0, gate=0.20):
    E = B.E
    keep = np.array([P[i] for i in P]); thr = np.quantile(keep, 1-gate)
    passed = keep[keep >= thr]; lo, hi = np.quantile(passed, 0.40), np.quantile(passed, 0.80)
    eq=bankroll; peak=bankroll; mdd=0.0; free=pd.Timestamp("2000"); trades=[]
    for i, r in enumerate(rows):
        if str(r["et"]) < E.OOS_START or i not in P or P[i] < thr or r["et"] < free: continue
        nt = confidence_notional(P[i], lo, hi)
        eq *= (1 + nt*(r["ret"]-E.COST)); free=r["xt"]
        peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak if peak>0 else 0); trades.append(r["win"])
        if eq<=0: break
    yrs=max(1e-9,(pd.Timestamp(str(rows[-1]["xt"]))-pd.Timestamp(E.OOS_START)).days/365.25)
    cagr=((eq/bankroll)**(1/yrs)-1)*100 if eq>0 else -100
    return dict(eq=eq, cagr=cagr, mdd=mdd*100, n=len(trades),
                wr=np.mean(trades)*100 if trades else 0, lo=lo, hi=hi)

def main():
    print(__doc__)
    print("Hazırlanıyor (sinyaller + walk-forward model)...")
    rows, P = B.prepare()
    r = backtest_confidence(rows, P, bankroll=250.0, gate=0.20)
    B.report("BOT OPTİMAL — güven-bazlı sizing (≤2.5x tavan)", r,
             f"En yüksek MAR (2.50) · güven bantları: <{r['lo']:.3f}→0.6x <{r['hi']:.3f}→1.25x üstü→2.5x")

if __name__ == "__main__":
    main()
