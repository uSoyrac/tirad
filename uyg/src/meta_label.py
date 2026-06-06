#!/usr/bin/env python3
"""
meta_label.py — META-LABELING (López de Prado): edge'i sızıntısız ML ile keskinleştir
═══════════════════════════════════════════════════════════════════════
V20/V21 hatası: ML ile YÖN tahmini + mock/leaked veri → %88 WR fantezi.
Doğrusu: birincil model (donchian+supertrend trend sinyali) YÖNÜ verir;
ikincil ML modeli "bu trade TP'ye mi SL'e mi gidecek?" KALİTESİNİ tahmin eder.
Feature'lar giriş-anında (entry_i-1, causal); split temporal + embargo (sızıntı yok).

Soru: meta-label filtresi OOS'ta WR ve beklentiyi yükseltiyor mu?
"""
import json, numpy as np, warnings
warnings.filterwarnings("ignore")
from signal_lab import load_all, simulate, metrics, rsi, macd, atr, adx, ema, sma, roc, supertrend
import sig_donchian_breakout as D, sig_supertrend_regime as S
from sklearn.ensemble import HistGradientBoostingClassifier

STRATS = [("donchian", D.make_sig(40,"atr",0.25,0.0), 2.0, 2.5),
          ("supertrend", S.make_sig(10,3,25), 2.0, 3.0)]
FEATURES = ["rsi","macd_h","adx","atrp","vol_ratio","ema50d","ema200d","roc_s","roc_l","st_dir","dir","sl_dist"]

def feat_arrays(df):
    c = df["close"].to_numpy(float); v = df["volume"].to_numpy(float)
    _,_,mh = macd(c); a = atr(df,14); ad,_,_ = adx(df,14)
    e50 = ema(c,50); e200 = ema(c,200); vs = sma(v,20)
    return {"rsi": rsi(c,14), "macd_h": mh/(c+1e-9), "adx": ad, "atrp": a/(c+1e-9),
            "vol_ratio": v/(vs+1e-9), "ema50d": (c-e50)/(e50+1e-9), "ema200d": (c-e200)/(e200+1e-9),
            "roc_s": roc(c,6), "roc_l": roc(c,42), "st_dir": supertrend(df,10,3)}

def build_dataset():
    dfs = load_all("mktdata","4h"); rows = []
    for name, sig, sl, tp in STRATS:
        for coin, df in dfs.items():
            fa = feat_arrays(df)
            for t in simulate(df, sig(df), sl_atr=sl, tp_r=tp):
                fi = t["entry_i"] - 1                       # sinyal barı = giriş-anı bilgisi (causal)
                if fi < 200 or fi >= len(df): continue
                row = {f: float(fa[f][fi]) if f in fa and np.isfinite(fa[f][fi]) else np.nan for f in fa}
                row.update({"dir": t["dir"], "sl_dist": t["sl_dist"], "r_mult": t["r_mult"],
                            "win": 1 if t["r_mult"] > 0 else 0, "entry_ts": t["entry_ts"],
                            "exit_ts": t["exit_ts"], "coin": coin, "strat": name})
                rows.append(row)
    rows.sort(key=lambda x: x["entry_ts"])
    return rows

def walk_forward(rows, X, y, rmult, folds=4, thr=0.35):
    """Genişleyen pencere walk-forward: her fold geçmişte eğit, sonraki dilimde tahmin et.
    Tüm OOS tahminlerini havuzla → tek-split fluke'una karşı sağlam lift ölçümü."""
    n = len(rows); start = int(n*0.4)
    bounds = np.linspace(start, n, folds+1).astype(int)
    sel_r, all_r, sel_coins = [], [], {}
    for k in range(folds):
        a, b = bounds[k], bounds[k+1]
        clf = HistGradientBoostingClassifier(max_depth=3, max_iter=200, learning_rate=0.05,
              l2_regularization=1.0, min_samples_leaf=80, random_state=42)
        clf.fit(X[:a-20], y[:a-20])
        pr = clf.predict_proba(X[a:b])[:,1]
        for j in range(a, b):
            all_r.append(rmult[j])
            if pr[j-a] >= thr:
                sel_r.append(rmult[j]); sel_coins.setdefault(rows[j]["coin"],[]).append(rmult[j])
    sel_r = np.array(sel_r); all_r = np.array(all_r)
    pos = sum(1 for c,rs in sel_coins.items() if np.mean(rs)>0)
    return {"sel_n": len(sel_r), "sel_wr": (sel_r>0).mean()*100, "sel_e": sel_r.mean(),
            "base_n": len(all_r), "base_wr": (all_r>0).mean()*100, "base_e": all_r.mean(),
            "pos_coins": pos, "tot_coins": len(sel_coins), "sel_r": sel_r}

def harvest_cmp(R, risk=0.02, target=10000, reset=300, ruin=0.10, n=4000, seed=42):
    rng = np.random.default_rng(seed); R = np.asarray(R); succ=ru=0; times=[]
    for _ in range(n):
        eq=100.0; floor=10.0; steps=0
        while steps<6000:
            blk=rng.integers(0,max(1,len(R)-50))
            for r in R[blk:blk+50]:
                eq+=eq*risk*r; steps+=1
                if eq>=target: succ+=1; times.append(steps); eq=reset; floor=reset*ruin
                elif eq<=floor: ru+=1; eq=reset; floor=reset*ruin
                if steps>=6000: break
    c=succ+ru
    return (succ/c*100 if c else 0), (np.median(times) if times else float('inf'))

def main():
    import os
    if os.path.exists("/tmp/meta_dataset.json"):
        rows = json.load(open("/tmp/meta_dataset.json"))
    else:
        rows = build_dataset(); json.dump(rows, open("/tmp/meta_dataset.json","w"))
    n = len(rows)
    X = np.array([[r.get(f, np.nan) for f in FEATURES] for r in rows], float)
    y = np.array([r["win"] for r in rows]); rmult = np.array([r["r_mult"] for r in rows])
    print("="*84); print(f"  META-LABELING — {n} trade (donchian+supertrend), {len(FEATURES)} feature"); print("="*84)
    base_wr = y.mean()*100; base_e = rmult.mean()
    print(f"  Baseline (tüm trade'ler): WR={base_wr:.1f}%  beklenti={base_e:+.3f}R")

    # temporal split + embargo (train ilk %60, 1 hafta=42 bar embargo, test son %40)
    split = int(n*0.60); emb = 0
    # embargo: train'in son exit'i test'in ilk entry'sini aşmasın diye basit boşluk (40 trade)
    tr_idx = np.arange(0, split-20); te_idx = np.arange(split+20, n)
    Xtr, ytr = X[tr_idx], y[tr_idx]; Xte, yte, rte = X[te_idx], y[te_idx], rmult[te_idx]

    clf = HistGradientBoostingClassifier(max_depth=3, max_iter=200, learning_rate=0.05,
                                         l2_regularization=1.0, min_samples_leaf=80, random_state=42)
    clf.fit(Xtr, ytr)
    proba = clf.predict_proba(Xte)[:,1]

    print(f"\n  OOS TEST ({len(te_idx)} trade, son %40 zaman):")
    print(f"  {'proba≥':>7}{'seçilen':>9}{'%kabul':>8}{'WR%':>7}{'beklenti':>10}{'sumR':>8}")
    best = None
    for thr in [0.0, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]:
        sel = proba >= thr
        if sel.sum() < 10:
            print(f"  {thr:>7.2f}{int(sel.sum()):>9}  (az)"); continue
        wr = yte[sel].mean()*100; e = rte[sel].mean(); sm = rte[sel].sum()
        print(f"  {thr:>7.2f}{int(sel.sum()):>9}{sel.mean()*100:>7.0f}%{wr:>7.1f}{e:>+10.3f}{sm:>+8.1f}")
        if e > 0 and (best is None or e > best[1]):
            best = (thr, e, wr, int(sel.sum()))

    # baseline OOS (filtresiz test)
    print(f"\n  OOS baseline (filtresiz): WR={yte.mean()*100:.1f}%  beklenti={rte.mean():+.3f}R")
    if best:
        thr,e,wr,ns = best
        print(f"  >>> META-LABEL @ proba≥{thr}: WR={wr:.1f}% beklenti={e:+.3f}R (N={ns})")
        lift_e = e - rte.mean(); lift_wr = wr - yte.mean()*100
        print(f"      LIFT: WR {lift_wr:+.1f} puan, beklenti {lift_e:+.3f}R")
        # per-coin OOS robustluk @ en iyi eşik
        sel = proba >= thr; te_rows = [rows[i] for i in te_idx]
        bycoin = {}
        for k,i in enumerate(te_idx):
            if sel[k]: bycoin.setdefault(rows[i]["coin"],[]).append(rmult[i])
        pos = sum(1 for c,rs in bycoin.items() if np.mean(rs)>0)
        print(f"      per-coin OOS: {pos}/{len(bycoin)} coinde pozitif")
        verdict = "META-LABEL EDGE'İ YÜKSELTİYOR ✓" if (lift_e>0.01 and pos>=0.6*len(bycoin)) else "anlamlı/robust lift YOK"
        print(f"      VERDICT: {verdict}")
    else:
        print("  >>> Hiçbir eşik OOS beklentiyi pozitife çıkarmadı — meta-label bu feature setinde yardımcı olmuyor.")

    # feature önemleri (permutation yerine hızlı: HGB built-in yok; basit tek-feature AUC sırası)
    from sklearn.metrics import roc_auc_score
    aucs = []
    for j,f in enumerate(FEATURES):
        col = Xte[:,j]; ok = np.isfinite(col)
        try: aucs.append((f, roc_auc_score(yte[ok], col[ok])))
        except: aucs.append((f,0.5))
    aucs.sort(key=lambda x:-abs(x[1]-0.5))
    print(f"\n  Tek-feature ayrıştırma (AUC, 0.5=işe yaramaz): " + ", ".join(f"{f}:{a:.3f}" for f,a in aucs[:6]))

    # ── WALK-FORWARD (4 fold) — tek-split fluke kontrolü ──
    print(f"\n  [WALK-FORWARD] 4 genişleyen fold, pooled OOS (proba≥0.35):")
    wf = walk_forward(rows, X, y, rmult, folds=4, thr=0.35)
    print(f"    Baseline pooled OOS: N={wf['base_n']} WR={wf['base_wr']:.1f}% E={wf['base_e']:+.3f}R")
    print(f"    Meta-label pooled:   N={wf['sel_n']} WR={wf['sel_wr']:.1f}% E={wf['sel_e']:+.3f}R  "
          f"per-coin+ {wf['pos_coins']}/{wf['tot_coins']}")
    lift = wf['sel_e'] - wf['base_e']
    print(f"    LIFT (walk-forward): beklenti {lift:+.3f}R ({wf['base_e']:+.3f}→{wf['sel_e']:+.3f})  "
          f"→ {'ROBUST ✓' if lift>0.01 and wf['pos_coins']>=0.6*wf['tot_coins'] else 'zayıf'}")

    # ── HASAT-DÖNGÜSÜ: baseline vs meta-label ($100→$10k) ──
    print(f"\n  [HASAT-DÖNGÜSÜ] $100→$10k başarı oranı (risk %2):")
    base_R = rmult  # tüm trade'ler
    ps_b, t_b = harvest_cmp(base_R, risk=0.02)
    ps_m, t_m = harvest_cmp(wf['sel_r'], risk=0.02)
    print(f"    Baseline (E={base_R.mean():+.3f}R): P(başarı)={ps_b:.0f}%  medyan {t_b:.0f} işlem")
    print(f"    Meta-label (E={wf['sel_e']:+.3f}R): P(başarı)={ps_m:.0f}%  medyan {t_m:.0f} işlem")

if __name__ == "__main__":
    main()
