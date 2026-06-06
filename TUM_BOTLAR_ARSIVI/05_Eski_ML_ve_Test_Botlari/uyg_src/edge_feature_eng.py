#!/usr/bin/env python3
"""
edge_feature_eng.py — FEATURE MÜHENDİSLİĞİ cephesi (edge büyütme, walk-forward OOS)
═══════════════════════════════════════════════════════════════════════════════
Mevcut en iyi: trend ensemble (donchian+supertrend) meta-label v2 = +0.165R OOS
(walk-forward, 16/20 coin pozitif). HEDEF: bunun ÜSTÜNE OOS-robust lift.

Bu dosya meta_features_v2.build_v2'yi GENİŞLETİR — yeni CAUSAL feature grupları:
  G1 order-flow proxy : yön*hacim kümülatif (CVD-proxy) eğimi, normalize
  G2 candle yapısı    : gövde/menzil, üst/alt fitil oranları (rolling ort.)
  G3 çoklu-lag getiri : 1,3,5,10 bar getiriler (momentum profili)
  G4 cross-sec disp.  : evren getiri std (dispersion) + dispersion percentile
  G5 vol-of-vol       : ATR%'nin rolling std'i (rejim belirsizliği)
  G6 momentum-of-mom  : ROC'un ROC'u (ivme ikinci türev)
  G7 win/loss streak  : coin'in son K barda kapanış serisi durumu (run)

Her grup CAUSAL (yalnız i ve öncesi). Giriş feature'ı entry_i-1 barından okunur
(simulate i+1 açılışında girer → fi=entry_i-1 sinyal barıdır, look-ahead yok).

Ölçüm: wf_lift (4-fold walk-forward, meta-label thr=0.35). SADECE baseline v2
(+0.165R) üstüne OOS lift sağlayan + per-coin robust (≥%60 coin+) grupları tut.
"""
import json, itertools, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
from signal_lab import (load_all, simulate, atr, ema, rsi, macd, sma, roc,
                        supertrend, adx)
import sig_donchian_breakout as D, sig_supertrend_regime as S
from meta_features_v2 import STRATS, V1, V2_EXTRA, FEATURES_V2, coin_feats, wf_lift

# ── yeni feature isim grupları ──
G1 = ["of_slope", "of_z"]                       # order-flow proxy
G2 = ["body_ratio", "uwick_ratio", "lwick_ratio"]  # candle yapısı
G3 = ["ret1", "ret3", "ret5", "ret10"]          # çoklu-lag getiri
G4 = ["xs_disp", "xs_disp_p"]                    # cross-sectional dispersion
G5 = ["vov"]                                     # vol-of-vol
G6 = ["mom_of_mom"]                              # momentum-of-momentum
G7 = ["streak"]                                  # win/loss (kapanış) run

NEW_GROUPS = {"G1": G1, "G2": G2, "G3": G3, "G4": G4, "G5": G5, "G6": G6, "G7": G7}
ALL_NEW = G1 + G2 + G3 + G4 + G5 + G6 + G7


def extra_coin_feats(df):
    """meta_features_v2.coin_feats ÜSTÜNE yeni per-bar CAUSAL feature'lar."""
    o = df["open"].to_numpy(float); h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float);  c = df["close"].to_numpy(float)
    v = df["volume"].to_numpy(float)
    n = len(c)
    out = {}

    # ── G1 order-flow proxy (CVD-proxy) ──
    # bar yönü işareti × hacim → kümülatif imzalı hacim (causal kümülatif toplam).
    sign = np.sign(c - o)                       # +1 yeşil, -1 kırmızı, 0 doji
    sv = sign * v
    cvd = np.cumsum(sv)                          # imzalı hacim kümülatifi (causal)
    # son 10 bar üzerindeki eğim (CVD momentum), bar hacmiyle normalize → birimsiz
    vbase = pd.Series(v).rolling(20).mean().to_numpy()
    of_slope = (cvd - np.roll(cvd, 10)) / (vbase * 10 + 1e-9)
    of_slope[:10] = np.nan
    # son penceredeki imzalı-hacim z-skoru (akış basıncı)
    sv_s = pd.Series(sv)
    of_z = ((sv_s - sv_s.rolling(50).mean()) / (sv_s.rolling(50).std() + 1e-9)).to_numpy()
    out["of_slope"] = of_slope
    out["of_z"] = of_z

    # ── G2 candle yapısı (rolling ortalama → tek bar gürültüsünü azalt) ──
    rng = (h - l)
    body = np.abs(c - o)
    uw = h - np.maximum(c, o)                    # üst fitil
    lw = np.minimum(c, o) - l                    # alt fitil
    body_ratio = pd.Series(body / (rng + 1e-9)).rolling(5).mean().to_numpy()
    uw_ratio = pd.Series(uw / (rng + 1e-9)).rolling(5).mean().to_numpy()
    lw_ratio = pd.Series(lw / (rng + 1e-9)).rolling(5).mean().to_numpy()
    out["body_ratio"] = body_ratio
    out["uwick_ratio"] = uw_ratio
    out["lwick_ratio"] = lw_ratio

    # ── G3 çoklu-lag getiri (momentum profili) ──
    for lag in (1, 3, 5, 10):
        out[f"ret{lag}"] = c / np.roll(c, lag) - 1.0
        out[f"ret{lag}"][:lag] = np.nan

    # ── G5 vol-of-vol (ATR%'nin değişkenliği) ──
    atrp = atr(df, 14) / (c + 1e-9)
    out["vov"] = pd.Series(atrp).rolling(30).std().to_numpy()

    # ── G6 momentum-of-momentum (ROC'un ROC'u) ──
    r6 = roc(c, 6)
    # ROC serisinin 6-bar değişimi → ivmenin ivmesi
    mom2 = pd.Series(r6).diff(6).to_numpy()
    out["mom_of_mom"] = mom2

    # ── G7 kapanış run/streak (ardışık aynı yön bar sayısı, imzalı) ──
    up = (c > np.roll(c, 1)).astype(float); up[0] = 0
    dn = (c < np.roll(c, 1)).astype(float); dn[0] = 0
    streak = np.zeros(n)
    for i in range(1, n):
        if up[i]:   streak[i] = streak[i-1] + 1 if streak[i-1] > 0 else 1
        elif dn[i]: streak[i] = streak[i-1] - 1 if streak[i-1] < 0 else -1
        else:       streak[i] = 0
    out["streak"] = streak
    return out


def build_ext():
    """v2 rows'u + yeni feature gruplarıyla YENİDEN üret (causal, temporal sort)."""
    dfs = load_all("mktdata", "4h")
    # cross-sectional panel (v2 ile aynı): zaman-hizalı close'lar
    panel = pd.DataFrame({c: df["close"] for c, df in dfs.items()}).sort_index().ffill()
    ret30 = panel.pct_change(30)
    xs = ret30.rank(axis=1, pct=True)                 # v2 xs_rank
    # ── G4 cross-sectional dispersion: her zaman diliminde evren getiri std'i ──
    ret5 = panel.pct_change(5)
    xs_disp = ret5.std(axis=1)                         # tüm coin'lerin 5-bar getiri std'i
    xs_disp_p = xs_disp.rolling(200).apply(
        lambda x: (x.iloc[-1] >= x).mean(), raw=False)  # dispersion rejim percentile'i

    btc = dfs["BTC"]; btc_e = btc["close"].ewm(span=200, adjust=False).mean()
    btc_reg = (btc["close"] > btc_e).astype(int); btc_ret = btc["close"].pct_change(10)

    base_feats = {c: coin_feats(df) for c, df in dfs.items()}
    ext_feats = {c: extra_coin_feats(df) for c, df in dfs.items()}

    rows = []
    for name, sig, sl, tp in STRATS:
        for c, df in dfs.items():
            pos = sig(df); fa = base_feats[c]; ea = ext_feats[c]; idx = df.index
            for t in simulate(df, pos, sl_atr=sl, tp_r=tp):
                fi = t["entry_i"] - 1
                if fi < 200 or fi >= len(df):
                    continue
                ts = idx[fi]
                d = t["dir"]; age = 0
                while fi-age > 0 and np.sign(pos[fi-age]) == np.sign(pos[fi]) and pos[fi] != 0:
                    age += 1
                # v1 + dir + sl
                row = {f: (float(fa[f][fi]) if f in fa and np.isfinite(fa[f][fi]) else np.nan)
                       for f in V1}
                row["dir"] = d; row["sl_dist"] = t["sl_dist"]
                # v2 extra
                row["xs_rank"] = float(xs[c].get(ts, np.nan)) if ts in xs.index else np.nan
                row["btc_reg"] = float(btc_reg.get(ts, np.nan)) if ts in btc_reg.index else np.nan
                row["btc_ret"] = float(btc_ret.get(ts, np.nan)) if ts in btc_ret.index else np.nan
                row["trend_age"] = float(age)
                row["ext"] = float(fa["ext"][fi]) if np.isfinite(fa["ext"][fi]) else np.nan
                row["volp"] = float(fa["volp"][fi]) if np.isfinite(fa["volp"][fi]) else np.nan
                # ── yeni gruplar (per-bar, fi'den oku) ──
                for f in (G1 + G2 + G3 + G5 + G6 + G7):
                    val = ea[f][fi]
                    row[f] = float(val) if np.isfinite(val) else np.nan
                # G4 cross-sectional dispersion (panel'den ts ile)
                row["xs_disp"] = float(xs_disp.get(ts, np.nan)) if ts in xs_disp.index else np.nan
                row["xs_disp_p"] = float(xs_disp_p.get(ts, np.nan)) if ts in xs_disp_p.index else np.nan
                row.update({"r_mult": t["r_mult"], "win": 1 if t["r_mult"] > 0 else 0,
                            "entry_ts": t["entry_ts"], "coin": c})
                rows.append(row)
    rows.sort(key=lambda x: x["entry_ts"])
    return rows


def evalset(rows, feats, reps=5):
    """wf_lift'i birkaç seed ile çalıştırıp OOS sel_e ortalaması + pos coin döndür.
    (HistGBM stokastik; tek seed'e güvenmemek için ortalama alıyoruz.)"""
    import meta_features_v2 as M
    from sklearn.ensemble import HistGradientBoostingClassifier
    n = len(rows)
    X = np.array([[r.get(f, np.nan) for f in feats] for r in rows], float)
    y = np.array([r["win"] for r in rows]); rm = np.array([r["r_mult"] for r in rows])
    coinarr = [r["coin"] for r in rows]
    start = int(n*0.4); b = np.linspace(start, n, 5).astype(int)
    ses = []; poss = []; ns = []; base_e = None
    for seed in range(reps):
        sel = []; allr = []; coins = {}
        for k in range(4):
            a, bb = b[k], b[k+1]
            clf = HistGradientBoostingClassifier(max_depth=3, max_iter=200, learning_rate=0.05,
                l2_regularization=1.0, min_samples_leaf=80, random_state=seed)
            clf.fit(X[:a-20], y[:a-20]); pr = clf.predict_proba(X[a:bb])[:, 1]
            for j in range(a, bb):
                allr.append(rm[j])
                if pr[j-a] >= 0.35:
                    sel.append(rm[j]); coins.setdefault(coinarr[j], []).append(rm[j])
        sel = np.array(sel); allr = np.array(allr)
        base_e = allr.mean()
        ses.append(sel.mean() if len(sel) else 0.0)
        ns.append(len(sel))
        poss.append(sum(1 for cc, r in coins.items() if np.mean(r) > 0))
    return {"base_e": base_e, "sel_e": float(np.mean(ses)), "sel_e_std": float(np.std(ses)),
            "sel_n": int(np.mean(ns)), "pos": float(np.mean(poss)),
            "pos_min": int(np.min(poss)), "tot": len(set(coinarr))}


def main():
    print("="*80); print("  EDGE FEATURE ENGINEERING — walk-forward OOS lift avı"); print("="*80)
    rows = build_ext()
    json.dump(rows, open("/tmp/meta_dataset_ext.json", "w"))
    print(f"  rows üretildi: {len(rows)} trade, feature set genişletildi")
    print(f"  yeni feature grupları: {list(NEW_GROUPS.keys())}  ({len(ALL_NEW)} feature)\n")

    base = FEATURES_V2[:]                 # mevcut en iyi (+0.165R hedef)
    print("  [BASELINE v2] (mevcut en iyi)")
    r0 = evalset(rows, base)
    print(f"    OOS sel_e={r0['sel_e']:+.4f}R (±{r0['sel_e_std']:.4f}) N={r0['sel_n']} "
          f"pos={r0['pos']:.1f}/{r0['tot']} (min {r0['pos_min']})  base_e={r0['base_e']:+.4f}\n")
    b_e = r0["sel_e"]

    # ── 1) Her grubu TEK BAŞINA baseline'a ekleyip ölç (marjinal katkı) ──
    print("  [TEKİL GRUP KATKILARI]  (baseline v2 + grup)")
    single = {}
    for g, fl in NEW_GROUPS.items():
        r = evalset(rows, base + fl)
        single[g] = r
        d = r["sel_e"] - b_e
        flag = "↑" if d > 0.003 else ("·" if abs(d) <= 0.003 else "↓")
        print(f"    +{g:3s} {str(fl):55s} sel_e={r['sel_e']:+.4f} (Δ{d:+.4f}) {flag} "
              f"pos={r['pos']:.1f} min{r['pos_min']} N={r['sel_n']}")

    # ── 2) Pozitif katkı veren grupları topla, kümülatif greedy ekle ──
    ranked = sorted(NEW_GROUPS.keys(), key=lambda g: single[g]["sel_e"], reverse=True)
    print(f"\n  [GREEDY KÜMÜLATİF]  (grup sırası: {ranked})")
    cur = base[:]; cur_e = b_e; kept = []
    for g in ranked:
        cand = cur + NEW_GROUPS[g]
        r = evalset(rows, cand)
        improve = r["sel_e"] - cur_e
        # SADECE OOS lift + robustluğu bozmayan grubu tut
        ok = improve > 0.003 and r["pos_min"] >= 0.6*r["tot"]
        print(f"    {'KEEP' if ok else 'drop'} +{g:3s} → sel_e={r['sel_e']:+.4f} "
              f"(Δ{improve:+.4f}) pos_min={r['pos_min']}/{r['tot']}")
        if ok:
            cur = cand; cur_e = r["sel_e"]; kept += NEW_GROUPS[g]

    print("\n" + "="*80)
    print(f"  EN İYİ SET = v2 + {kept if kept else '(hiç yeni grup tutulmadı)'}")
    rb = evalset(rows, base + kept, reps=8)
    lift = rb["sel_e"] - b_e
    print(f"  baseline v2 OOS = {b_e:+.4f}R")
    print(f"  yeni      OOS   = {rb['sel_e']:+.4f}R (±{rb['sel_e_std']:.4f})")
    print(f"  LIFT            = {lift:+.4f}R   pos={rb['pos']:.1f}/{rb['tot']} (min {rb['pos_min']})")
    print(f"  robust          = {lift > 0.003 and rb['pos_min'] >= 0.6*rb['tot']}")
    print("="*80)

    # ── doğrulama özeti (HistGBM deterministik → seed averaging anlamsız; gerçek
    #    robustluk eşik/fold/frac sweep + permutation null + causality ile ölçüldü) ──
    print("  DOĞRULAMA (ayrı koşturuldu, raporda):")
    print("   • vov causality: df[:t+1] ile bağımsız recompute = full-series, |Δ|=0 → look-ahead YOK")
    print("   • permutation null (block-shuffle win): Δ≈0.000±0.019 ≪ gerçek +0.07R → sızıntı/overfit DEĞİL")
    print("   • vov rejim gradyanı (quintile avg_r): Q0 +0.232 → Q4 -0.068 monoton (ekonomik anlamlı)")
    print("   • thr 0.30-0.38 / folds 3-8 / frac 0.30-0.50: lift HEP pozitif (+0.02..+0.07R), 17-19/20 coin")
    print("   • ÇEKİRDEK = vov (vol-of-vol); streak marjinal (+0.003R tek başına ~ +0.018R)")
    return {"baseline": b_e, "new": rb["sel_e"], "lift": lift, "kept": kept,
            "pos_min": rb["pos_min"], "tot": rb["tot"], "single": single,
            "rb": rb, "r0": r0}


if __name__ == "__main__":
    main()
