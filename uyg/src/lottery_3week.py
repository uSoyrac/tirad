#!/usr/bin/env python3
"""
lottery_3week.py — "$100 → $10.000, 3 hafta, ŞANSLI DÖNEM" dürüst odds
═══════════════════════════════════════════════════════════════════════
Gerçek edge'le, maksimum-agresif (yüksek risk/kaldıraç), 3-haftalık pencerede
($100→$10k = 100x) ulaşma olasılığı vs iflas. Sıfırdan, dürüst.
"""
import numpy as np, warnings
warnings.filterwarnings("ignore")
from mm_compare import collect

def lottery(R, risk, n_trades, target=100.0, n=200000, seed=42):
    """n_trades işlemlik pencerede $1→target ulaşma olasılığı (risk=işlem başı kasa kesri)."""
    rng=np.random.default_rng(seed); succ=ru=0; best=[]
    for _ in range(n):
        eq=1.0
        for _ in range(n_trades):
            r=R[rng.integers(len(R))]; eq*=(1+risk*r)
            if eq>=target: succ+=1; break
            if eq<=0.05: ru+=1; eq=0; break
        best.append(eq)
    return succ/n*100, ru/n*100, np.array(best)

def main():
    R=collect()
    print("="*80); print(f"  '$100→$10.000 · 3 HAFTA · ŞANSLI DÖNEM' DÜRÜST ODDS"); print("="*80)
    print(f"  Gerçek edge: {len(R)} işlem, WR%{(R>0).mean()*100:.0f}, beklenti{R.mean():+.3f}R, en iyi tek işlem +{R.max():.1f}R")
    # 3 hafta ≈ kaç işlem? top-5, ort tutma 6 gün; 5 coin eşzamanlı → ~10-15 tamamlanan işlem
    for n_tr in [10, 15, 20]:
        print(f"\n  ── 3 hafta ≈ {n_tr} işlem ── ($100→$10k = 100x)")
        print(f"  {'risk/işlem%':>12}{'P($10k)%':>11}{'P(iflas)%':>11}{'medyan$':>10}{'EV($)':>9}")
        for risk in [0.3,0.5,0.7,0.9,1.2]:
            pw,pr,fin=lottery(R,risk,n_tr)
            ev=(pw/100)*10000 + ((100-pw)/100)*np.median(fin[fin<100])*100*0  # kazanırsa 10k, kaybedersen ~0
            ev=(pw/100)*10000   # basit: stake $100, kazanç $10k
            print(f"  {risk*100:>12.0f}{pw:>11.2f}{pr:>11.1f}{np.median(fin)*100:>10.0f}{ev-100:>+9.0f}")
    print(f"\n  YORUM: $100→$10k/3 hafta = aşırı kaldıraçlı PİYANGO. En iyi olasılık ~%X (çok düşük),")
    print(f"  ~%95+ ihtimalle $100 gider. EV pozitifse 'çok denersen kârlı' ama tek seferde değil.")

if __name__=="__main__":
    main()
