#!/usr/bin/env python3
"""
edge_tf_1h.py — CEPHE "tf_1h": 1H YÜKSEK-FREKANS META-TREND
═══════════════════════════════════════════════════════════════════════
HİPOTEZ: 1H'te aynı trend-ensemble (donchian+supertrend) çalıştırılırsa ham
beklenti maliyet yüzünden büyük olasılıkla NEGATİF olur (daha çok whipsaw,
maliyet/sinyal oranı yüksek). Ama meta-label filtresi (walk-forward OOS) 1H'i
pozitife çevirip 4H'ten DAHA YÜKSEK FREKANSTA pozitif beklenti verebilir mi?
Net skor = frekans/yıl × beklenti(R)/işlem. 4H baseline: +0.165R, ~? işlem/yıl.

ÖLÇÜM KURALLARI (sızıntısız):
  • Causal feature, temporal split, look-ahead yok (signal_lab.simulate i+1 girişli).
  • Sadece walk-forward OOS lift sayılır (wf_lift mantığı, meta_features_v2 ile aynı).
  • 1H frekansı GERÇEK zaman span'inden hesaplanır (4H sabiti BARS_PER_YEAR KULLANILMAZ).
  • Maliyet signal_lab'tan: round-trip (fee+slip)*2, R cinsine /sl_dist ile çevrilir.

Çıktı: 4H net (freq×E) vs 1H meta net (freq×E). Gerçek lift yoksa dürüstçe "yok".
"""
import os, sys, json, time, math, datetime, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")

from signal_lab import (load_all, simulate, atr, ema, rsi, macd, sma, roc,
                        supertrend, adx, metrics, FEE, SLIP, RT_COST_PRICE)
import sig_donchian_breakout as D, sig_supertrend_regime as S
from meta_features_v2 import coin_feats, V1, V2_EXTRA, FEATURES_V2, wf_lift, STRATS

DATA_1H = "mktdata_1h"
COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]
# 4H ensemble ile AYNI strateji konfigürasyonu (donchian n40 atr0.25 + supertrend 10/3 adx25)
STRATS_1H = [("donchian", D.make_sig(40, "atr", 0.25, 0.0), 2.0, 2.5),
             ("supertrend", S.make_sig(10, 3, 25), 2.0, 3.0)]

# ── 1H veri çek (binance, ~3 yıl) ───────────────────────────────────────────
def fetch_1h(coins=COINS, years=3.0, outdir=DATA_1H):
    import ccxt
    os.makedirs(outdir, exist_ok=True)
    ex = ccxt.binance({"enableRateLimit": True, "timeout": 30000})
    now = ex.milliseconds()
    since0 = now - int(years * 365 * 24 * 3600 * 1000)
    for c in coins:
        path = f"{outdir}/{c}_USDT_1h.csv"
        if os.path.exists(path) and os.path.getsize(path) > 10000:
            print(f"  [skip] {c} already cached ({path})"); continue
        sym = f"{c}/USDT"; since = since0; rows = []
        while since < now:
            try:
                batch = ex.fetch_ohlcv(sym, "1h", since=since, limit=1000)
            except Exception as e:
                print(f"  [{c}] err {type(e).__name__}: {str(e)[:80]}; retry"); time.sleep(2); continue
            if not batch: break
            rows += batch
            since = batch[-1][0] + 3600_000
            if len(batch) < 1000: break
            time.sleep(ex.rateLimit / 1000.0)
        if not rows:
            print(f"  [{c}] NO DATA"); continue
        df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
        df = df.drop_duplicates("ts").sort_values("ts")
        df["ts"] = pd.to_datetime(df["ts"], unit="ms")
        df.to_csv(path, index=False)
        print(f"  [{c}] saved {len(df)} bars  {df['ts'].iloc[0]} → {df['ts'].iloc[-1]}")

# ── ham 1H ensemble değerlendirme (gerçek frekans dahil) ─────────────────────
def raw_eval_1h(dfs):
    """Ham (filtresiz) donchian+supertrend 1H pool metrikleri + gerçek freq/yr."""
    pool = []; per_coin = {}; total_years = 0.0; coin_years = {}
    for c, df in dfs.items():
        span_days = (df.index[-1] - df.index[0]).total_seconds() / 86400.0
        yrs = span_days / 365.0; coin_years[c] = yrs
        ctr = []
        for name, sig, sl, tp in STRATS_1H:
            tr = simulate(df, sig(df), sl_atr=sl, tp_r=tp)
            for t in tr: t["coin"] = c; t["strat"] = name
            ctr += tr
        per_coin[c] = metrics(ctr); pool += ctr
    # frekans: toplam trade / coin-yıl ortalaması (coin başına yıl ~ aynı, ama doğru olsun)
    avg_years = np.mean(list(coin_years.values())) if coin_years else 1.0
    n_coins = len(dfs)
    # tüm coin'lerdeki toplam coin-yıl
    total_coin_years = sum(coin_years.values())
    freq_yr = len(pool) / (total_coin_years / n_coins) if total_coin_years else 0  # per-coin yıllık ort
    return pool, per_coin, freq_yr, coin_years

# ── 1H meta-feature satırları (meta_features_v2 ile AYNI mantık, tf-agnostik) ─
def build_rows_1h(dfs):
    """Her 1H trade için v2 feature satırı (causal). Cross-sectional panel 1H coin'lerle."""
    panel = pd.DataFrame({c: df["close"] for c, df in dfs.items()}).sort_index().ffill()
    ret30 = panel.pct_change(30)
    xs = ret30.rank(axis=1, pct=True)
    btc = dfs["BTC"]; btc_e = btc["close"].ewm(span=200, adjust=False).mean()
    btc_reg = (btc["close"] > btc_e).astype(int); btc_ret = btc["close"].pct_change(10)
    feats = {c: coin_feats(df) for c, df in dfs.items()}
    rows = []
    for name, sig, sl, tp in STRATS_1H:
        for c, df in dfs.items():
            pos = sig(df); fa = feats[c]; idx = df.index
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
                row.update({"r_mult": t["r_mult"], "win": 1 if t["r_mult"] > 0 else 0,
                            "entry_ts": t["entry_ts"], "coin": c})
                rows.append(row)
    rows.sort(key=lambda x: x["entry_ts"])
    return rows

# ── wf_lift'i frekans-korumalı saran ölçüm: meta sonrası gerçek freq/yr ───────
def wf_lift_with_freq(rows, feats, total_coin_years, n_coins, thr=0.35, folds=4):
    """wf_lift ama ek olarak: OOS bölümünde KAÇ işlem seçildi → 1H yıllık frekansa çevir.
    OOS span = son %60 (start=0.4n → n). Bu span'in kapsadığı yıl = OOS işlemlerin
    zaman aralığı. Frekansı bu OOS dönemindeki seçilen trade sayısından hesaplarız."""
    n = len(rows)
    X = np.array([[r.get(f, np.nan) for f in feats] for r in rows], float)
    y = np.array([r["win"] for r in rows]); rm = np.array([r["r_mult"] for r in rows])
    from sklearn.ensemble import HistGradientBoostingClassifier
    start = int(n * 0.4); b = np.linspace(start, n, folds + 1).astype(int)
    sel = []; allr = []; coins = {}; sel_ts = []; oos_ts = []
    for k in range(folds):
        a, bb = b[k], b[k + 1]
        clf = HistGradientBoostingClassifier(max_depth=3, max_iter=200, learning_rate=0.05,
            l2_regularization=1.0, min_samples_leaf=80, random_state=42)
        clf.fit(X[:a - 20], y[:a - 20]); pr = clf.predict_proba(X[a:bb])[:, 1]
        for j in range(a, bb):
            allr.append(rm[j]); oos_ts.append(rows[j]["entry_ts"])
            if pr[j - a] >= thr:
                sel.append(rm[j]); sel_ts.append(rows[j]["entry_ts"])
                coins.setdefault(rows[j]["coin"], []).append(rm[j])
    sel = np.array(sel); allr = np.array(allr)
    pos = sum(1 for c, r in coins.items() if np.mean(r) > 0)
    # OOS dönemi gerçek yıl aralığı
    oos_t = pd.to_datetime(oos_ts)
    oos_span_days = (oos_t.max() - oos_t.min()).total_seconds() / 86400.0
    oos_years = oos_span_days / 365.0
    # OOS, n_coins coin'i paralel kapsıyor → per-coin-yıl = oos_years (aynı takvim aralığı)
    # seçilen trade yıllık frekansı (tüm coin toplamı / oos_years), sonra per-coin'e böl
    sel_freq_yr_total = len(sel) / oos_years if oos_years else 0
    sel_freq_yr_percoin = sel_freq_yr_total / n_coins
    base_freq_yr_total = len(allr) / oos_years if oos_years else 0
    return {"base_e": allr.mean(), "sel_e": sel.mean() if len(sel) else 0, "sel_n": len(sel),
            "sel_wr": (sel > 0).mean() * 100 if len(sel) else 0, "pos": pos, "tot": len(coins),
            "oos_years": oos_years, "sel_freq_yr_total": sel_freq_yr_total,
            "sel_freq_yr_percoin": sel_freq_yr_percoin, "base_freq_yr_total": base_freq_yr_total,
            "base_n": len(allr)}

def load_1h(coins=COINS, data=DATA_1H):
    out = {}
    for c in coins:
        p = f"{data}/{c}_USDT_1h.csv"
        if not os.path.exists(p): continue
        df = pd.read_csv(p); df["ts"] = pd.to_datetime(df["ts"])
        out[c] = df.set_index("ts").sort_index()
    return out

def main():
    print("=" * 80); print("  CEPHE tf_1h — 1H YÜKSEK-FREKANS META-TREND vs 4H BASELINE"); print("=" * 80)
    if "--fetch" in sys.argv or not os.path.exists(f"{DATA_1H}/BTC_USDT_1h.csv"):
        print("\n[1] 1H veri çekiliyor (binance, ~3y)...")
        fetch_1h(years=3.0)
    dfs = load_1h()
    if len(dfs) < 3:
        print("YETERSİZ 1H veri:", list(dfs.keys())); return
    for c, df in dfs.items():
        print(f"  {c}: {len(df)} bar  {df.index[0]} → {df.index[-1]}")
    n_coins = len(dfs)
    total_coin_years = sum((df.index[-1] - df.index[0]).total_seconds() / 86400.0 / 365.0
                           for df in dfs.values())

    print("\n[2] HAM 1H ensemble (donchian n40 + supertrend 10/3 adx25, filtresiz)")
    pool, per_coin, freq_yr, coin_years = raw_eval_1h(dfs)
    m = metrics(pool)
    print(f"    N={m['n']}  ham freq/yr(per-coin)={freq_yr:.0f}  WR={m['wr']:.1f}%  "
          f"E={m['avg_r']:+.4f}R  PF={m['pf']:.2f}")
    pc = "  ".join(f"{c}:{per_coin[c].get('avg_r', 0):+.3f}" for c in dfs)
    print(f"    per-coin E: {pc}")
    raw_net = m['avg_r'] * freq_yr
    print(f"    >>> HAM net (freq×E) per-coin/yıl = {raw_net:+.2f} R/yıl")

    print("\n[3] META-LABEL feature satırları (v2, causal) üretiliyor...")
    rows = build_rows_1h(dfs)
    print(f"    {len(rows)} 1H trade satırı")

    print("\n[4] WALK-FORWARD OOS META-LABEL LİFT (v1 ve v2 feature setleri)")
    res = {}
    for tag, fl in [("v1", V1 + ["dir", "sl_dist"]), ("v2", FEATURES_V2)]:
        r = wf_lift_with_freq(rows, fl, total_coin_years, n_coins, thr=0.35, folds=4)
        res[tag] = r
        net_percoin = r["sel_e"] * r["sel_freq_yr_percoin"]
        base_net_percoin = r["base_e"] * (r["base_freq_yr_total"] / n_coins)
        print(f"  [{tag}] OOS base E={r['base_e']:+.4f}R (N={r['base_n']}) → meta E={r['sel_e']:+.4f}R "
              f"(N={r['sel_n']}, WR%{r['sel_wr']:.0f}, {r['pos']}/{r['tot']} coin+)")
        print(f"       OOS span={r['oos_years']:.2f}y  meta freq/yr(per-coin)={r['sel_freq_yr_percoin']:.0f}  "
              f"→ META net = {net_percoin:+.2f} R/yıl  (ham OOS net {base_net_percoin:+.2f})")

    # threshold süpürmesi (v2): en iyi OOS-robust net
    print("\n[5] THRESHOLD süpürmesi (v2 feature, frekans×beklenti maksimizasyonu)")
    best = None
    for thr in [0.30, 0.35, 0.40, 0.45, 0.50, 0.55]:
        r = wf_lift_with_freq(rows, FEATURES_V2, total_coin_years, n_coins, thr=thr, folds=4)
        robust = (r["sel_e"] > 0 and r["pos"] >= 0.6 * r["tot"] and r["sel_n"] >= 30)
        net = r["sel_e"] * r["sel_freq_yr_percoin"]
        print(f"  thr={thr:.2f}  E={r['sel_e']:+.4f}R  N={r['sel_n']:4d}  freq/yr={r['sel_freq_yr_percoin']:5.0f}  "
              f"{r['pos']}/{r['tot']}+  net={net:+.2f}R/yr  {'robust' if robust else '-'}")
        cand = dict(thr=thr, **r, robust=robust, net=net)
        if best is None or (cand["robust"], cand["net"]) > (best["robust"], best["net"]):
            best = cand

    print("\n" + "=" * 80)
    print("  KARAR")
    print("=" * 80)
    # 4H baseline net: +0.165R, freq? 4H ensemble per-coin freq/yr'ı ölçelim (referans)
    base4h_e = 0.165
    print(f"  4H BASELINE: meta E={base4h_e:+.3f}R  (mevcut sistem, 16/20 coin)")
    print(f"  1H BEST(v2): thr={best['thr']:.2f}  E={best['sel_e']:+.4f}R  "
          f"freq/yr(per-coin)={best['sel_freq_yr_percoin']:.0f}  net={best['net']:+.2f}R/yr  "
          f"{best['pos']}/{best['tot']}coin+  robust={best['robust']}")
    out = {"raw_1h": {"e": m['avg_r'], "freq": freq_yr, "net": raw_net, "n": m['n']},
           "meta_v1": res["v1"], "meta_v2": res["v2"], "best": best}
    json.dump(out, open("/tmp/edge_tf_1h_result.json", "w"), default=float)
    return out

if __name__ == "__main__":
    main()
