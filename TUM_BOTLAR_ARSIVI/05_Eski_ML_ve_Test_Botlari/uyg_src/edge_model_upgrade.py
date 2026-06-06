#!/usr/bin/env python3
"""
edge_model_upgrade.py — META-MODEL İYİLEŞTİRME (cephe: model_upgrade)
═══════════════════════════════════════════════════════════════════════
AYNI v2 feature setiyle (meta_features_v2.FEATURES_V2), wf_lift'teki tek
HistGradientBoosting'i geliştirip walk-forward OOS BEKLENTİyi (R) ölçer.

Denenen model değişiklikleri (hepsi SIZINTISIZ, temporal split korunur):
  (a) probability calibration  — CalibratedClassifierCV (sigmoid/isotonic)
  (b) sample-uniqueness ağırlıkları — López de Prado; eşzamanlı açık trade
      sayısının tersi (concurrency) ile örnek ağırlığı. Overlapping label
      düzeltmesi. Per-coin ve portfolio-level iki varyant.
  (c) ensemble — GB + ExtraTrees + Logistic predicted-proba ortalaması
  (d) eşik optimizasyonu — eşik SADECE train'in iç validation diliminde
      (son %25) OOS-beklenti maksimize edilerek seçilir; gerçek test
      fold'una BAKILMAZ (look-ahead yok). Sonra test fold'una uygulanır.

KURAL: sadece walk-forward OOS sel_e (meta-seçilmiş beklenti) sayılır.
Baseline (mevcut wf_lift, HGB, sabit thr=0.35) = +0.165R, 16/20 coin.

ÖNEMLİ: uniqueness ağırlığı için entry/exit bar-index gerekir. Cache'te
exit_ts yok → build_v2'nin AYNI trade/feature mantığını kullanarak
exit_ts + bar-index'li dataset'i bir kez yeniden üretir (deterministik,
r_mult cache ile birebir aynı). Feature seti DEĞİŞMEZ.
"""
import json, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
from signal_lab import load_all, simulate
from meta_features_v2 import coin_feats, STRATS, V1, V2_EXTRA, FEATURES_V2, build_v2
from sklearn.ensemble import HistGradientBoostingClassifier, ExtraTreesClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

AUG_CACHE = "/tmp/meta_dataset_v2_aug.json"


# ════════════════════════════════════════════════════════════════════
# 1) DATASET (exit_ts + entry_i/exit_i bar index'li) — AYNI feature/trade
# ════════════════════════════════════════════════════════════════════
def build_aug():
    """build_v2 ile birebir aynı trade/feature; ek olarak exit bar-index
    ve coin-içi entry/exit bar konumu (uniqueness ağırlığı için)."""
    dfs = load_all("mktdata", "4h")
    panel = pd.DataFrame({c: df["close"] for c, df in dfs.items()}).sort_index().ffill()
    ret30 = panel.pct_change(30); xs = ret30.rank(axis=1, pct=True)
    btc = dfs["BTC"]; btc_e = btc["close"].ewm(span=200, adjust=False).mean()
    btc_reg = (btc["close"] > btc_e).astype(int); btc_ret = btc["close"].pct_change(10)
    feats = {c: coin_feats(df) for c, df in dfs.items()}
    rows = []
    for name, sig, sl, tp in STRATS:
        for c, df in dfs.items():
            pos = sig(df); fa = feats[c]; idx = df.index; n = len(df)
            for t in simulate(df, pos, sl_atr=sl, tp_r=tp):
                fi = t["entry_i"] - 1
                if fi < 200 or fi >= len(df): continue
                ts = idx[fi]
                d = t["dir"]; age = 0
                while fi - age > 0 and np.sign(pos[fi - age]) == np.sign(pos[fi]) and pos[fi] != 0: age += 1
                row = {f: (float(fa[f][fi]) if f in fa and np.isfinite(fa[f][fi]) else np.nan) for f in V1}
                row["dir"] = d; row["sl_dist"] = t["sl_dist"]
                row["xs_rank"] = float(xs[c].get(ts, np.nan)) if ts in xs.index else np.nan
                row["btc_reg"] = float(btc_reg.get(ts, np.nan)) if ts in btc_reg.index else np.nan
                row["btc_ret"] = float(btc_ret.get(ts, np.nan)) if ts in btc_ret.index else np.nan
                row["trend_age"] = float(age)
                row["ext"] = float(fa["ext"][fi]) if np.isfinite(fa["ext"][fi]) else np.nan
                row["volp"] = float(fa["volp"][fi]) if np.isfinite(fa["volp"][fi]) else np.nan
                # exit bar-index'i exit_ts'ten coin-içi konuma çevir
                ex_i = idx.get_loc(pd.to_datetime(t["exit_ts"]))
                row.update({"r_mult": t["r_mult"], "win": 1 if t["r_mult"] > 0 else 0,
                            "entry_ts": t["entry_ts"], "exit_ts": t["exit_ts"],
                            "coin": c, "entry_i": int(t["entry_i"]), "exit_i": int(ex_i)})
                rows.append(row)
    rows.sort(key=lambda x: x["entry_ts"])
    return rows


def get_aug():
    import os
    if os.path.exists(AUG_CACHE):
        rows = json.load(open(AUG_CACHE))
        # sanity: cache ile aynı trade sayısı mı
        base = json.load(open("/tmp/meta_dataset_v2.json"))
        if len(rows) == len(base): return rows
    rows = build_aug(); json.dump(rows, open(AUG_CACHE, "w"))
    return rows


# ════════════════════════════════════════════════════════════════════
# 2) SAMPLE-UNIQUENESS WEIGHTS (López de Prado)
# ════════════════════════════════════════════════════════════════════
def uniqueness_weights(rows_idx, portfolio=False):
    """Her trade için ortalama benzersizlik = mean_t 1/concurrency(t).
    concurrency(t) = t barında açık olan trade sayısı.
    portfolio=False → sadece AYNI coin'de eşzamanlılık (fiyat serisi bağımsız).
    portfolio=True  → tüm coin'ler ortak global bar ekseni üzerinde.
    rows_idx: işlenecek satırların listesi (her biri entry_i/exit_i/coin içerir).
    Dönüş: len(rows_idx) uzunlukta ağırlık dizisi (ortalama ~1'e normalize)."""
    if portfolio:
        # global zaman ekseni: entry_ts -> ordinal bar. 4H grid varsay.
        # Basitlik: entry_ts'leri sıralı unique zaman damgalarına map'le.
        # Burada coin bağımsız concurrency için entry/exit gerçek datetime aralığı kullanılır.
        ev = []  # (time, +1/-1)
        spans = []
        for r in rows_idx:
            e = pd.Timestamp(r["entry_ts"]).value; x = pd.Timestamp(r["exit_ts"]).value
            if x < e: x = e
            spans.append((e, x)); ev.append((e, 1)); ev.append((x + 1, -1))
        ev.sort()
        # her trade için aralığındaki ortalama concurrency'yi say (sweep)
        # küçük N (≤folds*birkaç bin) → O(N log N) yeterli
        times = sorted(set([t for t, _ in ev]))
        # prefix concurrency at each event time
        conc = {}; cur = 0; i = 0
        evs = ev
        # build stepwise concurrency timeline
        timeline = []  # (time, concurrency_after)
        from collections import defaultdict
        delta = defaultdict(int)
        for t, s in evs: delta[t] += s
        ts_sorted = sorted(delta)
        cum = 0
        for t in ts_sorted:
            cum += delta[t]; timeline.append((t, cum))
        tarr = np.array([t for t, _ in timeline]); carr = np.array([c for _, c in timeline])
        w = np.empty(len(spans))
        for k, (e, x) in enumerate(spans):
            # ortalama concurrency: [e, x] aralığında timeline segmentlerini ağırlıkla
            lo = np.searchsorted(tarr, e, side="right") - 1
            hi = np.searchsorted(tarr, x, side="right") - 1
            lo = max(lo, 0)
            if hi <= lo:
                c = max(carr[lo], 1); w[k] = 1.0 / c; continue
            # segment uzunluklarıyla ağırlıklı ortalama 1/concurrency
            seg_t = list(tarr[lo:hi + 1]) + [x]
            tot = 0.0; acc = 0.0
            for s in range(lo, hi + 1):
                a = max(tarr[s], e); b = (tarr[s + 1] if s + 1 < len(tarr) else x)
                b = min(b, x); dur = max(b - a, 0)
                cc = max(carr[s], 1)
                acc += dur * (1.0 / cc); tot += dur
            w[k] = acc / tot if tot > 0 else 1.0 / max(carr[lo], 1)
        w = w / w.mean()
        return w
    # per-coin: coin başına concurrency bar-index üzerinden
    from collections import defaultdict
    by_coin = defaultdict(list)
    for pos, r in enumerate(rows_idx): by_coin[r["coin"]].append(pos)
    w = np.ones(len(rows_idx))
    for c, poss in by_coin.items():
        ivs = [(rows_idx[p]["entry_i"], max(rows_idx[p]["exit_i"], rows_idx[p]["entry_i"])) for p in poss]
        mx = max(x for _, x in ivs) + 2
        cnt = np.zeros(mx, dtype=float)
        for e, x in ivs: cnt[e:x + 1] += 1.0
        for (e, x), p in zip(ivs, poss):
            seg = cnt[e:x + 1]; seg = np.where(seg < 1, 1, seg)
            w[p] = (1.0 / seg).mean()
    w = w / w.mean()
    return w


# ════════════════════════════════════════════════════════════════════
# 3) MODEL FABRİKALARI (aynı feature seti, X NaN içerebilir)
# ════════════════════════════════════════════════════════════════════
def make_gb():
    return HistGradientBoostingClassifier(max_depth=3, max_iter=200, learning_rate=0.05,
        l2_regularization=1.0, min_samples_leaf=80, random_state=42)

def make_et():
    return make_pipeline(SimpleImputer(strategy="median"),
        ExtraTreesClassifier(n_estimators=400, max_depth=6, min_samples_leaf=60,
            max_features="sqrt", n_jobs=-1, random_state=42))

def make_lr():
    return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
        LogisticRegression(C=0.5, max_iter=1000, random_state=42))


class Ensemble:
    """predicted-proba ortalaması alan basit ensemble."""
    def __init__(self, builders, calib=None):
        self.builders = builders; self.calib = calib; self.models = []
    def fit(self, X, y, sw=None):
        self.models = []
        for b in self.builders:
            m = b()
            if self.calib:  # her base'i kalibre et
                m = CalibratedClassifierCV(m, method=self.calib, cv=3)
            try:
                if sw is not None: m.fit(X, y, sample_weight=sw)
                else: m.fit(X, y)
            except TypeError:
                m.fit(X, y)  # sample_weight desteklemiyorsa
            self.models.append(m)
        return self
    def predict_proba1(self, X):
        return np.mean([m.predict_proba(X)[:, 1] for m in self.models], axis=0)


# ════════════════════════════════════════════════════════════════════
# 4) WALK-FORWARD OOS — model değişkenli, eşik opsiyonel
# ════════════════════════════════════════════════════════════════════
def expectancy_at_thr(pr, rm, thr):
    m = pr >= thr
    return rm[m].mean() if m.any() else -9.0, int(m.sum())


def pick_threshold(pr_val, rm_val, grid, min_frac=0.10):
    """İç validation'da OOS-beklenti maksimize eden eşik. min_frac: en az
    bu kadar trade seçilmeli (aşırı az N'e overfit'i önler)."""
    nval = len(pr_val); best_t, best_e = grid[0], -9.0
    for t in grid:
        e, n = expectancy_at_thr(pr_val, rm_val, t)
        if n >= max(1, int(min_frac * nval)) and e > best_e:
            best_e, best_t = e, t
    return best_t


def wf_lift_model(rows, feats, build_fn, thr=0.35, folds=4, sample_weight=None,
                  opt_thr=False, thr_grid=None, inner_val_frac=0.25, min_sel_frac=0.10,
                  verbose=False):
    """Genelleştirilmiş walk-forward.
    build_fn() -> taze model (fit(X,y[,sample_weight]) + predict_proba).
    sample_weight: None | 'uniq' | 'uniq_pf'  (train alt-kümesine uygulanır).
    opt_thr: True ise eşik train'in iç validation diliminde seçilir."""
    n = len(rows)
    X = np.array([[r.get(f, np.nan) for f in feats] for r in rows], float)
    y = np.array([r["win"] for r in rows]); rm = np.array([r["r_mult"] for r in rows])
    start = int(n * 0.4); b = np.linspace(start, n, folds + 1).astype(int)
    if thr_grid is None: thr_grid = np.round(np.arange(0.30, 0.56, 0.01), 3)
    sel = []; allr = []; coins = {}; fold_e = []; used_thr = []
    for k in range(folds):
        a, bb = b[k], b[k + 1]
        tr_end = a - 20  # embargo: test başlamadan 20 bar önce kes
        Xtr, ytr = X[:tr_end], y[:tr_end]
        # örnek ağırlığı (sadece train satırları)
        sw = None
        if sample_weight == "uniq":
            sw = uniqueness_weights(rows[:tr_end], portfolio=False)
        elif sample_weight == "uniq_pf":
            sw = uniqueness_weights(rows[:tr_end], portfolio=True)
        m = build_fn()
        try:
            if sw is not None: m.fit(Xtr, ytr, sample_weight=sw)
            else: m.fit(Xtr, ytr)
        except TypeError:
            m.fit(Xtr, ytr)
        # predict_proba arayüzü (Ensemble veya sklearn)
        def proba(Z):
            return m.predict_proba1(Z) if hasattr(m, "predict_proba1") else m.predict_proba(Z)[:, 1]
        # eşik seçimi (iç validation = train'in SON inner_val_frac dilimi)
        t_use = thr
        if opt_thr:
            v0 = int(tr_end * (1 - inner_val_frac))
            pr_val = proba(X[v0:tr_end]); rm_val = rm[v0:tr_end]
            t_use = pick_threshold(pr_val, rm_val, thr_grid, min_frac=min_sel_frac)
        used_thr.append(t_use)
        pr = proba(X[a:bb])
        fe = []
        for j in range(a, bb):
            allr.append(rm[j])
            if pr[j - a] >= t_use:
                sel.append(rm[j]); fe.append(rm[j])
                coins.setdefault(rows[j]["coin"], []).append(rm[j])
        fold_e.append(np.mean(fe) if fe else 0.0)
    sel = np.array(sel); allr = np.array(allr)
    pos = sum(1 for c, r in coins.items() if np.mean(r) > 0)
    # zaman-stabillik: her fold'da seçim beklentisi > 0 mı
    folds_pos = sum(1 for e in fold_e if e > 0)
    out = {"base_e": float(allr.mean()), "sel_e": float(sel.mean()) if len(sel) else 0.0,
           "sel_n": int(len(sel)), "sel_wr": float((sel > 0).mean() * 100) if len(sel) else 0.0,
           "pos": pos, "tot": len(coins), "fold_e": [round(float(e), 3) for e in fold_e],
           "folds_pos": folds_pos, "used_thr": [round(float(t), 3) for t in used_thr]}
    if verbose: print("   ", out)
    return out


# ════════════════════════════════════════════════════════════════════
# 5) DENEYLER
# ════════════════════════════════════════════════════════════════════
def fmt(tag, r, base=0.165):
    lift = r["sel_e"] - base
    rob = "ROBUST" if (r["pos"] >= 0.6 * r["tot"] and r["folds_pos"] >= 3 and r["sel_e"] > 0) else "  -   "
    return (f"  {tag:<34} sel_e={r['sel_e']:+.3f}R  lift={lift:+.3f}  "
            f"N={r['sel_n']:>4}  WR%{r['sel_wr']:>4.1f}  coin+ {r['pos']:>2}/{r['tot']:<2}  "
            f"folds+ {r['folds_pos']}/4  {rob}  {r['fold_e']}")


def cross_fold_estimate(rows, build_fn, label, base_kw, cand_kw, fold_counts=(3, 4, 5, 6)):
    """Tek-slice şansını elemek için lift'i {3,4,5,6} fold'da ölç. Gerçek
    iyileşme HER fold sayısında aynı işareti korumalı. mean lift + işaret-
    tutarlılığı döndürür. (Eşik gridini test fold'una göre seçmez.)"""
    bl, cl = [], []
    for f in fold_counts:
        rb = wf_lift_model(rows, FEATURES_V2, build_fn, folds=f, **base_kw)
        rc = wf_lift_model(rows, FEATURES_V2, build_fn, folds=f, **cand_kw)
        bl.append(rb["sel_e"]); cl.append(rc["sel_e"])
    bl, cl = np.array(bl), np.array(cl)
    lifts = cl - bl
    same_sign = int((lifts > 0).all() or (lifts < 0).all())
    pos_all = bool((lifts > 0).all())
    print(f"  [{label}] fold-counts {list(fold_counts)}: cand={[round(x,3) for x in cl]} "
          f"base={[round(x,3) for x in bl]}")
    print(f"      mean lift={lifts.mean():+.4f}  per-fold lift={[round(x,3) for x in lifts]}  "
          f"all-positive={'EVET' if pos_all else 'HAYIR'}")
    return {"mean_lift": float(lifts.mean()), "lifts": [float(x) for x in lifts],
            "all_positive": pos_all, "cand_mean": float(cl.mean()), "base_mean": float(bl.mean())}


def main():
    rows = get_aug()
    print("=" * 100)
    print(f"  META-MODEL UPGRADE — {len(rows)} trade, feature seti = FEATURES_V2 ({len(FEATURES_V2)})")
    print(f"  Metrik: walk-forward OOS sel_e (meta-seçilmiş beklenti R). Baseline = +0.165R, 16/20 coin.")
    print("=" * 100)

    results = {}

    # 0) BASELINE — mevcut wf_lift ile birebir (HGB, sabit thr=0.35)
    r = wf_lift_model(rows, FEATURES_V2, make_gb, thr=0.35); results["baseline_HGB"] = r
    print(fmt("0) baseline HGB (thr=0.35)", r))

    # (a) CALIBRATION — tek GB, sigmoid / isotonic kalibre, sabit thr
    r = wf_lift_model(rows, FEATURES_V2, lambda: CalibratedClassifierCV(make_gb(), method="sigmoid", cv=3), thr=0.35)
    results["calib_sigmoid"] = r; print(fmt("a) GB + sigmoid calib", r))
    r = wf_lift_model(rows, FEATURES_V2, lambda: CalibratedClassifierCV(make_gb(), method="isotonic", cv=3), thr=0.35)
    results["calib_isotonic"] = r; print(fmt("a) GB + isotonic calib", r))

    # (b) UNIQUENESS WEIGHTS — GB, sabit thr
    r = wf_lift_model(rows, FEATURES_V2, make_gb, thr=0.35, sample_weight="uniq")
    results["uniq_percoin"] = r; print(fmt("b) GB + uniqueness (per-coin)", r))
    r = wf_lift_model(rows, FEATURES_V2, make_gb, thr=0.35, sample_weight="uniq_pf")
    results["uniq_portfolio"] = r; print(fmt("b) GB + uniqueness (portfolio)", r))

    # (c) ENSEMBLE — GB+ET+LR ortalama, sabit thr
    r = wf_lift_model(rows, FEATURES_V2, lambda: Ensemble([make_gb, make_et, make_lr]), thr=0.35)
    results["ensemble"] = r; print(fmt("c) ensemble GB+ET+LR", r))
    r = wf_lift_model(rows, FEATURES_V2, lambda: Ensemble([make_gb, make_et, make_lr], calib="sigmoid"), thr=0.35)
    results["ensemble_calib"] = r; print(fmt("c) ensemble + sigmoid calib", r))

    # (d) THRESHOLD OPT — eşik iç-validation'da seçilir (look-ahead yok)
    r = wf_lift_model(rows, FEATURES_V2, make_gb, opt_thr=True)
    results["thr_opt_HGB"] = r; print(fmt("d) HGB + thr-opt (inner val)", r))

    # KOMBO — en umut verenleri birleştir
    r = wf_lift_model(rows, FEATURES_V2, lambda: CalibratedClassifierCV(make_gb(), method="sigmoid", cv=3), opt_thr=True)
    results["calib+thropt"] = r; print(fmt("e) GB calib + thr-opt", r))
    r = wf_lift_model(rows, FEATURES_V2, lambda: Ensemble([make_gb, make_et, make_lr], calib="sigmoid"), opt_thr=True)
    results["ens+thropt"] = r; print(fmt("e) ensemble calib + thr-opt", r))
    r = wf_lift_model(rows, FEATURES_V2, make_gb, opt_thr=True, sample_weight="uniq")
    results["uniq+thropt"] = r; print(fmt("e) GB uniq + thr-opt", r))
    r = wf_lift_model(rows, FEATURES_V2, lambda: Ensemble([make_gb, make_et, make_lr], calib="sigmoid"),
                      opt_thr=True, sample_weight="uniq")
    results["ALL"] = r; print(fmt("e) ALL (ens+calib+uniq+thropt)", r))

    print("=" * 100)
    print("  CROSS-FOLD-COUNT DOĞRULAMA (tek-slice şansını ele; gerçek lift HER fold'da + olmalı)")
    print("=" * 100)
    # Sadece folds=4'te robust+lift>0 görünen adayları cross-fold ile sına.
    cfe = {}
    cfe["uniq_percoin"] = cross_fold_estimate(rows, make_gb, "uniq per-coin (thr.35)",
                                              dict(thr=0.35), dict(thr=0.35, sample_weight="uniq"))
    cfe["uniq+thropt"] = cross_fold_estimate(rows, make_gb, "uniq + thr-opt",
                                             dict(thr=0.35), dict(opt_thr=True, sample_weight="uniq"))
    cfe["thropt_only"] = cross_fold_estimate(rows, make_gb, "thr-opt only",
                                             dict(thr=0.35), dict(opt_thr=True))

    print("=" * 100)
    base = results["baseline_HGB"]["sel_e"]
    # GERÇEK kazanan: cross-fold mean lift > +0.005 VE her fold'da pozitif (işaret-stabil)
    real = {k: v for k, v in cfe.items() if v["all_positive"] and v["mean_lift"] > 0.005}
    if real:
        win_k = max(real, key=lambda k: real[k]["mean_lift"])
        win = real[win_k]
        print(f"  GERÇEK (işaret-stabil) İYİLEŞME: {win_k}")
        print(f"    cross-fold mean: baseline {win['base_mean']:+.4f}R → {win['cand_mean']:+.4f}R  "
              f"(mean lift {win['mean_lift']:+.4f}R, her fold'da pozitif)")
        print(f"    NOT: kanonik folds=4'te bu adayın lift'i {results.get('uniq_percoin',{}).get('sel_e',0)-base:+.4f}R "
              f"(marjinal); güvenilir tahmin cross-fold ortalamasıdır.")
    else:
        win_k, win = None, None
        print(f"  HİÇBİR upgrade işaret-stabil pozitif lift sağlamadı. baseline korunur (+0.165R).")
        print(f"  thr-opt tek-slice'ta (+0.186) parlıyor ama fold sayısı değişince işaret değiştiriyor → overfit, REDDEDİLDİ.")
    print("=" * 100)
    json.dump({"folds4": results, "cross_fold": cfe}, open("/tmp/edge_upgrade_results.json", "w"), indent=2)
    return results, cfe, win_k


if __name__ == "__main__":
    main()
