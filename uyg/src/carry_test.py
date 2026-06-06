#!/usr/bin/env python3
"""
carry_test.py — HİPOTEZ A: DELTA-NÖTR FUNDING CARRY (yönsüz risk primi)

Model:
  Delta-neutral pozisyon = LONG spot + SHORT perp (eşit notional).
  Fiyat riski nötrlenir (spot +, perp - birbirini götürür).
  SHORT perp pozitif funding TOPLAR (funding>0 → longlar shortlara öder → short alır).
  Getiri kaynağı = funding akışı; maliyet = her iki legin giriş+çıkış taker fee'si.

Konvansiyon (signal_lab ile uyumlu):
  - taker fee = FEE+SLIP = 7bps/taraf. Delta-neutral kurulum = 2 leg aç (spot long + perp short)
    = 2 taraf giriş; kapatış = 2 taraf çıkış. Toplam 4 taraf = 4*0.0007 = 0.0028 notional/round-trip.
  - funding 8h'de bir tahakkuk; short perp her tahakkukta +funding (notional oranı) alır.
  - LEAK-FREE: funding bar kapanışında bilinir, koşullu giriş bir sonraki bar açılışına dayanır (shift).

Varyantlar:
  (a) always-on : pozisyon hep açık, tüm tahakkukları topla (sadece açılış+kapanış 1 kez maliyet).
  (b) conditional: rolling funding ort > eşik iken aç, altına düşünce kapat (her aç/kapa maliyet öder).

Metrikler: net yıllık getiri (notional üzerinden), Sharpe, MDD, funding-negatif dönem kaybı,
           BTC trend ile korelasyon, walk-forward OOS, per-coin pozitiflik.
DÜRÜSTLÜK: sadece gerçek funddata/ ile çalıştırılan gerçek sayılar.
"""
import os
import numpy as np
import pandas as pd

warnings_filter = None
import warnings; warnings.filterwarnings("ignore")

LEG_SIDE_COST = 0.0007          # taker per side per leg (7bps)
ROUND_TRIP_COST = LEG_SIDE_COST * 4   # spot+perp aç (2) + kapat (2) = 0.0028 notional
ACCR_PER_YEAR = 3 * 365         # 8h funding → 3/gün

COINS = ["ADA","APT","ARB","ATOM","AVAX","BNB","BTC","DOGE","DOT","ETC",
         "ETH","FIL","INJ","LINK","LTC","NEAR","OP","SOL","UNI","XRP"]


def load_funding(coin):
    f = pd.read_csv(f"funddata/{coin}_funding.csv")
    f["ts"] = pd.to_datetime(f["ts"]).dt.floor("4h")
    f = f.drop_duplicates("ts").set_index("ts").sort_index()
    return f["funding"]


def load_mkt(coin):
    df = pd.read_csv(f"mktdata/{coin}_USDT_4h.csv")
    df["ts"] = pd.to_datetime(df["ts"])
    return df.set_index("ts").sort_index()


def annualize_sharpe(per_accr_returns):
    """per-accrual (8h) net getiri serisinden yıllık Sharpe."""
    r = np.asarray(per_accr_returns, float)
    if len(r) < 2 or r.std() == 0:
        return 0.0
    return float(r.mean() / r.std() * np.sqrt(ACCR_PER_YEAR))


def max_drawdown(cum):
    cum = np.asarray(cum, float)
    peak = np.maximum.accumulate(cum)
    dd = cum - peak
    return float(dd.min())


def carry_always_on(funding):
    """
    (a) always-on: pozisyon başta açılır, sonda kapanır. Tek round-trip maliyeti.
    funding: pd.Series index=ts (8h), değer = o tahakkukta short'un aldığı funding oranı.
    Döner: per-accrual net getiri serisi (ilk accrual'a açılış maliyeti yüklenir).
    """
    f = funding.dropna()
    if len(f) < 10:
        return None
    gross = f.values.copy()            # her tahakkukta short +funding alır
    net = gross.copy()
    # tek kurulum + tek kapatış: maliyeti ilk tahakkuğa yükle (amorti edilmez, konservatif)
    net[0] -= ROUND_TRIP_COST
    return pd.Series(net, index=f.index)


def carry_conditional(funding, win=21, thresh=0.0):
    """
    (b) conditional: rolling(win) funding ortalaması > thresh iken pozisyon AÇIK.
    Sinyal shift(1) ile causal: bugünkü kapanan rolling ort → bir sonraki tahakkukta pozisyon.
    Her açılış-kapanış geçişinde ROUND_TRIP_COST öder.
    Döner: per-accrual net getiri (pozisyon kapalıyken 0).
    """
    f = funding.dropna()
    if len(f) < win + 5:
        return None
    roll = f.rolling(win).mean()
    want = (roll > thresh).astype(int)
    want = want.shift(1).fillna(0)     # causal: geçmiş bilgiyle karar, sonraki tahakkukta uygula
    pos = want.values
    fv = f.values
    net = np.zeros(len(fv))
    for i in range(len(fv)):
        if pos[i] == 1:
            net[i] += fv[i]            # short funding alır (yön fark etmez, pozitif funding'i hedefler)
            if i == 0 or pos[i-1] == 0:
                net[i] -= ROUND_TRIP_COST / 2   # açılış maliyeti (2 leg giriş)
            if i == len(fv)-1 or pos[i+1] == 0:
                net[i] -= ROUND_TRIP_COST / 2   # kapanış maliyeti (2 leg çıkış)
    return pd.Series(net, index=f.index)


def summary(net, label):
    if net is None or len(net) < 2:
        return None
    cum = net.cumsum()
    yrs = len(net) / ACCR_PER_YEAR
    total = cum.iloc[-1]
    ann = total / yrs
    sharpe = annualize_sharpe(net.values)
    mdd = max_drawdown(cum.values)
    return {"label": label, "n_accr": len(net), "years": yrs,
            "total_ret": float(total), "ann_ret": float(ann),
            "sharpe": sharpe, "mdd": mdd,
            "frac_neg_accr": float((net < 0).mean()),
            "neg_period_sum": float(net[net < 0].sum())}


def walk_forward_oos(funding, n_folds=4):
    """
    Expanding-window WF: always-on carry'nin OOS yıllık getirisini fold'lar halinde ölç.
    Carry her zaman açık olduğu için 'fit' edilecek parametre yok; ama zaman-stabiliteyi
    test bölmelerinde always-on ann_ret > 0 mi diye kontrol ederiz.
    """
    f = funding.dropna()
    if len(f) < 200:
        return []
    start = int(len(f) * 0.4)
    bounds = np.linspace(start, len(f), n_folds + 1).astype(int)
    outs = []
    for k in range(n_folds):
        seg = f.iloc[bounds[k]:bounds[k+1]]
        if len(seg) < 10:
            continue
        net = seg.copy()
        net.iloc[0] -= ROUND_TRIP_COST
        yrs = len(net) / ACCR_PER_YEAR
        outs.append(float(net.sum() / yrs))
    return outs


def btc_trend_4h(funding_index):
    """BTC 4H getiri/trend serisini funding (8h) gridine hizala → korelasyon için."""
    btc = load_mkt("BTC")
    ret4h = btc["close"].pct_change()
    # funding 8h gridi 4H gridin alt-kümesi → reindex ile hizala
    aligned = ret4h.reindex(funding_index).fillna(0.0)
    # 8h penceredeki 2 bar getirisini topla (yaklaşık): bir önceki 4h dahil
    return aligned


def main():
    print("=" * 78)
    print("  HİPOTEZ A — DELTA-NÖTR FUNDING CARRY (gerçek funddata/, 20 coin)")
    print(f"  maliyet: leg/side={LEG_SIDE_COST}  round-trip(spot+perp aç+kapat)={ROUND_TRIP_COST}")
    print("=" * 78)

    rows_a, rows_b = [], []
    all_net_a = {}
    wf_pos = 0; wf_tot = 0

    for c in COINS:
        try:
            fund = load_funding(c)
        except Exception as e:
            print(f"  {c}: funding yüklenemedi ({e})")
            continue
        net_a = carry_always_on(fund)
        net_b = carry_conditional(fund, win=21, thresh=0.0)
        sa = summary(net_a, f"{c}-alwaysON")
        sb = summary(net_b, f"{c}-cond")
        if sa: rows_a.append(sa); all_net_a[c] = net_a
        if sb: rows_b.append(sb)
        # WF
        wf = walk_forward_oos(fund)
        if wf:
            wf_pos += sum(1 for x in wf if x > 0); wf_tot += len(wf)

    def report_variant(rows, name):
        if not rows:
            print(f"\n  [{name}] veri yok"); return
        df = pd.DataFrame(rows)
        pos = (df["ann_ret"] > 0).sum()
        print(f"\n  ── {name} ── ({len(df)} coin)")
        print(f"   medyan yıllık net getiri : {df['ann_ret'].median():+.4f}  "
              f"(={df['ann_ret'].median()*100:+.2f}%/yr notional)")
        print(f"   ortalama yıllık net      : {df['ann_ret'].mean():+.4f}")
        print(f"   medyan Sharpe            : {df['sharpe'].median():.2f}")
        print(f"   medyan MDD               : {df['mdd'].median():+.4f}  (kümülatif notional)")
        print(f"   per-coin pozitif         : {pos}/{len(df)}  ({pos/len(df)*100:.0f}%)")
        print(f"   medyan negatif-tahakkuk payı : {df['frac_neg_accr'].median()*100:.1f}%")
        print(f"   en kötü 3 coin (ann_ret):")
        for _, r in df.nsmallest(3, "ann_ret").iterrows():
            print(f"      {r['label']:16s} {r['ann_ret']:+.4f}/yr  Sharpe={r['sharpe']:.2f}  MDD={r['mdd']:+.4f}")
        print(f"   en iyi 3 coin:")
        for _, r in df.nlargest(3, "ann_ret").iterrows():
            print(f"      {r['label']:16s} {r['ann_ret']:+.4f}/yr  Sharpe={r['sharpe']:.2f}")
        return df

    dfa = report_variant(rows_a, "VARYANT (a) ALWAYS-ON")
    dfb = report_variant(rows_b, "VARYANT (b) CONDITIONAL (roll21>0)")

    # ── WALK-FORWARD OOS ──
    print(f"\n  ── WALK-FORWARD OOS (always-on, expanding 4-fold, %40+ test) ──")
    if wf_tot:
        print(f"   pozitif OOS fold : {wf_pos}/{wf_tot}  ({wf_pos/wf_tot*100:.0f}%)")

    # ── BTC TREND KORELASYONU (kritik: yönsüz mü?) ──
    print(f"\n  ── BTC TREND KORELASYONU (always-on carry getiri akışı vs BTC 4H getirisi) ──")
    btc_net = all_net_a.get("BTC")
    if btc_net is not None:
        btc_ret = btc_trend_4h(btc_net.index)
        common = pd.concat([btc_net.rename("carry"), btc_ret.rename("px")], axis=1).dropna()
        corr_btc = common["carry"].corr(common["px"])
        print(f"   BTC carry akışı vs BTC fiyat getirisi  corr = {corr_btc:+.4f}")
        # tüm coinlerin carry akışı havuzu vs BTC getirisi
        pool = []
        for c, net in all_net_a.items():
            br = btc_trend_4h(net.index)
            cc = pd.concat([net.rename("carry"), br.rename("px")], axis=1).dropna()
            if len(cc) > 50:
                pool.append(cc["carry"].corr(cc["px"]))
        pool = [x for x in pool if not np.isnan(x)]
        if pool:
            print(f"   tüm coinler carry vs BTC getiri  medyan corr = {np.median(pool):+.4f}  "
                  f"(|corr|<0.1 → yönsüz)")
            print(f"   coin sayısı |corr|<0.10 : {sum(1 for x in pool if abs(x)<0.10)}/{len(pool)}")

    # ── KÜMÜLATIF PORTFÖY (eşit ağırlık always-on, tüm coinler) ──
    print(f"\n  ── EŞİT-AĞIRLIK PORTFÖY (always-on, tüm coinler ortak takvimde) ──")
    if all_net_a:
        port = pd.concat(all_net_a.values(), axis=1).fillna(0.0)
        port_net = port.mean(axis=1)          # eşit ağırlık günlük net
        sp = summary(port_net, "PORTFOY")
        if sp:
            print(f"   yıllık net getiri : {sp['ann_ret']:+.4f}  (={sp['ann_ret']*100:+.2f}%/yr)")
            print(f"   Sharpe            : {sp['sharpe']:.2f}")
            print(f"   MDD               : {sp['mdd']:+.4f}")
            print(f"   negatif tahakkuk payı : {sp['frac_neg_accr']*100:.1f}%")

    print("\n" + "=" * 78)
    print("  NOT: getiri 'notional oranı' cinsinden (kaldıraçsız, 1x spot + 1x perp).")
    print("  Modellenmiyor: basis convergence kayması, likidasyon (perp marjin), borrow/")
    print("  rollover ücreti, gerçek spread/derinlik. Bunlar net getiriyi AŞAĞI çeker.")
    print("=" * 78)


if __name__ == "__main__":
    main()
