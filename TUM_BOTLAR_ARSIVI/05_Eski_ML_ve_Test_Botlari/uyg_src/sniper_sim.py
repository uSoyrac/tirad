#!/usr/bin/env python3
"""
sniper_sim.py — SNIPER BOT: rejim-gate'li agresif compound (uyu → ateş)
═══════════════════════════════════════════════════════════════════════
Motor1 rejim skoru < eşik → BEKLE (kasa korunur). Skor ≥ eşik → ATEŞ:
trend sinyallerini agresif boyutla al, compound. Gerçek kronolojik edge.
Çıktı: rejim-eşiği × risk süpürmesi → büyüme, MDD, aktiflik, WR.
"""
import json, os, numpy as np, warnings
warnings.filterwarnings("ignore")
from regime_timing import collect_chrono, regime_score

def sniper(T, sc, thr, risk, start=100.0, harvest_x=None, reset=100.0):
    eq=start; peak=start; mdd=0; taken=0; wins=0; harvested=0.0
    for i,t in enumerate(T):
        if sc[i] < thr: continue          # BEKLE
        r=t["r"]; eq*=(1+risk*r); taken+=1; wins+= (r>0)
        peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak if peak>0 else 0)
        if eq<=0.05*start: eq=0; break     # iflas
        if harvest_x and eq>=start*harvest_x:   # kâr al → çek, resetle
            harvested+=eq-reset; eq=reset; peak=reset
    return {"final":eq,"mdd":mdd*100,"taken":taken,"wr":wins/taken*100 if taken else 0,"harvested":harvested}

def main():
    if os.path.exists("/tmp/sniper_T.json"):
        d=json.load(open("/tmp/sniper_T.json")); T=d["T"]; sc=np.array(d["sc"])
    else:
        T=collect_chrono(); sc=regime_score(T)
        json.dump({"T":T,"sc":sc.tolist()},open("/tmp/sniper_T.json","w"))
    R=np.array([t["r"] for t in T])
    print("="*82); print(f"  SNIPER BOT — rejim-gate'li agresif compound ({len(T)} işlem, 2024-04→2026-05)"); print("="*82)
    print(f"  Tüm akış: WR%{(R>0).mean()*100:.0f}, beklenti{R.mean():+.3f}R | rejim≥2'de {len(R[sc>=2])} işlem ort{R[sc>=2].mean():+.3f}R | rejim=3'te ort{R[sc>=3].mean() if (sc>=3).any() else 0:+.3f}R")
    print(f"\n  $100 başlangıç, ~2 yıl, hasat YOK (saf compound):")
    print(f"  {'rejim eşiği':>12}{'risk%':>7}{'işlem':>7}{'WR%':>6}{'final$':>11}{'x':>8}{'MDD%':>7}")
    best=None
    for thr in [2,3]:
        for risk in [0.05,0.10,0.20,0.30]:
            r=sniper(T,sc,thr,risk)
            x=r["final"]/100
            flag=" ✓" if r["mdd"]<=40 and x>1 else ""
            print(f"  {'skor≥'+str(thr):>12}{risk*100:>7.0f}{r['taken']:>7}{r['wr']:>6.0f}{r['final']:>11.0f}{x:>8.1f}{r['mdd']:>7.0f}{flag}")
            if x>1 and (best is None or x>best[1]): best=(f"skor≥{thr} risk%{int(risk*100)}",x,r["mdd"],r["taken"])
    print(f"\n  Hasat modu (skor≥2, risk%20, her 3x'te kâr çek→$100 reset):")
    h=sniper(T,sc,2,0.20,harvest_x=3.0)
    print(f"    {h['taken']} işlem, WR%{h['wr']:.0f}, çekilen toplam ${h['harvested']:.0f}, son kasa ${h['final']:.0f}")
    if best: print(f"\n  >>> En iyi saf-compound: {best[0]} → {best[1]:.1f}x, MDD%{best[2]:.0f}, {best[3]} işlem (~2 yıl)")
    print(f"  NOT: Sniper uyku-modunda (skor<eşik) kasayı korur → MDD düşer; sadece favori rejimde ateş eder.")

if __name__=="__main__":
    main()
