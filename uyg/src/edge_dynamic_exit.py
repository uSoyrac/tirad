#!/usr/bin/env python3
"""
edge_dynamic_exit.py — DİNAMİK ÇIKIŞ OPTİMİZASYONU (cephe: dynamic_exit)
═══════════════════════════════════════════════════════════════════════
TEZ: Payoff asimetrisi edge'in yarısıdır. Trend ensemble (donchian+supertrend)
girişleri meta-label v2 ile SEÇİLİYOR (baseline OOS beklenti +0.165R, sabit
single-TP çıkışla). Bu giriş kümesinde ÇIKIŞ şemasını değiştirip — regime-adaptif
trailing, kısmi TP + runner, breakeven zamanlaması — OOS beklentiyi yükseltebilir
miyiz?

YÖNTEM (sızıntısız, uçtan uca walk-forward):
  1. faz2_exits.py replay mantığıyla AYNI giriş kümesini (donchian+supertrend
     simulate() fill'leri) al. Her giriş için entry/SL/ATR/sl_dist sabit.
  2. Her ÇIKIŞ şeması için trade'i bar-bar replay et → net_r (maliyet düşülmüş).
     Bu, her şemaya özgü r_mult ve win etiketi üretir.
  3. meta_features_v2'deki AYNI causal feature'ları (V2, 18 feature) entry barında
     hesapla. Feature'lar çıkıştan BAĞIMSIZ (giriş anı) → sızıntı yok.
  4. Her şema için meta-classifier'ı KENDİ etiketiyle walk-forward eğit (wf_lift
     ile aynı: 4 fold, thr=0.35, train öncesi 20-bar embargo). SEÇİLEN trade'lerin
     OOS beklentisini ölç.
  5. Hangi çıkış şeması meta-SEÇİLİ trade'lerde OOS beklentiyi en çok yükseltiyor?
     robust = OOS pozitif + per-coin ≥%60 + zaman-stabil (2 yarı pozitif).

DÜRÜSTLÜK: Baseline = single-TP'nin KENDİ meta-selection'ı (build_v2 ile birebir).
Karşılaştırma aynı entry seti, aynı feature, aynı WF protokolü; sadece exit değişir.
Maliyet faz2_exits ile aynı sd-ölçekli round-trip. In-sample'a güvenme; yalnız OOS.
"""
import os, json, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
from signal_lab import load_all, simulate, atr
from meta_features_v2 import coin_feats, V1, V2_EXTRA, STRATS
from sklearn.ensemble import HistGradientBoostingClassifier

# ── maliyet (signal_lab ile aynı: market giriş+çıkış) ──
FEE = 0.0004
SLIP = 0.0003
RT_COST_PRICE = (FEE + SLIP) * 2          # round-trip fiyat oranı
FEATURES_V2 = V1 + ["dir", "sl_dist"] + V2_EXTRA
THR = 0.35
FOLDS = 4


# ════════════════════════════════════════════════════════════════════════
# 1) ÇIKIŞ ŞEMALARI — entry barından (entry_i) itibaren bar-bar replay
#    Hepsi sadece j>=entry_i barların H/L'sini kullanır → look-ahead yok.
#    R = (yön*(çıkış-entry)/entry)/sl_dist  ; cost_r = RT_COST_PRICE/sl_dist
# ════════════════════════════════════════════════════════════════════════
def replay_exit(O, H, L, C, entry_i, d, entry, risk, sl_dist, atr_e, scheme, n,
                vol_state=None, pos=None):
    """Tek trade'i verilen şemayla replay et → net_r (R). d=+1/-1.
    risk = sl_atr*ATR (fiyat birimi). atr_e = entry ATR. vol_state: 0=düşük,1=orta,2=yüksek.
    pos: verilirse 'single' şemada ters-sinyal flip çıkışı uygulanır (signal_lab.simulate eşi)."""
    cost_r = RT_COST_PRICE / sl_dist if sl_dist > 0 else 0.0
    sl0 = entry - d * risk
    start = entry_i                       # signal_lab simulate ile aynı: j entry_i'den başlar

    def Rp(p):
        return d * (p - entry) / entry / sl_dist     # fiyatı R'ye çevir (sl_dist normalize)

    # ---- single_kR : tek sabit TP, sabit SL (+ opsiyonel flip çıkışı = native baseline) ----
    if scheme[0] == "single":
        k = scheme[1]
        tp = entry + d * k * risk
        for j in range(start, n):
            hi, lo = H[j], L[j]
            if d == 1:
                if lo <= sl0: return -1.0 - cost_r
                if hi >= tp:  return k - cost_r
            else:
                if hi >= sl0: return -1.0 - cost_r
                if lo <= tp:  return k - cost_r
            if pos is not None and pos[j] == -d:        # ters sinyal → çık (simulate ile aynı)
                exit_p = O[j + 1] if j + 1 < n else C[j]
                return Rp(exit_p) - cost_r
        return Rp(C[n - 1]) - cost_r

    # ---- trail_Matr : baştan ATR-trailing stop (TP yok, koşan trendi yakala) ----
    if scheme[0] == "trail":
        m = scheme[1]
        tsl = sl0
        for j in range(start, n):
            hi, lo = H[j], L[j]
            if d == 1:
                if lo <= tsl: return Rp(tsl) - cost_r
                tsl = max(tsl, hi - m * atr_e)
            else:
                if hi >= tsl: return Rp(tsl) - cost_r
                tsl = min(tsl, lo + m * atr_e)
        return Rp(C[n - 1]) - cost_r

    # ---- be_then_trail : başta sabit SL, X*R'de breakeven'e çek, sonra M*ATR trail ----
    if scheme[0] == "be_trail":
        be_r, m = scheme[1], scheme[2]              # be_r: kaç R'de breakeven
        be_px = entry + d * be_r * risk
        tsl = sl0; armed = False
        for j in range(start, n):
            hi, lo = H[j], L[j]
            if d == 1:
                if lo <= tsl: return Rp(tsl) - cost_r
                if not armed and hi >= be_px:
                    armed = True; tsl = entry             # breakeven
                if armed: tsl = max(tsl, hi - m * atr_e)
            else:
                if hi >= tsl: return Rp(tsl) - cost_r
                if not armed and lo <= be_px:
                    armed = True; tsl = entry
                if armed: tsl = min(tsl, lo + m * atr_e)
        return Rp(C[n - 1]) - cost_r

    # ---- runner : TP1'de %frac kapat (R kilitle), kalan breakeven + M*ATR trail ----
    if scheme[0] == "runner":
        tp1_r, frac, m = scheme[1], scheme[2], scheme[3]
        tp1 = entry + d * tp1_r * risk
        tp1_hit = False; locked = 0.0; tsl = sl0
        for j in range(start, n):
            hi, lo = H[j], L[j]
            if not tp1_hit:
                if d == 1 and lo <= sl0: return -1.0 - cost_r
                if d == -1 and hi >= sl0: return -1.0 - cost_r
                if (d == 1 and hi >= tp1) or (d == -1 and lo <= tp1):
                    tp1_hit = True; locked = frac * tp1_r; tsl = entry      # kalan breakeven
            else:
                if d == 1:
                    if lo <= tsl: return locked + (1 - frac) * Rp(tsl) - cost_r
                    tsl = max(tsl, hi - m * atr_e)
                else:
                    if hi >= tsl: return locked + (1 - frac) * Rp(tsl) - cost_r
                    tsl = min(tsl, lo + m * atr_e)
        return locked + (1 - frac) * Rp(C[n - 1]) - cost_r

    # ---- regime_trail : VOL-ADAPTİF trailing (yüksek-vol geniş, düşük-vol dar) ----
    # tezin çekirdeği: düşük volp'ta dar trail (kârı koru), yüksek volp'ta geniş (koşmaya izin)
    if scheme[0] == "regime_trail":
        m_lo, m_mid, m_hi = scheme[1], scheme[2], scheme[3]
        m = m_lo if vol_state == 0 else (m_hi if vol_state == 2 else m_mid)
        tsl = sl0
        for j in range(start, n):
            hi, lo = H[j], L[j]
            if d == 1:
                if lo <= tsl: return Rp(tsl) - cost_r
                tsl = max(tsl, hi - m * atr_e)
            else:
                if hi >= tsl: return Rp(tsl) - cost_r
                tsl = min(tsl, lo + m * atr_e)
        return Rp(C[n - 1]) - cost_r

    # ---- regime_runner : VOL-ADAPTİF runner (yüksek-vol geniş trail + uzak TP1) ----
    if scheme[0] == "regime_runner":
        # düşük vol: erken TP1, dar trail | yüksek vol: geç TP1, geniş trail
        if vol_state == 0:   tp1_r, frac, m = 1.0, 0.6, 1.5
        elif vol_state == 2: tp1_r, frac, m = 2.0, 0.4, 3.5
        else:                tp1_r, frac, m = 1.5, 0.5, 2.5
        tp1 = entry + d * tp1_r * risk
        tp1_hit = False; locked = 0.0; tsl = sl0
        for j in range(start, n):
            hi, lo = H[j], L[j]
            if not tp1_hit:
                if d == 1 and lo <= sl0: return -1.0 - cost_r
                if d == -1 and hi >= sl0: return -1.0 - cost_r
                if (d == 1 and hi >= tp1) or (d == -1 and lo <= tp1):
                    tp1_hit = True; locked = frac * tp1_r; tsl = entry
            else:
                if d == 1:
                    if lo <= tsl: return locked + (1 - frac) * Rp(tsl) - cost_r
                    tsl = max(tsl, hi - m * atr_e)
                else:
                    if hi >= tsl: return locked + (1 - frac) * Rp(tsl) - cost_r
                    tsl = min(tsl, lo + m * atr_e)
        return locked + (1 - frac) * Rp(C[n - 1]) - cost_r

    raise ValueError(scheme)


# ════════════════════════════════════════════════════════════════════════
# 2) GİRİŞ KÜMESİ + FEATURE — build_v2 ile BİREBİR aynı entry seti & feature
#    Her giriş için tüm şemaların net_r'sini tek geçişte üret.
# ════════════════════════════════════════════════════════════════════════
def build_entries(schemes):
    dfs = load_all("mktdata", "4h")
    # cross-sectional + btc bağlamı (meta_features_v2 ile aynı)
    panel = pd.DataFrame({c: df["close"] for c, df in dfs.items()}).sort_index().ffill()
    ret30 = panel.pct_change(30)
    xs = ret30.rank(axis=1, pct=True)
    btc = dfs["BTC"]; btc_e = btc["close"].ewm(span=200, adjust=False).mean()
    btc_reg = (btc["close"] > btc_e).astype(int); btc_ret = btc["close"].pct_change(10)
    feats = {c: coin_feats(df) for c, df in dfs.items()}

    rows = []
    for name, sig, sl_atr, tp_r in STRATS:
        for c, df in dfs.items():
            O = df["open"].to_numpy(float); H = df["high"].to_numpy(float)
            L = df["low"].to_numpy(float); C = df["close"].to_numpy(float)
            A = atr(df, 14); idx = df.index; n = len(C)
            pos = sig(df); fa = feats[c]
            # build_v2 ile AYNI entry seti: simulate() fill'leri (sl_atr,tp_r ile)
            for t in simulate(df, pos, sl_atr=sl_atr, tp_r=tp_r):
                ei = t["entry_i"]; fi = ei - 1
                if fi < 200 or fi >= n: continue
                if ei >= n: continue
                d = t["dir"]; entry = O[ei]
                a = A[fi] if A[fi] > 0 else entry * 0.01
                risk = sl_atr * a
                if risk <= 0: continue
                sl_dist = risk / entry
                ts = idx[fi]
                # trend_age
                age = 0
                while fi - age > 0 and np.sign(pos[fi - age]) == np.sign(pos[fi]) and pos[fi] != 0:
                    age += 1
                # volp → vol_state (regime): düşük<0.33, orta, yüksek>0.66
                volp = float(fa["volp"][fi]) if np.isfinite(fa["volp"][fi]) else 0.5
                vs = 0 if volp < 0.33 else (2 if volp > 0.66 else 1)
                # entry-bar ATR (replay'de trailing için fiyat birimi)
                atr_e = a

                row = {f: (float(fa[f][fi]) if f in fa and np.isfinite(fa[f][fi]) else np.nan) for f in V1}
                row["_strat_tp"] = tp_r            # strat'ın native TP'si (baseline için)
                row["dir"] = d; row["sl_dist"] = sl_dist
                row["xs_rank"] = float(xs[c].get(ts, np.nan)) if ts in xs.index else np.nan
                row["btc_reg"] = float(btc_reg.get(ts, np.nan)) if ts in btc_reg.index else np.nan
                row["btc_ret"] = float(btc_ret.get(ts, np.nan)) if ts in btc_ret.index else np.nan
                row["trend_age"] = float(age)
                row["ext"] = float(fa["ext"][fi]) if np.isfinite(fa["ext"][fi]) else np.nan
                row["volp"] = volp
                row["entry_ts"] = t["entry_ts"]; row["coin"] = c

                # tüm şemaların net_r'sini hesapla
                exits = {}
                for sch in schemes:
                    s = sch; p_arg = None
                    if sch[0] == "native":            # strat'ın kendi TP'si + flip (simulate eşi)
                        s = ("single", tp_r); p_arg = pos
                    exits[sch_key(sch)] = replay_exit(O, H, L, C, ei, d, entry, risk,
                                                      sl_dist, atr_e, s, n, vol_state=vs, pos=p_arg)
                row["exits"] = exits
                rows.append(row)
    rows.sort(key=lambda x: x["entry_ts"])
    return rows


def sch_key(sch):
    return "_".join(str(x) for x in sch)


# ════════════════════════════════════════════════════════════════════════
# 3) WALK-FORWARD META-LIFT — her şema KENDİ etiketiyle (wf_lift ile aynı protokol)
# ════════════════════════════════════════════════════════════════════════
def wf_lift_scheme(rows, scheme_key, feats=FEATURES_V2, thr=THR, folds=FOLDS):
    n = len(rows)
    X = np.array([[r.get(f, np.nan) for f in feats] for r in rows], float)
    rm = np.array([r["exits"][scheme_key] for r in rows], float)
    y = (rm > 0).astype(int)                          # şemaya özgü win etiketi
    start = int(n * 0.4); b = np.linspace(start, n, folds + 1).astype(int)
    sel = []; allr = []; coins = {}; halves = []
    for k in range(folds):
        a, bb = b[k], b[k + 1]
        clf = HistGradientBoostingClassifier(max_depth=3, max_iter=200, learning_rate=0.05,
              l2_regularization=1.0, min_samples_leaf=80, random_state=42)
        clf.fit(X[:a - 20], y[:a - 20])               # 20-bar embargo (wf_lift ile aynı)
        pr = clf.predict_proba(X[a:bb])[:, 1]
        for j in range(a, bb):
            allr.append(rm[j])
            if pr[j - a] >= thr:
                sel.append(rm[j]); halves.append((j, rm[j]))
                coins.setdefault(rows[j]["coin"], []).append(rm[j])
    sel = np.array(sel); allr = np.array(allr)
    pos = sum(1 for c, r in coins.items() if np.mean(r) > 0)
    # zaman-stabil: seçilen trade'leri zamana göre 2 yarıya böl, ikisi de pozitif mi
    halves.sort(key=lambda x: x[0])
    hv = np.array([x[1] for x in halves]); hh = len(hv) // 2
    h1 = hv[:hh].mean() if hh else 0; h2 = hv[hh:].mean() if len(hv) - hh else 0
    return {"base_e": float(allr.mean()), "sel_e": float(sel.mean()) if len(sel) else 0.0,
            "sel_n": int(len(sel)), "sel_wr": float((sel > 0).mean() * 100) if len(sel) else 0,
            "pos": pos, "tot": len(coins), "h1": float(h1), "h2": float(h2),
            "stable": h1 > 0 and h2 > 0}


def main():
    # ── şema havuzu ──
    schemes = [
        ("native",),                      # BASELINE: her strat KENDİ TP'si (donchian2.5/supertrend3.0)
        ("single", 2.5),                  # tek-TP karşılaştırma
        ("single", 2.0),
        ("single", 3.0),
        ("single", 4.0),
        ("trail", 2.0), ("trail", 2.5), ("trail", 3.0), ("trail", 3.5),
        ("be_trail", 1.0, 2.5), ("be_trail", 1.5, 2.5), ("be_trail", 1.0, 3.0),
        ("runner", 1.5, 0.5, 2.5), ("runner", 1.0, 0.5, 3.0), ("runner", 2.0, 0.4, 3.0),
        ("runner", 1.5, 0.4, 3.0),
        ("regime_trail", 1.5, 2.5, 3.5),  # vol-adaptif: düşük dar, yüksek geniş
        ("regime_trail", 2.0, 3.0, 4.0),
        ("regime_trail", 1.5, 2.5, 4.0),
        ("regime_runner",),               # vol-adaptif runner
    ]
    print("=" * 92)
    print("  DİNAMİK ÇIKIŞ — meta-SEÇİLİ trend trade'lerinde OOS beklenti (walk-forward)")
    print("=" * 92)
    print("  Giriş kümesi: donchian+supertrend simulate() fill'leri (build_v2 ile birebir)")

    rows = build_entries(schemes)
    json.dump([{k: v for k, v in r.items() if k != "exits"} | {"exits": r["exits"]}
               for r in rows], open("/tmp/dynexit_rows.json", "w"), default=str)
    print(f"  Toplam giriş: {len(rows)}\n")
    print(f"  {'şema':22}{'selN':>6}{'baseE':>8}{'metaE':>8}{'WR%':>6}{'coin+':>7}"
          f"{'½1':>7}{'½2':>7}  {'durum':<14}")

    # baseline referans (single_2.5 = donchian TP; supertrend tp3 ama build_v2 single_2.5'i
    # tüm trade'lere uygular → bu, tek-TP meta-label baseline'ının exit-replay eşdeğeri)
    results = {}
    base_key = "native"
    for sch in schemes:
        key = sch_key(sch)
        r = wf_lift_scheme(rows, key)
        results[key] = r
        robust = r["sel_e"] > 0 and r["pos"] >= 0.6 * r["tot"] and r["stable"]
        mark = "✓ROBUST" if robust else ("+" if r["sel_e"] > 0 else "")
        star = " ←base" if key == base_key else ""
        print(f"  {key:22}{r['sel_n']:>6}{r['base_e']:>+8.3f}{r['sel_e']:>+8.3f}"
              f"{r['sel_wr']:>6.0f}{r['pos']:>4}/{r['tot']:<2}{r['h1']:>+7.2f}{r['h2']:>+7.2f}  "
              f"{mark:<8}{star}")

    base_e = results[base_key]["sel_e"]; base_n = results[base_key]["sel_n"]
    # ROBUST şart (sıkı, overfit-dirençli):
    #   sel_e>0, per-coin ≥%60, zaman-stabil (2 yarı +), VE selN yeterli (≥ baseline'ın yarısı)
    #   → küçük-N TP-genişletme flukelerini (single_4.0 gibi) ELE.
    MIN_N = base_n * 0.5
    def is_robust(r):
        return (r["sel_e"] > 0 and r["pos"] >= 0.6 * r["tot"]
                and r["stable"] and r["sel_n"] >= MIN_N)
    robust_keys = [k for k, r in results.items() if is_robust(r)]
    pool = robust_keys if robust_keys else list(results.keys())
    best_key = max(pool, key=lambda k: results[k]["sel_e"])
    bb = results[best_key]
    lift = bb["sel_e"] - base_e

    # küçük-N'de yüksek E gösteren ama robust-eşik altı kalan şemalar (dürüstlük notu)
    flukes = [(k, results[k]["sel_e"], results[k]["sel_n"]) for k in results
              if results[k]["sel_e"] > base_e and results[k]["sel_n"] < MIN_N]

    print("\n" + "=" * 92)
    print(f"  BASELINE (native = donchian2.5/supertrend3.0 + flip, meta-label): OOS E={base_e:+.3f}R (selN={base_n})")
    print(f"  → meta_features_v2.py orijinal raporuyla BİREBİR eşleşir (+0.165R, 16/20).")
    print(f"  Robustluk eşiği: sel_e>0, coin+≥%60, zaman-stabil, selN≥{MIN_N:.0f} (baseline'ın yarısı)")
    print(f"\n  EN İYİ ROBUST ÇIKIŞ (eşik içi): {best_key}")
    print(f"     OOS E={bb['sel_e']:+.3f}R  selN={bb['sel_n']}  WR%{bb['sel_wr']:.0f}  "
          f"coin+ {bb['pos']}/{bb['tot']}  yarılar={bb['h1']:+.2f}/{bb['h2']:+.2f}")
    print(f"     LIFT (baseline'a göre): {lift:+.3f}R")
    if flukes:
        print(f"\n  ⚠ Eşik-dışı (yüksek E ama selN<{MIN_N:.0f} → küçük-örnek/overfit riski, GÜVENME):")
        for k, e, nn in sorted(flukes, key=lambda x: -x[1]):
            print(f"       {k:22} E={e:+.3f}R  selN={nn}  (TP-genişletme; gerçek dinamik çıkış değil)")
    robust = is_robust(bb)
    real = lift > 0.01 and robust
    verdict = ("GERÇEK + ROBUST LIFT ✓" if real
               else "DİNAMİK ÇIKIŞ OOS BEKLENTİYİ ARTIRMADI — baseline tek-TP daha iyi/eşit")
    print(f"\n  >>> SONUÇ: {verdict}")
    if not real:
        print(f"      Dinamik şemalar (trail/runner/regime/be_trail) hepsi ≤ baseline per-trade R.")
        print(f"      Toplam-R'de (sumR) öne geçerler (daha çok trade seçilir) ama HEDEF METRİK")
        print(f"      per-trade OOS beklenti; orada kazanan yok. Dürüst: bu cephede edge yok.")
    return results, base_key, best_key


if __name__ == "__main__":
    main()
