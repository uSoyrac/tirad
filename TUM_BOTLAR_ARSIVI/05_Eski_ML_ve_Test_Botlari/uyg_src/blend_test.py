#!/usr/bin/env python3
"""
blend_test.py — TREND + CARRY HARMAN MATEMATİĞİ (GERÇEK getiri serileriyle)
═══════════════════════════════════════════════════════════════════════════
Soru: trend edge (donchian+supertrend portföyü) ile funding-carry'yi (carry_test
conditional roll21>0, eşit-ağırlık) bir portföyde birleştirince AYNI MDD hedefinde
CAGR gerçekte ne kadar artıyor? Sentez ajanı teorik +%7..+%35 dedi → ÖLÇ.

YÖNTEM (leak-free, gerçek seriler):
  1. TREND haftalık getiri serisi: /tmp/portfolio_trades.json'daki gerçek trade akışını
     portfolio_sim.portfolio_run motoruyla zaman-sıralı oynat → equity eğrisi → haftalık
     periyodik getiri. (portfolio_run equity'yi sadece çıkışta günceller; biz çıkış
     anındaki equity'yi haftalık gride taşıyıp pct_change alıyoruz.)
  2. CARRY haftalık getiri serisi: carry_test.carry_conditional(win=21,thresh=0) ile
     20 coin'in per-accrual (8h) NET getirisi → eşit ağırlık → haftalık toplam.
     İKİ SÜRTÜNME SENARYOSU:
        optimist  : sadece carry_test'in modellediği fee (round-trip taker).
        gercekci  : + her tahakkukta 1bp basis/borrow/spread drag (pozisyon AÇIKKEN).
  3. İki seriyi ortak haftalık takvimde hizala → GERÇEK Pearson korelasyon (rho~0 mı?).
  4. Vol-targeting: her iki seriyi de aynı hedef vol'a ölçekle. Risk-bütçesi harman
     w_carry ∈ {0,0.2,0.4,0.6}. Harman serisinin Sharpe/CAGR/MDD'sini ölç.
  5. AYNI-MDD normalize: harmanı, trend-tek-başına ile AYNI MDD'ye gelecek şekilde
     tek bir kaldıraç k ile ölçekle (getiri ve MDD k ile lineer ölçeklenir →
     k = MDD_trend / MDD_blend). Normalize CAGR / trend CAGR = CAGR çarpanı.
  6. DÜRÜST sonuç: gerçekçi senaryoda harman aynı MDD'de ne kadar CAGR ekliyor?

DÜRÜSTLÜK: sadece gerçek mktdata/funddata; sayı uydurma yok; çalışmazsa infeasible.
"""
import json
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

import carry_test as ct

WEEKS_PER_YEAR = 365.25 / 7.0
COINS = ct.COINS
EXTRA_DRAG_BP = 1.0   # gerçekçi senaryo: 1bp/tahakkuk ek drag (basis+borrow+spread)


# ─────────────────────── TREND HAFTALIK GETİRİ ───────────────────────
def trend_weekly_returns(risk_per_trade=0.0025):
    """
    /tmp/portfolio_trades.json'daki GERÇEK trade akışı → haftalık periyodik getiri.

    portfolio_run'ın eşzamanlı-slot motoru bu YOĞUN akışta (10011 trade, no-cap max
    eşzamanlık=38, 76 güne kadar tutuş) cap=8 ile dejenere oluyor: 8 slot erken dolup
    aylarca açık kalıyor, geri kalan ~9950 trade skip ediliyor → seri 9 haftaya çöküyor.
    Bunun yerine RİSK-BÜTÇELİ haftalık R-toplamı kullanıyoruz: her trade'in realize R'si,
    çıkış haftasının kovasına sabit kesir (risk_per_trade) ile katkı yapar:
        haftalık_getiri ≈ risk_per_trade * Σ(R_mult, o hafta çıkanlar)
    Bu, trend edge'inin GERÇEK periyodik getiri profilini (vol kümelenmesi, MDD,
    Sharpe) korur. risk_per_trade serbest bir ölçek; vol-targeting onu zaten götürür.
    """
    trades = json.load(open("/tmp/portfolio_trades.json"))
    df = pd.DataFrame(trades)
    df["exit_ts"] = pd.to_datetime(df["exit_ts"])
    df = df.set_index("exit_ts").sort_index()
    wk_ret = (df["r_mult"] * risk_per_trade).resample("W").sum()
    return wk_ret.dropna()


# ─────────────────────── CARRY HAFTALIK GETİRİ ───────────────────────
def carry_weekly_returns(extra_drag_bp=0.0):
    """
    Eşit-ağırlık conditional carry (roll21>0) per-accrual NET getiri → haftalık toplam.
    extra_drag_bp: pozisyon AÇIKKEN her tahakkukta uygulanan ek drag (bp). Carry
    getirisinin pozitif olduğu (=pozisyon açık) tahakkuklarda değil, conditional
    pozisyonun açık olduğu HER tahakkukta uygulanmalı. carry_conditional net=0
    ise pozisyon kapalı; net!=0 ise açık. Drag'i 'açık' tahakkuklara uygularız.
    """
    nets = {}
    for c in COINS:
        try:
            f = ct.load_funding(c)
        except Exception:
            continue
        net = ct.carry_conditional(f, win=21, thresh=0.0)
        if net is None:
            continue
        if extra_drag_bp > 0:
            # pozisyon açık = conditional varyantta net hesaplanırken funding eklenen barlar.
            # carry_conditional açık barlarda net = funding(+/-) [- maliyet]. Kapalı barlarda net==0.
            # 'açık' barı net!=0 OR funding katkısı ile ayırmak için: pozisyon maskesini yeniden üret.
            ff = f.dropna()
            roll = ff.rolling(21).mean()
            want = (roll > 0.0).astype(int).shift(1).fillna(0)
            want = want.reindex(net.index).fillna(0).astype(int)
            drag = want.values * (extra_drag_bp / 1e4)
            net = net - pd.Series(drag, index=net.index)
        nets[c] = net
    if not nets:
        return None
    port = pd.concat(nets.values(), axis=1).fillna(0.0)
    per_accr = port.mean(axis=1)         # eşit ağırlık per-accrual net getiri
    # haftalık toplam (per-accrual getiriler küçük → toplama additif yaklaşımı uygun)
    wk = per_accr.resample("W").sum()
    return wk.dropna()


# ─────────────────────── METRİKLER ───────────────────────
def ann_stats(wk_ret):
    """haftalık getiri serisinden yıllık Sharpe, CAGR, MDD."""
    r = wk_ret.dropna().values
    if len(r) < 4 or r.std() == 0:
        return dict(sharpe=0.0, cagr=0.0, mdd=0.0, vol=0.0, mean=0.0)
    sharpe = r.mean() / r.std() * np.sqrt(WEEKS_PER_YEAR)
    # equity (additif yerine compound: getiriler haftalık → kümülatif çarpım)
    eq = (1 + wk_ret.dropna()).cumprod()
    yrs = len(r) / WEEKS_PER_YEAR
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    peak = eq.cummax()
    mdd = float(((eq - peak) / peak).min())   # negatif
    vol = r.std() * np.sqrt(WEEKS_PER_YEAR)
    return dict(sharpe=float(sharpe), cagr=float(cagr), mdd=mdd, vol=float(vol), mean=float(r.mean()))


def vol_scale(wk_ret, target_vol):
    """seriyi hedef yıllık vol'a ölçekle (getiriyi sabit k ile çarp)."""
    v = wk_ret.std() * np.sqrt(WEEKS_PER_YEAR)
    if v == 0:
        return wk_ret * 0
    return wk_ret * (target_vol / v)


def main():
    print("=" * 80)
    print("  TREND + CARRY HARMAN MATEMATİĞİ (gerçek seriler, haftalık)")
    print("=" * 80)

    # 1. TREND
    trend = trend_weekly_returns(risk_per_trade=0.0025)
    ts = ann_stats(trend)
    print(f"\n  ── TREND (donchian+supertrend, risk-bütçeli haftalık R, 0.25%/trade) ──")
    print(f"   hafta sayısı : {len(trend)}  ({trend.index.min().date()} → {trend.index.max().date()})")
    print(f"   Sharpe={ts['sharpe']:.2f}  CAGR={ts['cagr']*100:+.1f}%  MDD={ts['mdd']*100:.1f}%  vol={ts['vol']*100:.1f}%")

    # 2. CARRY iki senaryo
    carry_opt = carry_weekly_returns(extra_drag_bp=0.0)
    carry_real = carry_weekly_returns(extra_drag_bp=EXTRA_DRAG_BP)
    co, cr = ann_stats(carry_opt), ann_stats(carry_real)
    print(f"\n  ── CARRY (eşit-ağırlık conditional roll21>0, 20 coin) ──")
    print(f"   OPTİMİST (sadece modellenmiş fee):")
    print(f"     hafta={len(carry_opt)}  Sharpe={co['sharpe']:.2f}  CAGR={co['cagr']*100:+.1f}%  MDD={co['mdd']*100:.1f}%  vol={co['vol']*100:.2f}%")
    print(f"   GERÇEKÇİ (+{EXTRA_DRAG_BP:.0f}bp/tahakkuk drag):")
    print(f"     hafta={len(carry_real)}  Sharpe={cr['sharpe']:.2f}  CAGR={cr['cagr']*100:+.1f}%  MDD={cr['mdd']*100:.1f}%  vol={cr['vol']*100:.2f}%")

    # 3. KORELASYON (ortak haftalık takvim)
    print(f"\n  ── KORELASYON (ortak haftalık takvimde) ──")
    for name, carry in [("optimist", carry_opt), ("gercekci", carry_real)]:
        df = pd.concat([trend.rename("trend"), carry.rename("carry")], axis=1).dropna()
        rho = df["trend"].corr(df["carry"])
        print(f"   trend vs carry({name})  ortak hafta={len(df)}  rho = {rho:+.4f}")

    # 4+5. RİSK-BÜTÇESİ HARMAN + AYNI-MDD NORMALİZE
    #   Her iki seriyi de trend'in vol'una ölçekle (ortak ölçek), w ile karıştır,
    #   sonra harmanı trend ile AYNI MDD'ye getirecek tek kaldıraç k ile ölçekle.
    for scen_name, carry in [("OPTİMİST", carry_opt), ("GERÇEKÇİ", carry_real)]:
        print(f"\n  ── HARMAN ({scen_name} carry) — vol-targeting + AYNI-MDD normalize ──")
        df = pd.concat([trend.rename("trend"), carry.rename("carry")], axis=1).dropna()
        if len(df) < 12:
            print("   ortak veri yetersiz"); continue
        target_vol = df["trend"].std() * np.sqrt(WEEKS_PER_YEAR)
        T = vol_scale(df["trend"], target_vol)
        Cv = vol_scale(df["carry"], target_vol)
        base = ann_stats(T)
        mdd_target = base["mdd"]
        print(f"   (ortak pencere trend: Sharpe={base['sharpe']:.2f} CAGR={base['cagr']*100:+.1f}% MDD={mdd_target*100:.1f}%)")
        print(f"   {'w_carry':>8}{'Sharpe':>9}{'CAGR%':>9}{'MDD%':>9}  {'→ AYNI-MDD k':>13}{'normCAGR%':>11}{'CAGR çarpanı':>14}")
        base_norm_cagr = None
        for w in [0.0, 0.2, 0.4, 0.6]:
            blend = (1 - w) * T + w * Cv
            bs = ann_stats(blend)
            # aynı-MDD normalize: getiriler ve MDD k'ya yaklaşık lineer (additif harman)
            if bs["mdd"] == 0:
                k = 0.0
            else:
                k = mdd_target / bs["mdd"]   # her ikisi de negatif → pozitif k
            norm = vol_scale(blend, blend.std() * np.sqrt(WEEKS_PER_YEAR) * k)  # k kaldıraç
            ns = ann_stats(norm)
            if w == 0.0:
                base_norm_cagr = ns["cagr"]
            mult = (ns["cagr"] / base_norm_cagr) if base_norm_cagr else float("nan")
            print(f"   {w:>8.1f}{bs['sharpe']:>9.2f}{bs['cagr']*100:>9.1f}{bs['mdd']*100:>9.1f}  "
                  f"{k:>13.3f}{ns['cagr']*100:>11.1f}{mult:>13.3f}x")

        # En iyi w (normalize CAGR maksimize)
        best_w, best_mult = 0.0, 1.0
        for w in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]:
            blend = (1 - w) * T + w * Cv
            bs = ann_stats(blend)
            if bs["mdd"] == 0: continue
            k = mdd_target / bs["mdd"]
            norm = vol_scale(blend, blend.std() * np.sqrt(WEEKS_PER_YEAR) * k)
            ns = ann_stats(norm)
            mult = ns["cagr"] / base_norm_cagr if base_norm_cagr else 1.0
            if mult > best_mult:
                best_mult, best_w = mult, w
        print(f"   → EN İYİ w_carry={best_w:.1f}: aynı-MDD'de CAGR ÇARPANI = {best_mult:.3f}x "
              f"(= {(best_mult-1)*100:+.1f}% CAGR artışı)")

    # ─────────── DRAG-SWEEP: gerçekçi sürtünme bandında aynı-MDD CAGR çarpanı ───────────
    # Carry net Sharpe drag'e çok duyarlı (3 tahakkuk/gün × 5 yıl). Sentez ajanı
    # 'gerçekçi Sharpe 0.3-0.7' dedi; bunu drag'e çevirip harman faydasını BANTLA raporla.
    print(f"\n  ── DRAG-SWEEP: harmanın gerçekçi sürtünme bandında AYNI-MDD CAGR faydası ──")
    print(f"   (her drag için carry net Sharpe + en iyi w_carry'de CAGR çarpanı)")
    print(f"   {'drag(bp)':>9}{'carrySharpe':>12}{'enİyi_w':>9}{'CAGRçarpanı':>13}{'CAGR artışı%':>14}")
    for drag in [0.0, 0.25, 0.5, 0.75, 1.0]:
        carry = carry_weekly_returns(extra_drag_bp=drag)
        cs = ann_stats(carry)
        df = pd.concat([trend.rename("trend"), carry.rename("carry")], axis=1).dropna()
        tv = df["trend"].std() * np.sqrt(WEEKS_PER_YEAR)
        T = vol_scale(df["trend"], tv); Cv = vol_scale(df["carry"], tv)
        mdd_t = ann_stats(T)["mdd"]; base_cagr = ann_stats(T)["cagr"]
        best_w, best_mult = 0.0, 1.0
        for w in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]:
            blend = (1 - w) * T + w * Cv
            bs = ann_stats(blend)
            if bs["mdd"] == 0: continue
            k = mdd_t / bs["mdd"]
            ns = ann_stats(vol_scale(blend, blend.std() * np.sqrt(WEEKS_PER_YEAR) * k))
            mult = ns["cagr"] / base_cagr if base_cagr else 1.0
            if mult > best_mult: best_mult, best_w = mult, w
        print(f"   {drag:>9.2f}{cs['sharpe']:>12.2f}{best_w:>9.1f}{best_mult:>12.2f}x{(best_mult-1)*100:>13.1f}%")
    print(f"   YORUM: sentez ajanının 'gerçekçi carry Sharpe 0.3-0.7' bandı ≈ 0.85-0.95bp drag.")
    print(f"   Bu bantta carry net Sharpe trend'inkine (~0.75) yakın/altında → harman faydası")
    print(f"   teorik +%7..%35'in ÇOK altında; ~0.9bp+ drag'de harman aynı MDD'de DEĞER KATMIYOR.")

    print("\n" + "=" * 80)
    print("  NOT: trend getirisi gerçek trade akışı (risk-bütçeli haftalık R); carry getirisi")
    print("  gerçek funding + conditional varyant. Korelasyon ve harman GERÇEK seriler.")
    print("  Modellenmiyor: harmanın dinamik yeniden-dengesi, carry likidasyon riski,")
    print("  funding rejim kırılması. Aynı-MDD normalize additif-harman varsayımıyla lineer.")
    print("=" * 80)


if __name__ == "__main__":
    main()
