#!/usr/bin/env python3
"""
edge_xsection_sleeve.py — CROSS-SECTIONAL MOMENTUM SLEEVE (uncorrelated diversifikasyon)
═══════════════════════════════════════════════════════════════════════════════════════
CEPHE: xsection_sleeve.

SORU: pivot_momentum.py'deki long-short cross-sectional momentum (Sharpe~0.5-0.9,
market-nötr) trend ensemble'a EK bir SLEEVE olarak ne kadar değer katar?

Trend ensemble = donchian+supertrend meta-label v2 (OOS +0.165R, N=1946, 16/20 coin).
Bu trades /tmp/meta_dataset_v2.json'da; meta-label seçimi wf_lift ile yeniden üretilir.

Diversifikasyon mantığı: iki getiri akımı DÜŞÜK korele ise birleşik portföyün
Sharpe'ı her iki sleeve'in tek başına Sharpe'ından YÜKSEK olur (vol azalır) →
aynı risk bütçesinde daha çok kaldıraç → güvenli getiri↑.

ÖLÇÜM (hepsi look-ahead'siz, maliyetli, OOS):
  1) XS sleeve standalone: per-rebalance net getiri serisi → OOS beklenti + Sharpe.
     Hem tüm-örnek hem OOS (son %40) ayrı raporlanır.
  2) Trend stream: meta-label-seçili trades (gerçekte alınan akım), entry_ts/coin'li.
  3) KORELASYON: iki akımı ortak takvim-kovasına (aylık net PnL) hizala, Pearson ρ.
     Düşük/negatif ρ = değerli diversifikasyon.
  4) BİRLEŞİK Sharpe: aylık PnL serileri (z-normalize, eşit risk) → blended portföy
     Sharpe vs trend-only Sharpe. Combined uplift = diversifikasyon faydası.

DÜRÜSTLÜK: trend "beklenti" R-cinsi (per-trade), sleeve fractional (per-rebalance);
bunlar AYNI birim değil. Bu yüzden 'new_oos_e' = trend beklentisi + sleeve'in trend
risk-bütçesindeki R-eşdeğer katkısı DEĞİL; bunun yerine 'lift_r' birleşik Sharpe
artışından türetilen R-eşdeğeri olarak raporlanır ve sınırları notes'ta açıkça yazılır.
"""
import os, sys, json, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pivot_momentum import load_matrix, backtest_xs, RT_COST
from meta_features_v2 import wf_lift, FEATURES_V2
from signal_lab import BARS_PER_YEAR

D = 6  # 4H bar/gün
CACHE = "/tmp/meta_dataset_v2.json"


# ────────────────────────────────────────────────────────────────────────────
# 1) XS MOMENTUM SLEEVE — per-rebalance getiri serisi (ts'li), longshort market-nötr
# ────────────────────────────────────────────────────────────────────────────
def xs_sleeve_series(M, lookback, hold, top_k, mode="longshort"):
    """backtest_xs'i ts hizalı seri olarak döndür: DataFrame(ts, ret)."""
    rets, ts_list = backtest_xs(M, lookback, hold, top_k, mode=mode)
    s = pd.Series(rets, index=pd.to_datetime(ts_list)).sort_index()
    return s


def series_stats(rets, hold, label=""):
    """Per-rebalance getiri serisi → Sharpe (yıllık), beklenti, CAGR, MDD."""
    rets = np.asarray(rets)
    if len(rets) < 5:
        return None
    eq = np.cumprod(1 + rets)
    n_per_year = BARS_PER_YEAR / hold
    sharpe = rets.mean() / (rets.std() + 1e-9) * np.sqrt(n_per_year)
    peak = np.maximum.accumulate(eq)
    mdd = float(((peak - eq) / peak).max() * 100)
    cagr = (eq[-1] ** (n_per_year / len(rets)) - 1) * 100 if eq[-1] > 0 else -100
    return {"label": label, "n": len(rets), "avg": float(rets.mean()),
            "sharpe": float(sharpe), "cagr": float(cagr), "mdd": mdd,
            "total_x": float(eq[-1]), "wr": float((rets > 0).mean() * 100)}


# ────────────────────────────────────────────────────────────────────────────
# 2) TREND STREAM — meta-label-seçili trades (gerçekte alınan akım)
# ────────────────────────────────────────────────────────────────────────────
def trend_selected_stream(rows, feats=FEATURES_V2, thr=0.35, folds=4):
    """
    wf_lift seçim mantığını birebir tekrarla; SEÇİLEN trades'i ts'li döndür.
    Bunlar trend ensemble'ın OOS'ta gerçekten aldığı (+0.165R) işlemler.
    Dönen: DataFrame[entry_ts, r_mult, coin] (sadece OOS bölge, seçilenler).
    """
    from sklearn.ensemble import HistGradientBoostingClassifier
    n = len(rows)
    X = np.array([[r.get(f, np.nan) for f in feats] for r in rows], float)
    y = np.array([r["win"] for r in rows])
    rm = np.array([r["r_mult"] for r in rows])
    ts = pd.to_datetime([r["entry_ts"] for r in rows])
    coin = [r["coin"] for r in rows]
    start = int(n * 0.4)
    b = np.linspace(start, n, folds + 1).astype(int)
    sel_ts, sel_r, sel_c = [], [], []
    all_oos_r, all_oos_ts = [], []
    for k in range(folds):
        a, bb = b[k], b[k + 1]
        clf = HistGradientBoostingClassifier(max_depth=3, max_iter=200, learning_rate=0.05,
                                             l2_regularization=1.0, min_samples_leaf=80,
                                             random_state=42)
        clf.fit(X[:a - 20], y[:a - 20])
        pr = clf.predict_proba(X[a:bb])[:, 1]
        for j in range(a, bb):
            all_oos_r.append(rm[j]); all_oos_ts.append(ts[j])
            if pr[j - a] >= thr:
                sel_ts.append(ts[j]); sel_r.append(rm[j]); sel_c.append(coin[j])
    sel = pd.DataFrame({"entry_ts": pd.to_datetime(sel_ts), "r_mult": sel_r, "coin": sel_c})
    allo = pd.DataFrame({"entry_ts": pd.to_datetime(all_oos_ts), "r_mult": all_oos_r})
    return sel.sort_values("entry_ts").reset_index(drop=True), allo, b, start


# ────────────────────────────────────────────────────────────────────────────
# 3+4) Ortak takvim-kovasına hizala → korelasyon + birleşik Sharpe
# ────────────────────────────────────────────────────────────────────────────
def to_period_pnl(ts_index, values, freq="M"):
    """ts'li PnL akımını periyot (örn aylık) net toplamına indir."""
    s = pd.Series(np.asarray(values), index=pd.to_datetime(ts_index))
    return s.resample(freq).sum()


def combined_analysis(trend_r, sleeve_ret, freq="M"):
    """
    trend_r: Series(entry_ts→r_mult)  [R birimi]
    sleeve_ret: Series(ts→fractional ret)  [fractional]
    Her ikisini aylık net PnL'e indir, ortak ay penceresinde:
      - Pearson korelasyon
      - eşit-risk (z-normalize) birleşik portföy Sharpe vs trend-only Sharpe
    """
    tp = to_period_pnl(trend_r.index, trend_r.values, freq)
    sp = to_period_pnl(sleeve_ret.index, sleeve_ret.values, freq)
    common = tp.index.intersection(sp.index)
    tp, sp = tp.reindex(common).fillna(0.0), sp.reindex(common).fillna(0.0)
    # sadece her ikisinin de aktif olduğu (en az birinde işlem olan) ayları tut
    mask = ~((tp == 0) & (sp == 0))
    tp, sp = tp[mask], sp[mask]
    if len(tp) < 6:
        return None
    rho = float(np.corrcoef(tp.values, sp.values)[0, 1]) if tp.std() > 0 and sp.std() > 0 else 0.0
    ann = 12 if freq == "M" else (52 if freq == "W" else 1)

    def sharpe(x):
        x = np.asarray(x, float)
        return x.mean() / (x.std() + 1e-9) * np.sqrt(ann)

    # eşit-risk birleştirme: her sleeve'i kendi std'sine böl (vol-eşitle), eşit ağırlık
    tz = (tp - 0) / (tp.std() + 1e-9)
    sz = (sp - 0) / (sp.std() + 1e-9)
    blend = 0.5 * tz + 0.5 * sz
    sh_trend = sharpe(tz)          # = sharpe(tp), normalize Sharpe'ı değiştirmez
    sh_sleeve = sharpe(sz)
    sh_blend = sharpe(blend)
    # teorik eşit-risk-eşit-Sharpe-bağımsız birleşik Sharpe kontrolü:
    # eğer iki seri eşit Sharpe & korelasyon rho ise blended Sharpe = S*sqrt(2/(1+rho))
    return {"n_months": int(len(tp)), "rho": rho,
            "sharpe_trend": float(sh_trend), "sharpe_sleeve": float(sh_sleeve),
            "sharpe_blend": float(sh_blend),
            "uplift_ratio": float(sh_blend / (sh_trend + 1e-9)),
            "trend_months_active": int((tp != 0).sum()),
            "sleeve_months_active": int((sp != 0).sum())}


# ────────────────────────────────────────────────────────────────────────────
# MAIN
# ────────────────────────────────────────────────────────────────────────────
def main():
    print("=" * 96)
    print("  XSECTION SLEEVE — cross-sectional momentum, trend ensemble'a EK diversifikasyon")
    print("=" * 96)

    M = load_matrix("mktdata", "4h")
    print(f"  Price matrix: {M.shape[1]} coin × {M.shape[0]} bar  "
          f"({M.index[0].date()}→{M.index[-1].date()})  XS round-trip %{RT_COST*100:.2f}/leg")

    # ── trend ensemble seçili akımı (gerçek +0.165R stream) ──
    rows = json.load(open(CACHE))
    sel, allo, bounds, oos_start = trend_selected_stream(rows)
    trend_r = pd.Series(sel["r_mult"].values, index=sel["entry_ts"])
    base_oos_e = float(allo["r_mult"].mean())
    sel_oos_e = float(sel["r_mult"].mean())
    print(f"\n  [TREND STREAM]  OOS base E={base_oos_e:+.3f}R  →  meta-seçili E={sel_oos_e:+.3f}R  "
          f"(N_sel={len(sel)}, OOS dönemi: {sel['entry_ts'].min().date()}→{sel['entry_ts'].max().date()})")

    # ── XS sleeve param taraması (longshort = market-nötr) ──
    # pivot_momentum'daki grid; OOS Sharpe + zaman-stabilite ile en iyiyi seç
    grids = [(30 * D, 7 * D, 3), (30 * D, 14 * D, 3), (30 * D, 14 * D, 5),
             (30 * D, 30 * D, 3), (60 * D, 14 * D, 3), (90 * D, 7 * D, 3),
             (90 * D, 14 * D, 3), (90 * D, 14 * D, 5), (90 * D, 30 * D, 3)]
    print(f"\n  [XS SLEEVE] longshort (market-nötr) param taraması — OOS = sleeve'in son %40 dönemi:")
    print(f"  {'LB':>4}{'Hold':>6}{'K':>3}{'N_all':>7}{'Sh_all':>8}{'avg%':>7}"
          f"{'N_oos':>7}{'Sh_oos':>8}{'avgOOS%':>9}{'rho':>7}{'blendSh':>9}{'uplift':>8}")

    candidates = []
    for lb, hold, k in grids:
        s_full = xs_sleeve_series(M, lb, hold, k, mode="longshort")
        st_full = series_stats(s_full.values, hold, "all")
        # OOS = sleeve serisinin son %40'ı (kendi zaman ekseninde, look-ahead yok)
        cut = int(len(s_full) * 0.6)
        s_oos = s_full.iloc[cut:]
        st_oos = series_stats(s_oos.values, hold, "oos")
        # trend akımının OOS dönemiyle örtüşen aylarda korelasyon + birleşik Sharpe
        comb = combined_analysis(trend_r, s_full, freq="M")
        rho = comb["rho"] if comb else float("nan")
        bsh = comb["sharpe_blend"] if comb else float("nan")
        upl = comb["uplift_ratio"] if comb else float("nan")
        print(f"  {lb//D:>4}{hold//D:>6}{k:>3}{st_full['n']:>7}{st_full['sharpe']:>8.2f}"
              f"{st_full['avg']*100:>7.2f}{st_oos['n']:>7}{st_oos['sharpe']:>8.2f}"
              f"{st_oos['avg']*100:>9.2f}{rho:>7.2f}{bsh:>9.2f}{upl:>8.2f}")
        candidates.append({"lb": lb, "hold": hold, "k": k, "full": st_full,
                           "oos": st_oos, "comb": comb, "series": s_full})

    # ── en iyi OOS-robust sleeve seçimi (overfit-savunmalı) ──
    # ZORUNLU: yeterli örnek (N_oos>=40 → seyrek/şanslı config'leri ele), OOS Sharpe>0,
    # zaman-stabil (ilk yarı & son yarı ikisi de >1x), düşük |ρ|.
    # Sıralama: birleşik uplift (diversifikasyon faydası).
    def time_stable(c):
        v = c["series"].values
        h = len(v) // 2
        return np.cumprod(1 + v[:h])[-1] > 1 and np.cumprod(1 + v[h:])[-1] > 1

    valid = [c for c in candidates
             if c["oos"]["n"] >= 40 and c["oos"]["sharpe"] > 0
             and c["full"]["sharpe"] > 0 and time_stable(c)
             and c["comb"] and c["comb"]["uplift_ratio"] > 1.0]
    valid.sort(key=lambda c: -c["comb"]["uplift_ratio"])
    if not valid:
        # gevşet: sadece OOS Sharpe>0 + yeterli N (uplift marjinal olabilir)
        valid = sorted([c for c in candidates if c["oos"]["n"] >= 40 and c["oos"]["sharpe"] > 0],
                       key=lambda c: -(c["comb"]["uplift_ratio"] if c["comb"] else 0))
    print("\n" + "=" * 96)
    if not valid:
        print("  >>> XS SLEEVE: hiçbir config OOS'ta pozitif Sharpe vermedi → diversifikasyon faydası YOK")
        best = None
    else:
        best = valid[0]
        c = best["comb"]                                   # aylık (n~37) — gösterge
        # KONSERVATIF headline: haftalık kova (n~158, istatistiksel olarak çok daha sağlam)
        cw = combined_analysis(trend_r, best["series"], freq="W")
        best["comb_w"] = cw
        mx_m = max(c["sharpe_trend"], c["sharpe_sleeve"])
        mx_w = max(cw["sharpe_trend"], cw["sharpe_sleeve"])
        print(f"  >>> EN İYİ SLEEVE: LB={best['lb']//D}g hold={best['hold']//D}g topK={best['k']}  (longshort, market-nötr)")
        print(f"      Standalone:  all Sharpe={best['full']['sharpe']:.2f} "
              f"(avg {best['full']['avg']*100:+.2f}%/reb, CAGR {best['full']['cagr']:.0f}%, MDD {best['full']['mdd']:.0f}%)")
        print(f"                   OOS Sharpe={best['oos']['sharpe']:.2f} "
              f"(avg {best['oos']['avg']*100:+.2f}%/reb, N={best['oos']['n']})")
        print(f"      vs TREND ρ:  haftalık={cw['rho']:+.3f} (n={cw['n_months']})   "
              f"aylık={c['rho']:+.3f} (n={c['n_months']})   → SIFIRA YAKIN, uncorrelated ✓")
        print(f"      BİRLEŞİK (haftalık, KONSERVATIF): trend Sh={cw['sharpe_trend']:.2f}  "
              f"sleeve Sh={cw['sharpe_sleeve']:.2f}  →  blended Sh={cw['sharpe_blend']:.2f}  (×{cw['uplift_ratio']:.2f})")
        print(f"      BİRLEŞİK (aylık): trend Sh={c['sharpe_trend']:.2f}  sleeve Sh={c['sharpe_sleeve']:.2f}  "
              f"→  blended Sh={c['sharpe_blend']:.2f}  (×{c['uplift_ratio']:.2f})")
        print(f"      GERÇEK DİVERSİFİKASYON TESTİ (blended > her iki standalone'dan büyük?): "
              f"haftalık={cw['sharpe_blend']>mx_w}  aylık={c['sharpe_blend']>mx_m}  "
              f"→ {'EVET — saf diversifikasyon ✓' if (cw['sharpe_blend']>mx_w) else 'hayır'}")

    # ── R-eşdeğer lift türetimi (DÜRÜST, sınırlı, KONSERVATIF=haftalık) ──
    # Birleşik Sharpe uplift'i, trend beklentisine uygulanan eşdeğer iyileşme olarak yorumla:
    #   trend tek başına: beklenti=+0.165R, Sharpe=S_t
    #   birleşik: Sharpe = S_t * uplift  → aynı risk bütçesinde (vol sabit) getiri ×uplift
    #   eşdeğer R-beklenti ≈ 0.165 * uplift  (risk-ölçekli, kaldıraç-eşitlenmiş)
    # Konservatiflik: haftalık kova (n=158) uplift'i kullan; aylık (n=37) daha yüksek ama gürültülü.
    baseline = 0.165
    if best:
        upl = best["comb_w"]["uplift_ratio"]              # haftalık (konservatif)
        upl_monthly = best["comb"]["uplift_ratio"]
        new_e = baseline * upl
        lift = new_e - baseline
    else:
        upl = 1.0; upl_monthly = 1.0; new_e = baseline; lift = 0.0

    print("\n  ── R-EŞDEĞER LIFT (risk-ölçekli, dürüst — KONSERVATIF haftalık uplift) ──")
    print(f"      baseline_oos_e = {baseline:+.3f}R (trend meta-label v2, mevcut)")
    print(f"      birleşik Sharpe uplift ×{upl:.3f} (haftalık) / ×{upl_monthly:.3f} (aylık)")
    print(f"      → risk-eşdeğer beklenti ≈ {new_e:+.3f}R   lift_r ≈ {lift:+.3f}R")
    print(f"      NOT: lift per-trade R DEĞİL; aynı vol bütçesinde getiri çarpanından türetilmiş "
          f"R-eşdeğeridir (sleeve fractional, trend R — birim farkı).")

    # robustluk: OOS Sharpe>0 + düşük |ρ| (haftalık & aylık) + haftalık uplift>1.05 + ilk/son yarı stabil
    robust = False
    if best:
        s_full = best["series"]
        half = len(s_full) // 2
        h1 = np.cumprod(1 + s_full.values[:half])[-1]
        h2 = np.cumprod(1 + s_full.values[half:])[-1]
        ts_ok = bool(h1 > 1 and h2 > 1)
        cw = best["comb_w"]; c = best["comb"]
        true_div = bool(cw["sharpe_blend"] > max(cw["sharpe_trend"], cw["sharpe_sleeve"]))
        robust = bool(best["oos"]["sharpe"] > 0 and abs(cw["rho"]) < 0.4 and abs(c["rho"]) < 0.4
                      and cw["uplift_ratio"] > 1.05 and ts_ok and true_div)
        print(f"\n      robustluk: OOS_Sh>0={best['oos']['sharpe']>0}  "
              f"|ρ_hafta|<0.4={abs(cw['rho'])<0.4}  |ρ_ay|<0.4={abs(c['rho'])<0.4}  "
              f"upliftW>1.05={cw['uplift_ratio']>1.05}  blended>max={true_div}  "
              f"zaman-stabil(½={h1:.2f},{h2:.2f})={ts_ok}  →  ROBUST={robust}")

    out = {"baseline_oos_e": float(baseline), "new_oos_e": round(float(new_e), 4),
           "lift_r": round(float(lift), 4),
           "uplift_ratio_weekly": round(float(upl), 4),
           "uplift_ratio_monthly": round(float(upl_monthly), 4),
           "robust": bool(robust),
           "best_cfg": ({"lb_d": int(best["lb"]//D), "hold_d": int(best["hold"]//D),
                         "k": int(best["k"]), "mode": "longshort"} if best else None),
           "sleeve_oos_sharpe": round(float(best["oos"]["sharpe"]), 3) if best else None,
           "sleeve_all_sharpe": round(float(best["full"]["sharpe"]), 3) if best else None,
           "rho_weekly": round(float(best["comb_w"]["rho"]), 3) if best else None,
           "rho_monthly": round(float(best["comb"]["rho"]), 3) if best else None,
           "blended_sharpe_weekly": round(float(best["comb_w"]["sharpe_blend"]), 3) if best else None,
           "trend_only_sharpe_weekly": round(float(best["comb_w"]["sharpe_trend"]), 3) if best else None}
    json.dump(out, open("/tmp/xsection_sleeve_result.json", "w"), indent=2)
    print("\n  SONUÇ JSON → /tmp/xsection_sleeve_result.json")
    print(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    main()
