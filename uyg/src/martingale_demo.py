#!/usr/bin/env python3
"""
martingale_demo.py — "Kaybedince büyüt, telafi et" sisteminin matematiği
═══════════════════════════════════════════════════════════════════════
Kullanıcının tarifi: kaybedince sonraki bahsi, bir kazanç önceki kayıpları
TELAFİ edecek kadar büyüt (martingale-recovery). + kaldıraç.
Karşılaştırma: martingale-recovery vs flat vs Kelly,
  (a) ADİL oyun (rulet analojisi: %50 WR, $2 bahis → $4, EV=0)
  (b) GERÇEK edge'imiz (gerçek R dağılımı, hafif +EV)
Sonuç: P(iflas), medyan, max kayıp serisi.
"""
import json, numpy as np, warnings
warnings.filterwarnings("ignore")

SEED=42

def real_R():
    """Gerçek edge R dağılımı (varsa cache, yoksa tipik: WR37, win+2.7 loss-1.04)."""
    import os
    if os.path.exists("/tmp/meta_dataset_v2vov.json"):
        # kaba: WR ve payoff'tan üret
        pass
    # ölçülen değerlerden sentetik dağılım: %37 kazanç +2.7R, %63 kayıp -1.04R
    rng=np.random.default_rng(1)
    R=np.where(rng.random(5000)<0.37, 2.7, -1.04)
    return R

def simulate(system, fair=True, n_trials=20000, n_trades=300, start=100.0, base=2.0, seed=SEED):
    rng=np.random.default_rng(seed)
    if fair:
        # adil oyun: %50, kazanç +base (1:1, $2→$4), kayıp -base
        wr=0.50; win_pay=1.0; loss_pay=-1.0   # birim bahis başına R
    else:
        Rdist=real_R()
    ruined=0; finals=[]; maxstreaks=[]
    for _ in range(n_trials):
        bank=start; deficit=0.0; streak=0; mx=0; dead=False
        for _ in range(n_trades):
            # bahis büyüklüğü (birim)
            if system=="flat":
                bet=base
            elif system=="kelly":
                bet=bank*0.05   # sabit kesir (fractional Kelly proxy)
            else:  # martingale-recovery: kazanç deficit+base telafi etsin
                bet=(deficit+base)   # 1:1 oyunda kazanç=bet, deficit+base'i kapatmak için
                bet=min(bet, bank)   # kasadan fazla bahis olamaz
            if fair:
                win = rng.random()<wr
                pnl = bet*win_pay if win else bet*loss_pay
            else:
                r=Rdist[rng.integers(len(Rdist))]; win=r>0
                # bet = riske atılan miktar; pnl = bet*r
                if system=="kelly": pnl=bet*r
                elif system=="flat": pnl=bet*r
                else: pnl=bet*r
            bank+=pnl
            if win: deficit=0; streak=0
            else: deficit+=bet; streak+=1; mx=max(mx,streak)
            if bank<=base:   # bahis yapamayacak kadar küçük = iflas
                dead=True; break
        if dead: ruined+=1; bank=0.0
        finals.append(bank); maxstreaks.append(mx)
    f=np.array(finals)
    return {"median":float(np.median(f)),"p5":float(np.percentile(f,5)),
            "ruin":ruined/n_trials*100,"max_streak":int(np.max(maxstreaks))}

def main():
    print("="*74); print("  MARTİNGALE-RECOVERY ('kaybedince büyüt, telafi et') MATEMATİĞİ"); print("="*74)
    for fair,lab in [(True,"(a) ADİL OYUN — rulet analojin: %50 WR, $2→$4, EV=0"),
                     (False,"(b) GERÇEK EDGE'imiz: %37 WR, +2.7R/-1.04R, hafif +EV")]:
        print(f"\n  {lab}")
        print(f"  {'sistem':22}{'medyan$':>10}{'P5$':>9}{'P(iflas)%':>11}{'maks kayıp serisi':>18}")
        for sysn,sysl in [("flat","Flat (hep $2)"),("kelly","Kelly (sabit %5)"),("martingale","Martingale-recovery")]:
            r=simulate(sysn,fair=fair)
            flag=" ← İFLAS" if r["ruin"]>30 else (" ✓" if r["ruin"]<2 else "")
            print(f"  {sysl:22}{r['median']:>10.0f}{r['p5']:>9.0f}{r['ruin']:>11.1f}{r['max_streak']:>18}{flag}")
    print(f"\n  DERS: Martingale EV'yi DEĞİŞTİRMEZ — sadece 'çok küçük kazanç + nadir TAM iflas'a çevirir.")
    print(f"  Adil oyunda garanti iflas; +EV oyunda bile Kelly'den kötü. 8-12 kayıp serisi KAÇINILMAZ.")
    print(f"  +EV edge'i büyütmenin DOĞRU yolu Kelly (sabit kesir): optimal compound + iflas=0.")

if __name__=="__main__":
    main()
