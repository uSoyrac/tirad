#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
OPTIMAL FINAL — Compound Engine + GÜVEN-BAZLI DİNAMİK SİZİNG (V71 vizyonu, GÜVENLİ)
═══════════════════════════════════════════════════════════════════════════════
Bu, projenin NİHAİ birleşik botudur. İki doğrulanmış parçayı birleştirir:
  1. classic_compound (compound_engine.py): donchian+supertrend → XGBoost kalite-kapısı
     → TP+5%/SL-2.5% → walk-forward doğrulanmış edge (+31% CAGR, MDD%17, WR%44 OOS).
  2. Hybrid'in DİNAMİK KELLY'si: AI'ın güven oranına (proba persentili) göre kasayı
     orantılı bas — AMA 2.5x KELLY-TAVANINI ASLA İHLAL ETME (volatilite-drag/ruin koruması).

GÜVENLİK KURALLARI (ihlal edilemez):
  • Sizing GÜVEN-bazlı (anti-martingale), KAYIP-bazlı DEĞİL. "Kaybedince büyüt" YASAK.
  • notional ≤ 2.5x (Kelly tepesi). Ötesi geometrik büyümeyi DÜŞÜRÜR (kanıtlandı).
  • Bu BACKTEST. DSR%31 → edge istatistiksel kesin değil. Önce PAPER-TRADE.

NEDEN bu 4 bot arasından bu?  (uyg/june_2 değerlendirmesi, hepsi koşturuldu)
  • sniper (TP10/SL2): +33% ama MDD%30 → risk-ayarlı inferior.
  • smartmoney_accel: 2.türev feature'ları importance'ta SON SIRADA → katkı yok (kanıtlandı).
  • TP2/SL10 (yüksek-WR): WR%74 ama breakeven%83 altı + fat-tail → kırılgan.
  • >>> classic + güven-sizing (bu) = doğrulanmış edge + güvenli agresiflik.

Çalıştırma:  cd uyg/src && PYTHONPATH=. python3 ../june_2/optimal_final_confidence.py
═══════════════════════════════════════════════════════════════════════════════
"""
import os, sys, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import compound_engine as E   # doğrulanmış baz motor

# ── GÜVEN-BAZLI SİZİNG (V71 dinamik Kelly, 2.5x tavanlı) ──────────────────────
NOTIONAL_CAP = 2.5            # Kelly tepesi — ASLA aşma
def confidence_notional(proba, lo, hi):
    """proba persentiline göre notional: düşük güven→0.6x, orta→1.25x, yüksek→2.5x.
    KAYIP geçmişine DEĞİL, modelin güvenine bakar (anti-martingale, güvenli)."""
    if proba < lo:   return 0.6      # düşük güven: muhafazakâr
    if proba < hi:   return 1.25     # orta güven: yarı-Kelly
    return NOTIONAL_CAP              # yüksek güven: Kelly tepesi (2.5x), ÖTESİ YOK

def backtest_confidence(rows, P, bankroll=250.0, gate=0.20):
    keep = np.array([P[i] for i in P])
    thr = np.quantile(keep, 1-gate)
    # güven bantları: gate'i geçenler arasında 40/80 persentil
    passed = keep[keep>=thr]
    lo, hi = np.quantile(passed, 0.40), np.quantile(passed, 0.80)
    eq=bankroll; peak=bankroll; mdd=0.0; free=pd.Timestamp("2000"); trades=[]; monthly={}
    for i,r in enumerate(rows):
        if str(r["et"])<E.OOS_START or i not in P or P[i]<thr or r["et"]<free: continue
        nt = confidence_notional(P[i], lo, hi)
        eq *= (1 + nt*(r["ret"]-E.COST)); free=r["xt"]
        peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak if peak>0 else 0)
        trades.append(r["win"]); monthly[str(r["et"])[:7]]=eq
        if eq<=0: break
    yrs=max(1e-9,(pd.Timestamp(str(rows[-1]["xt"]))-pd.Timestamp(E.OOS_START)).days/365.25)
    cagr=((eq/bankroll)**(1/yrs)-1)*100 if eq>0 else -100
    return dict(eq=eq, cagr=cagr, mdd=mdd*100, n=len(trades),
                wr=np.mean(trades)*100 if trades else 0, monthly=monthly, lo=lo, hi=hi)

def main():
    print(__doc__.split("Çalıştırma")[0])
    print("Sinyaller + walk-forward discriminator (ilk çalıştırma birkaç dk)...")
    rows=E.build_signals(); P=E.walk_forward_proba(rows)
    print("="*74)
    print("  OPTIMAL FINAL — classic + GÜVEN-BAZLI sizing (2.5x tavanlı) · $250 · OOS")
    print("="*74)
    # kıyas: düz sizing vs güven-bazlı
    flat=E.backtest(rows,P,bankroll=250.0,sizing="fixed",notional_cap=0.6)
    conf=backtest_confidence(rows,P,bankroll=250.0,gate=0.20)
    print(f"  {'sizing':>24} {'$250->':>9} {'CAGR%':>7} {'MDD%':>6} {'WR%':>4}")
    print(f"  {'düz %60 notional (baz)':>24} {flat['eq']:>9.0f} {flat['cagr']:>7.1f} {flat['mdd']:>6.1f} {flat['wr']:>4.0f}")
    print(f"  {'GÜVEN-bazlı (0.6/1.25/2.5x)':>24} {conf['eq']:>9.0f} {conf['cagr']:>7.1f} {conf['mdd']:>6.1f} {conf['wr']:>4.0f}")
    print(f"\n  Güven bantları: proba<{conf['lo']:.3f}→0.6x · <{conf['hi']:.3f}→1.25x · üstü→2.5x")
    print(f"  KURAL: notional ≤2.5x (asla aşma) · sizing güven-bazlı (martingale DEĞİL)")
    print(f"  ⚠️ BACKTEST. DSR%31 → önce paper-trade, sonra gerçek sermaye.")

if __name__=="__main__":
    main()
