#!/usr/bin/env python3
"""
oi_ls_test.py — Binance futures OI + top-trader long/short ratio sinyali testi.

Veri: metricsdata/{COIN}_metrics_4h.csv (binance.vision daily metrics dump, 4H agg)
  cols: ts, oi, oi_value, toptrader_ls_ratio, ls_ratio, taker_buy_sell_ratio
  Tüm metrikler bar-kapanışında gözlemlenebilir (5m->4H last/mean).

Test tasarımı (signal_lab rigor):
  Feature'lar CAUSAL + shift(1) (sinyal kapanmış barda; giriş sonraki bar).
  (a) BAĞIMSIZ kontrarian sinyal: toptrader aşırı long -> short, vb.
  (b) trend (SuperTrend) sinyaline OI-onayı FİLTRESİ.
  Null/permutation: feature shuffle -> lift kayboluyor mu.
  Trend edge ile korelasyon.

DÜRÜSTLÜK: sadece çalışan stdout. Lift yoksa negatif.
"""
import os, sys, warnings
import numpy as np
import pandas as pd
import signal_lab as sl

warnings.filterwarnings("ignore")
np.random.seed(7)

METDIR = "metricsdata"


def zscore(s, win):
    s = pd.Series(s)
    return ((s - s.rolling(win).mean()) / (s.rolling(win).std() + 1e-12)).to_numpy()


def load_merged(coin):
    """mktdata OHLCV + metrics, inner-join on ts. Returns df or None."""
    mp = f"mktdata/{coin}_USDT_4h.csv"
    xp = f"{METDIR}/{coin}_metrics_4h.csv"
    if not (os.path.exists(mp) and os.path.exists(xp)):
        return None
    m = pd.read_csv(mp, parse_dates=["ts"]).set_index("ts").sort_index()
    x = pd.read_csv(xp, parse_dates=["ts"]).set_index("ts").sort_index()
    # guard against bad rows (oi==0)
    x = x[(x["oi"] > 0) & (x["toptrader_ls_ratio"] > 0)]
    df = m.join(x, how="inner")
    if len(df) < 400:
        return None
    return df


def add_features(df):
    """Causal features. NOT shifted here; signal_fn applies shift(1) at use."""
    out = df.copy()
    oi = out["oi"].to_numpy(float)
    tls = out["toptrader_ls_ratio"].to_numpy(float)
    gls = out["ls_ratio"].to_numpy(float)
    tak = out["taker_buy_sell_ratio"].to_numpy(float)
    out["oi_roc"] = sl.roc(oi, 6)          # 24h OI change
    out["oi_z"] = zscore(oi, 90)           # ~15d OI z-score
    out["tls_z"] = zscore(tls, 90)         # toptrader LS z-score (level extreme)
    out["tls_chg"] = sl.roc(tls, 6)        # toptrader LS 24h change
    out["gls_z"] = zscore(gls, 90)         # global LS z-score
    out["tak_z"] = zscore(tak, 90)         # taker buy/sell z-score
    return out


def C(arr):
    """shift(1): use only past/closed-bar info for entry at next bar (signal_lab gives i+1 entry)."""
    a = np.asarray(arr, float)
    s = np.empty_like(a); s[0] = np.nan; s[1:] = a[:-1]
    return s


# ── Cache merged frames ──
COINS = sl.evaluate.__defaults__  # not used; explicit list below
ALL = "BTC ETH SOL BNB XRP ADA AVAX DOGE DOT LINK LTC UNI ATOM NEAR APT ARB OP FIL INJ ETC".split()


def build_cache():
    cache = {}
    for c in ALL:
        df = load_merged(c)
        if df is not None:
            cache[c] = add_features(df)
    return cache


def eval_signal(cache, signal_fn, label, sl_atr=1.5, tp_r=2.0):
    pool = []; per_coin = {}; span = 0
    for c, df in cache.items():
        pos = signal_fn(df)
        tr = sl.simulate(df, pos, sl_atr=sl_atr, tp_r=tp_r)
        for t in tr: t["coin"] = c
        per_coin[c] = sl.metrics(tr); pool += tr; span = max(span, len(df))
    m = sl.metrics(pool)
    pool.sort(key=lambda x: x["exit_ts"])
    split = int(len(pool) * 0.6)
    trm = sl.metrics(pool[:split]); tem = sl.metrics(pool[split:])
    pos_coins = sum(1 for cm in per_coin.values() if cm.get("avg_r", -9) > 0)
    freq = m["n"] / (span / sl.BARS_PER_YEAR) if span else 0
    robust = (m["avg_r"] > 0 and tem.get("avg_r", -9) > 0 and pos_coins >= 0.6 * len(per_coin))
    print(f"  [{label}] N={m['n']} freq/yr={freq:.0f} WR={m['wr']:.1f}% "
          f"beklenti={m['avg_r']:+.4f}R PF={m['pf']:.2f}")
    print(f"       OOS train={trm.get('avg_r',0):+.4f} test={tem.get('avg_r',0):+.4f} "
          f"per-coin+ {pos_coins}/{len(per_coin)} -> {'ROBUST' if robust else 'robust degil'}")
    return {"m": m, "train": trm, "test": tem, "pos_coins": pos_coins,
            "n_coins": len(per_coin), "freq": freq, "robust": robust,
            "pool": pool, "per_coin": per_coin}


# ════════ SIGNAL DEFINITIONS ════════

def st_dir(df):
    return sl.supertrend(df, 10, 3.0)


def sig_trend_only(df):
    return st_dir(df)


# (a) Standalone contrarian: extreme top-trader LS level -> fade
def make_contrarian_tls(zthr):
    def f(df):
        z = C(df["tls_z"].to_numpy())
        pos = np.zeros(len(df))
        pos[z > zthr] = -1   # crowd very long -> short
        pos[z < -zthr] = 1   # crowd very short -> long
        return pos
    return f


# contrarian on global LS
def make_contrarian_gls(zthr):
    def f(df):
        z = C(df["gls_z"].to_numpy())
        pos = np.zeros(len(df))
        pos[z > zthr] = -1
        pos[z < -zthr] = 1
        return pos
    return f


# OI surge as momentum confirm: rising OI + rising price -> long (and vice versa)
def make_oi_momentum(roc_thr):
    def f(df):
        oiroc = C(df["oi_roc"].to_numpy())
        pret = C(sl.roc(df["close"].to_numpy(float), 6))
        pos = np.zeros(len(df))
        long = (oiroc > roc_thr) & (pret > 0)
        short = (oiroc > roc_thr) & (pret < 0)
        pos[long] = 1; pos[short] = -1
        return pos
    return f


# (b) Trend + OI confirmation filter: only take SuperTrend dir when OI rising (conviction)
def make_trend_oi_filter(roc_thr):
    def f(df):
        d = st_dir(df)
        oiroc = C(df["oi_roc"].to_numpy())
        d = d.copy()
        d[~(oiroc > roc_thr)] = 0   # suppress trades without OI buildup
        return d
    return f


# (b2) Trend + contrarian-crowd filter: take trend dir but veto when crowd already extreme same side
def make_trend_crowd_filter(zthr):
    def f(df):
        d = st_dir(df)
        z = C(df["tls_z"].to_numpy())
        d = d.copy()
        # if long trend but crowd already euphoric long -> skip; if short but crowd capitulated short -> skip
        d[(d == 1) & (z > zthr)] = 0
        d[(d == -1) & (z < -zthr)] = 0
        return d
    return f


def shuffle_feature(df, col):
    """Return df copy with one feature column randomly permuted (null test)."""
    out = df.copy()
    vals = out[col].to_numpy().copy()
    np.random.shuffle(vals)
    out[col] = vals
    return out


def main():
    cache = build_cache()
    print("=" * 78)
    print(f"  OI + TOP-TRADER LS TEST | coins={len(cache)} | "
          f"{'feasible' if cache else 'NO DATA'}")
    if cache:
        anyc = next(iter(cache))
        print(f"  ornek {anyc}: {cache[anyc].index[0]} .. {cache[anyc].index[-1]} "
              f"n={len(cache[anyc])}")
    print("=" * 78)
    if not cache:
        print("INFEASIBLE: metricsdata yok")
        return

    print("\n-- BASELINE (referans) --")
    base = eval_signal(cache, sig_trend_only, "SuperTrend(10,3) trend-only")

    print("\n-- (a) BAGIMSIZ KONTRARIAN sinyaller --")
    for z in (1.0, 1.5, 2.0):
        eval_signal(cache, make_contrarian_tls(z), f"contrarian toptraderLS |z|>{z}", sl_atr=1.5, tp_r=1.5)
    for z in (1.0, 1.5):
        eval_signal(cache, make_contrarian_gls(z), f"contrarian globalLS |z|>{z}", sl_atr=1.5, tp_r=1.5)

    print("\n-- (a) OI-momentum (OI surge + price dir) --")
    for r in (0.03, 0.06, 0.10):
        eval_signal(cache, make_oi_momentum(r), f"OI-mom roc>{r}", sl_atr=1.5, tp_r=2.0)

    print("\n-- (b) TREND + OI-onay filtresi --")
    filt_res = {}
    for r in (0.0, 0.02, 0.04):
        filt_res[r] = eval_signal(cache, make_trend_oi_filter(r), f"trend & OIroc>{r}")

    print("\n-- (b2) TREND + crowd-extreme veto --")
    for z in (1.0, 1.5):
        eval_signal(cache, make_trend_crowd_filter(z), f"trend & NOT crowd-extreme |z|>{z}")

    print("\n-- NULL/PERMUTATION TEST --")
    print("  best filtre feature (oi_roc) shuffle edildiginde lift kayboluyor mu?")
    # pick the trend+OI filter with best test avg_r among r>0
    best_r = max([0.02, 0.04], key=lambda r: filt_res[r]["test"].get("avg_r", -9))
    print(f"  (gercek filtre roc>{best_r} test avgR={filt_res[best_r]['test'].get('avg_r',0):+.4f}, "
          f"base test avgR={base['test'].get('avg_r',0):+.4f})")
    null_tests = []
    for trial in range(5):
        shuf = {c: shuffle_feature(df, "oi_roc") for c, df in cache.items()}
        r = eval_signal(shuf, make_trend_oi_filter(best_r), f"NULL trial{trial} trend&shuf(OIroc)>{best_r}")
        null_tests.append(r["m"]["avg_r"])
    real_filt = filt_res[best_r]["m"]["avg_r"]
    print(f"  GERCEK filtre pool avgR={real_filt:+.4f} | NULL ort={np.mean(null_tests):+.4f} "
          f"std={np.std(null_tests):.4f} | lift={real_filt-np.mean(null_tests):+.4f}")

    print("\n-- TREND EDGE ile KORELASYON (filtrenin secici oldugu barlarda mi?) --")
    # Compare per-trade returns: does OI-filter just subselect same trend trades?
    base_trades = {(t["coin"], t["entry_ts"]): t["r_mult"] for t in base["pool"]}
    filt_trades = filt_res[best_r]["pool"]
    overlap = sum(1 for t in filt_trades if (t["coin"], t["entry_ts"]) in base_trades)
    print(f"  filtre trade'lerinin {overlap}/{len(filt_trades)} tanesi base trend trade'i ile ayni giris "
          f"(yani filtre = trend'in alt-kumesi). Bagimsiz alfa yok ise sadece secim.")

    print("\n" + "=" * 78)
    print("  OZET: yukaridaki ROBUST etiketlerine ve NULL lift'e bak.")
    print("=" * 78)


if __name__ == "__main__":
    main()
