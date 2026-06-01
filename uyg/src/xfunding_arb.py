#!/usr/bin/env python3
"""
xfunding_arb.py — ÇAPRAZ-BORSA FUNDING-ARB (perp vs perp, fiyat-nötr)

Ekonomi:
  Tek-borsa carry (carry_test.py) funding rejimine maruz: tüm borsalarda funding
  negatife dönerse short-perp carry kaybeder. Çapraz-borsa arb bunun yerine
  borsalar-arası funding FARKINI yakalar:
    - Yüksek-funding borsada SHORT perp  (pozitif funding'i 'alır')
    - Düşük/negatif-funding borsada LONG perp (negatif funding'i 'alır' = öder az/alır)
  İki bacak da perp, aynı coin, eşit notional → net fiyat deltası ~0.
  Her tahakkukta net funding akışı = funding_short_leg - funding_long_leg = |spread|
  (her zaman pozitif yöne pozisyon alındığı için), eksi maliyet.

  Rejimden bağımsızlık: ikisi de negatif olsa bile FARK pozitif olabilir → carry'den
  daha robust olması beklenir. Bunu test ediyoruz.

Konvansiyon (signal_lab/carry_test uyumlu):
  - 8h funding (günde 3 tahakkuk), ACCR_PER_YEAR=3*365.
  - LEAK-FREE: hangi bacağın hangi borsa olacağı kararı KAPANMIŞ funding spread'ine
    göre, pozisyon BİR SONRAKİ tahakkukta uygulanır (shift(1)). Her zaman-on varyantında
    pozisyon yönü sürekli güncellenir; yön değiştikçe rebalance maliyeti öder.
  - taker fee = 7bps/taraf. Arb kurulumu = 2 perp bacak aç = 2 taraf; kapat = 2 taraf.
    Yön ters dönünce (which exchange short/long) her iki bacağı çevirmek gerekir → 4 taraf
    rebalance maliyeti. Konservatif: her yön değişiminde ROUND_TRIP (4*7bps).

Varyantlar:
  (a) directional always-on: her tahakkukta spread işaretine göre yön al (yüksek borsada short).
      Yön değişiminde rebalance maliyeti. Sürekli açık.
  (b) thresholded: |rolling spread| > eşik iken aç, altına düşünce kapat. Daha az işlem.

DÜRÜSTLÜK:
  - Binance(funddata) + Bybit(xfunddata) = ~5yr ortak geçmiş → ANA test.
  - OKX = sadece ~3 ay (278 bar) → yalnız kısa-pencere 3-borsa sanity, WEAK olarak işaretli.
  - Modellenmiyen maliyet: iki borsada sermaye bölünmesi (atıl marj), transfer/rebalance
    gecikmesi, perp likidasyon riski (her iki bacak marjinli), borsa-spesifik spread/derinlik,
    funding tahmin hatası. Bunlar net getiriyi AŞAĞI çeker. Sharpe yanıltıcı (oto-korelasyonlu).
"""
import os
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")

LEG_SIDE_COST = 0.0007              # 7 bps taker / side
SETUP_COST = LEG_SIDE_COST * 2      # 2 perp leg aç = 2 taraf
ROUNDTRIP_COST = LEG_SIDE_COST * 4  # aç+kapat (2+2) ya da yön ters çevir (4)
REBALANCE_COST = LEG_SIDE_COST * 4  # yön değişiminde her iki bacak çevrilir
ACCR_PER_YEAR = 3 * 365

COINS = ["ADA","APT","ARB","ATOM","AVAX","BNB","BTC","DOGE","DOT","ETC",
         "ETH","FIL","INJ","LINK","LTC","NEAR","OP","SOL","UNI","XRP"]


def _norm(s):
    s = s.copy()
    s.index = pd.to_datetime(s.index).floor("8h")
    s = s[~s.index.duplicated(keep="first")].sort_index()
    return s


def load_binance(coin):
    f = pd.read_csv(f"funddata/{coin}_funding.csv")
    f["ts"] = pd.to_datetime(f["ts"])
    return _norm(f.set_index("ts")["funding"])


def load_bybit(coin):
    f = pd.read_csv(f"xfunddata/bybit_{coin}_funding.csv")
    f["ts"] = pd.to_datetime(f["ts"])
    return _norm(f.set_index("ts")["funding"])


def load_okx(coin):
    f = pd.read_csv(f"xfunddata/okx_{coin}_funding.csv")
    f["ts"] = pd.to_datetime(f["ts"])
    return _norm(f.set_index("ts")["funding"])


def annualize_sharpe(r):
    r = np.asarray(r, float)
    if len(r) < 2 or r.std() == 0:
        return 0.0
    return float(r.mean() / r.std() * np.sqrt(ACCR_PER_YEAR))


def max_drawdown(cum):
    cum = np.asarray(cum, float)
    peak = np.maximum.accumulate(cum)
    return float((cum - peak).min())


def arb_directional(fA, fB):
    """
    (a) Always-on directional cross-exchange arb on the COMMON timeline of fA,fB.
    Spread_t = fA - fB. Decision uses CLOSED spread, applied NEXT accrual (shift(1)).
      sign=+1 → fA>fB → short A-perp(+fA) long B-perp(-fB) → collects (fA-fB)
      sign=-1 → fB>fA → short B-perp(+fB) long A-perp(-fA) → collects (fB-fA)
    Net realized per accrual = sign_{t-1} * (fA_t - fB_t)  [we collect actual diff
      with the side we committed to last bar]. Cost when sign flips (rebalance).
    Returns per-accrual net series.
    """
    common = pd.concat([fA.rename("A"), fB.rename("B")], axis=1).dropna()
    if len(common) < 30:
        return None, common
    spread = (common["A"] - common["B"])
    sign = np.sign(spread)
    sign = sign.replace(0, np.nan).ffill().fillna(1.0)
    pos = sign.shift(1).fillna(0.0)          # causal: last bar's decided side
    realized = pos.values * spread.values    # collect actual diff with committed side
    net = realized.copy()
    posv = pos.values
    for i in range(len(posv)):
        if i == 0:
            if posv[i] != 0:
                net[i] -= SETUP_COST
        else:
            if posv[i] != 0 and posv[i-1] == 0:
                net[i] -= SETUP_COST          # open
            elif posv[i] != 0 and posv[i-1] != 0 and posv[i] != posv[i-1]:
                net[i] -= REBALANCE_COST      # flip both legs
    # close at end
    if posv[-1] != 0:
        net[-1] -= SETUP_COST
    return pd.Series(net, index=common.index), common


def arb_thresholded(fA, fB, win=21, thresh=None):
    """
    (b) Trade only when |rolling-mean spread| exceeds a threshold; flat otherwise.
    Threshold auto = costs amortization heuristic if None: 2*SETUP/win per accrual
    expressed as spread magnitude. Causal shift(1) on the gate AND on the chosen side.
    """
    common = pd.concat([fA.rename("A"), fB.rename("B")], axis=1).dropna()
    if len(common) < win + 10:
        return None, common
    spread = (common["A"] - common["B"])
    roll = spread.rolling(win).mean()
    if thresh is None:
        thresh = (2 * SETUP_COST) / win      # need diff to cover round-trip over holding
    gate = (roll.abs() > thresh).astype(float)
    side = np.sign(roll).replace(0, np.nan).ffill().fillna(1.0)
    pos = (gate * side).shift(1).fillna(0.0)
    realized = pos.values * spread.values
    net = realized.copy()
    posv = pos.values
    for i in range(len(posv)):
        if posv[i] != 0:
            prev = posv[i-1] if i > 0 else 0.0
            if prev == 0:
                net[i] -= SETUP_COST          # open
            elif prev != posv[i]:
                net[i] -= REBALANCE_COST      # flip
            if i == len(posv)-1:
                net[i] -= SETUP_COST          # close at end
        else:
            prev = posv[i-1] if i > 0 else 0.0
            if prev != 0:
                net[i] -= SETUP_COST          # close
    return pd.Series(net, index=common.index), common


def summary(net):
    if net is None or len(net) < 2:
        return None
    cum = net.cumsum()
    yrs = len(net) / ACCR_PER_YEAR
    total = cum.iloc[-1]
    return {"n_accr": len(net), "years": yrs, "total_ret": float(total),
            "ann_ret": float(total / yrs), "sharpe": annualize_sharpe(net.values),
            "mdd": max_drawdown(cum.values), "frac_neg": float((net < 0).mean()),
            "neg_sum": float(net[net < 0].sum())}


def walk_forward(net, n_folds=4):
    """Time-stability: split the realized net stream into folds, ann_ret>0 in each?"""
    if net is None or len(net) < 200:
        return []
    bounds = np.linspace(0, len(net), n_folds + 1).astype(int)
    outs = []
    for k in range(n_folds):
        seg = net.iloc[bounds[k]:bounds[k+1]]
        if len(seg) < 10:
            continue
        outs.append(float(seg.sum() / (len(seg) / ACCR_PER_YEAR)))
    return outs


def load_btc_4h_aligned(index):
    df = pd.read_csv("mktdata/BTC_USDT_4h.csv")
    df["ts"] = pd.to_datetime(df["ts"])
    ret = df.set_index("ts")["close"].pct_change()
    return ret.reindex(index).fillna(0.0)


def run_pair(loaderA, loaderB, nameA, nameB, label, weak=False):
    print("\n" + "=" * 78)
    tag = "  [WEAK / kısa-pencere]" if weak else ""
    print(f"  PAIR: {nameA} vs {nameB}{tag}")
    print("=" * 78)
    rows_a, rows_b = [], []
    net_a_by_coin = {}
    spread_stats = []
    for c in COINS:
        try:
            fA = loaderA(c); fB = loaderB(c)
        except Exception as e:
            print(f"  {c}: yükleme hatası ({e})"); continue
        net_a, common = arb_directional(fA, fB)
        net_b, _ = arb_thresholded(fA, fB)
        if common is not None and len(common) > 0:
            sp = (common["A"] - common["B"])
            spread_stats.append({"coin": c, "n": len(common),
                                 "mean_abs_spread": float(sp.abs().mean()),
                                 "median_abs_spread": float(sp.abs().median())})
        sa = summary(net_a); sb = summary(net_b)
        if sa: sa["coin"] = c; rows_a.append(sa); net_a_by_coin[c] = net_a
        if sb: sb["coin"] = c; rows_b.append(sb)

    if spread_stats:
        sdf = pd.DataFrame(spread_stats)
        print(f"\n  funding SPREAD büyüklüğü (|fA-fB| per 8h tahakkuk):")
        print(f"   medyan |spread| (coinler arası medyan) : {sdf['median_abs_spread'].median():.6f}  "
              f"(={sdf['median_abs_spread'].median()*ACCR_PER_YEAR*100:.2f}%/yr brüt üst-sınır)")
        print(f"   ortak-takvim bar sayısı (medyan coin)   : {int(sdf['n'].median())}  "
              f"(≈{sdf['n'].median()/ACCR_PER_YEAR:.2f} yıl)")

    def rep(rows, name):
        if not rows:
            print(f"\n  [{name}] veri yok"); return None
        df = pd.DataFrame(rows)
        pos = (df["ann_ret"] > 0).sum()
        print(f"\n  ── {name} ── ({len(df)} coin)")
        print(f"   medyan yıllık net : {df['ann_ret'].median():+.4f}  "
              f"(={df['ann_ret'].median()*100:+.2f}%/yr notional)")
        print(f"   ortalama yıllık net: {df['ann_ret'].mean():+.4f}")
        print(f"   medyan Sharpe     : {df['sharpe'].median():.2f}  (oto-korelasyonlu, yanıltıcı)")
        print(f"   medyan MDD        : {df['mdd'].median():+.4f}")
        print(f"   per-coin pozitif  : {pos}/{len(df)}  ({pos/len(df)*100:.0f}%)")
        worst = df.nsmallest(3, "ann_ret")
        best = df.nlargest(3, "ann_ret")
        print(f"   en kötü 3: " + ", ".join(f"{r['coin']}={r['ann_ret']:+.3f}" for _, r in worst.iterrows()))
        print(f"   en iyi  3: " + ", ".join(f"{r['coin']}={r['ann_ret']:+.3f}" for _, r in best.iterrows()))
        return df

    dfa = rep(rows_a, "VARYANT (a) DIRECTIONAL always-on")
    dfb = rep(rows_b, "VARYANT (b) THRESHOLDED (roll21 |spread|>maliyet eşiği)")

    # walk-forward on directional, pooled fold positivity
    wf_pos = wf_tot = 0
    for c, net in net_a_by_coin.items():
        wf = walk_forward(net)
        wf_pos += sum(1 for x in wf if x > 0); wf_tot += len(wf)
    if wf_tot:
        print(f"\n  ── WALK-FORWARD OOS (directional, 4-fold/coin) ──")
        print(f"   pozitif OOS fold : {wf_pos}/{wf_tot}  ({wf_pos/wf_tot*100:.0f}%)")

    # equal-weight portfolio (directional)
    if net_a_by_coin:
        port = pd.concat(net_a_by_coin.values(), axis=1).fillna(0.0)
        pnet = port.mean(axis=1)
        sp = summary(pnet)
        if sp:
            print(f"\n  ── EŞİT-AĞIRLIK PORTFÖY (directional) ──")
            print(f"   yıllık net : {sp['ann_ret']:+.4f}  Sharpe={sp['sharpe']:.2f}  "
                  f"MDD={sp['mdd']:+.4f}  neg-bar={sp['frac_neg']*100:.1f}%")
            # BTC trend correlation
            btc_ret = load_btc_4h_aligned(pnet.index)
            cc = pd.concat([pnet.rename("arb"), btc_ret.rename("px")], axis=1).dropna()
            if len(cc) > 50:
                print(f"   BTC 4H getiri ile corr : {cc['arb'].corr(cc['px']):+.4f}  (|corr|<0.1 → yönsüz)")
            return pnet
    return None


def compare_to_carry(coin="BTC"):
    """Tek-borsa carry (Binance short-perp) vs cross-exchange arb robustluk kıyası."""
    print("\n" + "=" * 78)
    print("  KIYAS: TEK-BORSA CARRY vs ÇAPRAZ-BORSA ARB (negatif-funding rejimi dayanıklılığı)")
    print("=" * 78)
    rows = []
    for c in COINS:
        try:
            fbin = load_binance(c); fby = load_bybit(c)
        except Exception:
            continue
        common = pd.concat([fbin.rename("A"), fby.rename("B")], axis=1).dropna()
        if len(common) < 100:
            continue
        # single-exchange carry: short Binance perp, collect funding when >0 (always-on)
        carry = common["A"].copy()
        carry.iloc[0] -= ROUNDTRIP_COST
        net_arb, _ = arb_directional(fbin, fby)
        net_arb = net_arb.reindex(common.index).fillna(0.0)
        # fraction of accruals where the source is negative
        rows.append({
            "coin": c,
            "carry_frac_neg": float((common["A"] < 0).mean()),
            "carry_ann": float(carry.sum() / (len(carry)/ACCR_PER_YEAR)),
            "carry_sharpe": annualize_sharpe(carry.values),
            "arb_frac_neg": float((net_arb < 0).mean()),
            "arb_ann": float(net_arb.sum() / (len(net_arb)/ACCR_PER_YEAR)),
            "arb_sharpe": annualize_sharpe(net_arb.values),
            # correlation of the two PnL streams (diversification value)
            "corr": float(pd.Series(carry.values).corr(pd.Series(net_arb.values))),
        })
    if not rows:
        print("  veri yok"); return
    df = pd.DataFrame(rows)
    print(f"  (ortak Binance/Bybit takvimi, {len(df)} coin)")
    print(f"   CARRY  medyan ann={df['carry_ann'].median():+.4f}  Sharpe={df['carry_sharpe'].median():.2f}  "
          f"pozitif={int((df['carry_ann']>0).sum())}/{len(df)}")
    print(f"   ARB    medyan ann={df['arb_ann'].median():+.4f}  Sharpe={df['arb_sharpe'].median():.2f}  "
          f"pozitif={int((df['arb_ann']>0).sum())}/{len(df)}")
    print(f"   carry/arb PnL akış medyan corr = {df['corr'].median():+.4f}  "
          f"(düşük → diversifikasyon değeri var)")
    print(f"   medyan negatif-funding bar payı (kaynak Binance) = {df['carry_frac_neg'].median()*100:.1f}%")


def main():
    print("=" * 78)
    print("  ÇAPRAZ-BORSA FUNDING-ARB — gerçek funding (Binance/Bybit ~5yr, OKX ~3ay)")
    print(f"  maliyet: leg/side={LEG_SIDE_COST}  setup(2 leg)={SETUP_COST}  rebalance(4 taraf)={REBALANCE_COST}")
    print("=" * 78)

    # ANA test: Binance vs Bybit (uzun geçmiş)
    run_pair(load_binance, load_bybit, "BINANCE", "BYBIT", "binance_bybit")

    # KISA sanity: 3-borsa kısa pencerede OKX dahil iki çift
    run_pair(load_binance, load_okx, "BINANCE", "OKX", "binance_okx", weak=True)
    run_pair(load_bybit, load_okx, "BYBIT", "OKX", "bybit_okx", weak=True)

    compare_to_carry()

    print("\n" + "=" * 78)
    print("  DÜRÜSTLÜK NOTLARI:")
    print("  - Getiri 'notional oranı' (kaldıraçsız, iki perp bacak eşit notional).")
    print("  - Sharpe oto-korelasyonlu funding serisinden → ŞİŞİK olabilir, dikkat.")
    print("  - Modellenmiyen: iki borsada bölünmüş sermaye (atıl marj ~yarı getiri etkisi),")
    print("    perp likidasyon riski (her iki bacak marjinli), borsa-spesifik spread/derinlik,")
    print("    funding tahmin/rebalance gecikmesi. Hepsi net getiriyi AŞAĞI çeker.")
    print("  - OKX yalnız ~3 ay → o çiftler istatistiksel olarak ZAYIF, yön göstergesi.")
    print("=" * 78)


if __name__ == "__main__":
    main()
