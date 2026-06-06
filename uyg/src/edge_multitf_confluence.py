#!/usr/bin/env python3
"""
edge_multitf_confluence.py — CEPHE: multitf_confluence (çok-zamanlı konfluans)
═══════════════════════════════════════════════════════════════════════════
HİPOTEZ: 4H trend entry'sini (donchian breakout / supertrend regime) yalnız
DAHA YÜKSEK TF (günlük) trend yönüyle HİZALI olduğunda al. Yani:
  4H donchian/supertrend LONG sinyali  +  günlük EMA200/SuperTrend UP  → AL
  ayrışınca (4H long ama günlük down) → ATLA (kalite filtresi).

Konfluans kalite filtresi olarak WR/beklentiyi yükseltiyor mu, frekansı ne
kadar düşürüyor? İki düzlemde DÜRÜSTÇE ölç:
  (A) HAM SİNYAL FİLTRESİ  → signal_lab.evaluate ile OOS beklenti + frekans
  (B) META-FEATURE         → meta_features_v2.wf_lift ile +0.165R baseline'a
                             günlük-konfluans causal feature ekleyip OOS lift

SIZINTI KONTROLÜ (kritik):
  Günlük bar "bugün" ancak gün sonunda TAMAMLANIR. 4H bar i (örn saat 08:00)
  anında bugünün günlük barı henüz oluşuyor. Bu yüzden günlük trendi
  hesaplarken yalnız SON TAMAMLANMIŞ günlük barı (dün kapanış) kullanırız.
  İki causal yöntem:
    • rolling proxy: günlük EMA200 ≈ 4H EMA(span=200*6=1200); doğal causal.
    • true daily resample + 1-gün shift + ffill: her 4H bar yalnız dünün
      tamamlanmış günlük değerini görür (look-ahead yok).
"""
import json, sys
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

from signal_lab import (evaluate, report, load_all, simulate, atr, ema, rsi,
                        macd, sma, roc, supertrend, adx, donchian)
import sig_donchian_breakout as D
import sig_supertrend_regime as S


# ═══════════════════════════════════════════════════════════════════════════
# CAUSAL GÜNLÜK TREND HESABI (look-ahead'siz)
# ═══════════════════════════════════════════════════════════════════════════

def daily_trend_rolling_ema(df, day_bars=6, ema_n=200):
    """ROLLING PROXY: günlük EMA200 ≈ 4H EMA(span=ema_n*day_bars).
    Her 4H barda doğal olarak causal (geçmiş + şimdiki kapanış)."""
    c = df["close"].to_numpy(float)
    e = ema(c, ema_n * day_bars)
    return np.where(c > e, 1, -1).astype(float)


def daily_trend_resample(df, ema_n=200, kind="ema", st_period=10, st_mult=3.0):
    """TRUE DAILY RESAMPLE + 1-GÜN SHIFT + FFILL (look-ahead'siz).
    4H -> günlük OHLC resample; günlük EMA200 (kind='ema') ya da günlük
    SuperTrend (kind='st') yön hesapla; SONRA 1 gün shift et (bugünün günlük
    barı henüz tamamlanmadı → yalnız dünün tamamlanmış değerini kullan);
    günlük değeri 4H index'e ffill ile yay.
    Döner: 4H uzunluğunda +1/-1/0 (warmup'ta 0) dizi."""
    d = df.resample("1D").agg({"open": "first", "high": "max", "low": "min",
                               "close": "last", "volume": "sum"}).dropna()
    if kind == "ema":
        de = d["close"].ewm(span=ema_n, adjust=False).mean()
        dt = np.where(d["close"].to_numpy() > de.to_numpy(), 1.0, -1.0)
    elif kind == "st":
        dt = supertrend(d, st_period, st_mult)  # +1/-1
    else:
        raise ValueError(kind)
    dser = pd.Series(dt, index=d.index)
    # KRİTİK: 1 gün shift → 4H bar i, ancak DÜN tamamlanmış günlük barı görür
    dser = dser.shift(1)
    # 4H index'e hizala: her 4H ts için <= ts olan en son günlük değer (ffill)
    aligned = dser.reindex(df.index, method="ffill")
    return aligned.fillna(0.0).to_numpy()


# ═══════════════════════════════════════════════════════════════════════════
# (A) HAM SİNYAL FİLTRESİ — base trend signal × günlük konfluans
# ═══════════════════════════════════════════════════════════════════════════

def make_confluence_sig(base_sig_fn, daily_fn, mode="filter"):
    """base_sig_fn(df)->pos (4H trend), daily_fn(df)->günlük yön (+1/-1/0).
    mode='filter': 4H sinyal yalnız günlük yön AYNI ise geçer, değilse 0.
    mode='none'  : filtresiz (baseline karşılaştırması)."""
    def sig(df):
        pos = np.asarray(base_sig_fn(df), float).copy()
        if mode == "none":
            return pos
        dt = daily_fn(df)
        # konfluans: işaret aynı yönde değilse sinyali iptal et
        mask = np.sign(pos) != np.sign(dt)
        pos[mask] = 0.0
        return pos
    return sig


# baz 4H trend stratejileri (meta-label ensemble ile aynı, +0.165 kaynağı)
BASE_STRATS = [
    ("donchian", D.make_sig(40, "atr", 0.25, 0.0), 2.0, 2.5),
    ("supertrend", S.make_sig(10, 3, 25), 2.0, 3.0),
]

# denenecek günlük konfluans tanımları
DAILY_DEFS = {
    "ema200_roll": lambda df: daily_trend_rolling_ema(df, 6, 200),
    "ema100_roll": lambda df: daily_trend_rolling_ema(df, 6, 100),
    "ema200_resmp": lambda df: daily_trend_resample(df, 200, "ema"),
    "ema50_resmp": lambda df: daily_trend_resample(df, 50, "ema"),
    "st_resmp": lambda df: daily_trend_resample(df, kind="st", st_period=10, st_mult=3.0),
}


def run_filter_experiments():
    print("=" * 86)
    print("  (A) HAM SİNYAL FİLTRESİ — 4H trend × günlük konfluans (signal_lab.evaluate)")
    print("=" * 86)
    rows = []
    for sname, sfn, sl, tp in BASE_STRATS:
        # baseline (filtresiz)
        base = evaluate(make_confluence_sig(sfn, None, "none"), tf="4h",
                        sl_atr=sl, tp_r=tp, label=f"{sname} BASE")
        bp = base["pool"]
        print(f"\n  ── {sname} (sl{sl} tp{tp}) ──")
        print(f"  [BASE        ] N={bp['n']:5d} freq/yr={base['freq_yr']:6.0f} "
              f"WR={bp['wr']:5.1f}% E={bp['avg_r']:+.3f}R PF={bp['pf']:.2f} "
              f"test={base['test'].get('avg_r',0):+.3f} +c={base['pos_coins']}/{base['tot_coins']} "
              f"{'ROBUST' if base['robust'] else '-'}")
        rows.append(("BASE", sname, base))
        for dname, dfn in DAILY_DEFS.items():
            res = evaluate(make_confluence_sig(sfn, dfn, "filter"), tf="4h",
                           sl_atr=sl, tp_r=tp, label=f"{sname}+{dname}")
            p = res["pool"]
            dE = p["avg_r"] - bp["avg_r"]
            dWR = p["wr"] - bp["wr"]
            keep = p["n"] / bp["n"] if bp["n"] else 0
            print(f"  [+{dname:12s}] N={p['n']:5d} freq/yr={res['freq_yr']:6.0f} "
                  f"WR={p['wr']:5.1f}%({dWR:+.1f}) E={p['avg_r']:+.3f}R({dE:+.3f}) PF={p['pf']:.2f} "
                  f"test={res['test'].get('avg_r',0):+.3f} +c={res['pos_coins']}/{res['tot_coins']} "
                  f"keep={keep*100:.0f}% {'ROBUST' if res['robust'] else '-'}")
            rows.append((dname, sname, res))
    return rows


# ═══════════════════════════════════════════════════════════════════════════
# (B) META-FEATURE — günlük konfluansı v2 feature setine ekle, OOS lift ölç
# ═══════════════════════════════════════════════════════════════════════════

def build_rows_with_confluence():
    """meta_features_v2.build_v2 mantığını AYNEN tekrarla ama her trade satırına
    CAUSAL günlük-konfluans feature'ları EKLE:
      d_ema200r  — günlük EMA200 (rolling proxy) yönü {+1,-1}
      d_ema200   — günlük EMA200 (resample+shift) yönü {+1,-1,0}
      d_st       — günlük SuperTrend (resample+shift) yönü {+1,-1,0}
      conf_ema   — 4H trade yönü günlük EMA200(resmp) ile aynı mı {1/0}
      conf_st    — 4H trade yönü günlük SuperTrend ile aynı mı {1/0}
      conf_sum   — kaç günlük onay (conf_ema+conf_st+rolling) {0..3}
      d_dist     — fiyatın günlük EMA200'e % uzaklığı (causal, resample+shift)
    Sonra wf_lift ile v2 vs v2+confluence OOS karşılaştır."""
    from meta_features_v2 import coin_feats, V1, STRATS
    dfs = load_all("mktdata", "4h")
    panel = pd.DataFrame({c: df["close"] for c, df in dfs.items()}).sort_index().ffill()
    ret30 = panel.pct_change(30)
    xs = ret30.rank(axis=1, pct=True)
    btc = dfs["BTC"]; btc_e = btc["close"].ewm(span=200, adjust=False).mean()
    btc_reg = (btc["close"] > btc_e).astype(int); btc_ret = btc["close"].pct_change(10)
    feats = {c: coin_feats(df) for c, df in dfs.items()}

    # her coin için causal günlük serileri (hizalı, 4H uzunluğunda)
    daily = {}
    for c, df in dfs.items():
        d_ema200r = daily_trend_rolling_ema(df, 6, 200)
        d_ema200 = daily_trend_resample(df, 200, "ema")
        d_st = daily_trend_resample(df, kind="st", st_period=10, st_mult=3.0)
        # günlük EMA200'e % uzaklık (resample+shift, causal)
        dd = df.resample("1D").agg({"open": "first", "high": "max", "low": "min",
                                    "close": "last", "volume": "sum"}).dropna()
        de = dd["close"].ewm(span=200, adjust=False).mean()
        ddist = ((dd["close"] - de) / (de + 1e-9)).shift(1).reindex(df.index, method="ffill")
        daily[c] = {"d_ema200r": d_ema200r, "d_ema200": d_ema200, "d_st": d_st,
                    "d_dist": ddist.fillna(0.0).to_numpy()}

    rows = []
    for name, sig, sl, tp in STRATS:
        for c, df in dfs.items():
            pos = sig(df); fa = feats[c]; idx = df.index; dy = daily[c]
            for t in simulate(df, pos, sl_atr=sl, tp_r=tp):
                fi = t["entry_i"] - 1
                if fi < 200 or fi >= len(df):
                    continue
                ts = idx[fi]
                d = t["dir"]; age = 0
                while fi - age > 0 and np.sign(pos[fi - age]) == np.sign(pos[fi]) and pos[fi] != 0:
                    age += 1
                row = {f: (float(fa[f][fi]) if f in fa and np.isfinite(fa[f][fi]) else np.nan) for f in V1}
                row["dir"] = d; row["sl_dist"] = t["sl_dist"]
                row["xs_rank"] = float(xs[c].get(ts, np.nan)) if ts in xs.index else np.nan
                row["btc_reg"] = float(btc_reg.get(ts, np.nan)) if ts in btc_reg.index else np.nan
                row["btc_ret"] = float(btc_ret.get(ts, np.nan)) if ts in btc_ret.index else np.nan
                row["trend_age"] = float(age)
                row["ext"] = float(fa["ext"][fi]) if np.isfinite(fa["ext"][fi]) else np.nan
                row["volp"] = float(fa["volp"][fi]) if np.isfinite(fa["volp"][fi]) else np.nan
                # ── KONFLUANS FEATURE'LARI (causal) ──
                de200r = dy["d_ema200r"][fi]; de200 = dy["d_ema200"][fi]; dst = dy["d_st"][fi]
                row["d_ema200r"] = float(de200r)
                row["d_ema200"] = float(de200)
                row["d_st"] = float(dst)
                row["conf_ema"] = 1.0 if (de200 != 0 and np.sign(d) == np.sign(de200)) else 0.0
                row["conf_st"] = 1.0 if (dst != 0 and np.sign(d) == np.sign(dst)) else 0.0
                conf_r = 1.0 if np.sign(d) == np.sign(de200r) else 0.0
                row["conf_sum"] = row["conf_ema"] + row["conf_st"] + conf_r
                row["d_dist"] = float(dy["d_dist"][fi]) if np.isfinite(dy["d_dist"][fi]) else np.nan
                # yön-bağımsız: trade yönüyle çarpılmış uzaklık (aligned ise +)
                row["d_dist_signed"] = float(d * dy["d_dist"][fi]) if np.isfinite(dy["d_dist"][fi]) else np.nan
                row.update({"r_mult": t["r_mult"], "win": 1 if t["r_mult"] > 0 else 0,
                            "entry_ts": t["entry_ts"], "coin": c})
                rows.append(row)
    rows.sort(key=lambda x: x["entry_ts"])
    return rows


CONF_FEATS = ["d_ema200r", "d_ema200", "d_st", "conf_ema", "conf_st",
              "conf_sum", "d_dist", "d_dist_signed"]


def run_meta_experiments():
    from meta_features_v2 import wf_lift, FEATURES_V2
    print("\n" + "=" * 86)
    print("  (B) META-FEATURE — v2 baseline vs v2+günlük-konfluans (wf_lift OOS)")
    print("=" * 86)
    rows = build_rows_with_confluence()
    json.dump(rows, open("/tmp/meta_dataset_confluence.json", "w"))
    print(f"  rebuilt {len(rows)} trade (konfluans feature'lı)")

    # 1) saf konfluans onayı baseline expectancy'e ne yapıyor? (filtre simülasyonu)
    rm = np.array([r["r_mult"] for r in rows])
    for k in (1, 2, 3):
        m = np.array([r["conf_sum"] >= k for r in rows])
        sub = rm[m]
        print(f"  [naive conf_sum>={k}] N={m.sum():5d} keep={m.mean()*100:4.0f}% "
              f"E={sub.mean():+.3f}R WR={(sub>0).mean()*100:.1f}%   (tüm: E={rm.mean():+.3f}R)")

    # 2) v2 baseline
    r2 = wf_lift(rows, FEATURES_V2)
    print(f"\n  v2 baseline           : base E={r2['base_e']:+.4f} → meta E={r2['sel_e']:+.4f}R "
          f"(N={r2['sel_n']}, WR{r2['sel_wr']:.0f}%, {r2['pos']}/{r2['tot']} coin+)")

    # 3) v2 + her bir konfluans feature alt-kümesi
    variants = {
        "v2+conf_all": FEATURES_V2 + CONF_FEATS,
        "v2+conf_core": FEATURES_V2 + ["conf_ema", "conf_st", "conf_sum"],
        "v2+d_dist": FEATURES_V2 + ["d_dist", "d_dist_signed"],
        "v2+d_dir": FEATURES_V2 + ["d_ema200", "d_st", "d_ema200r"],
        "v2+conf_sum_only": FEATURES_V2 + ["conf_sum"],
    }
    best = ("v2_baseline", r2["sel_e"], r2)
    for vname, flist in variants.items():
        rv = wf_lift(rows, flist)
        lift = rv["sel_e"] - r2["sel_e"]
        print(f"  {vname:21s} : base E={rv['base_e']:+.4f} → meta E={rv['sel_e']:+.4f}R "
              f"(N={rv['sel_n']}, WR{rv['sel_wr']:.0f}%, {rv['pos']}/{rv['tot']} coin+)  "
              f"lift vs v2={lift:+.4f}")
        if rv["sel_e"] > best[1] and rv["pos"] >= 0.6 * rv["tot"]:
            best = (vname, rv["sel_e"], rv)
    return r2, best, rows


if __name__ == "__main__":
    filt_rows = run_filter_experiments()
    r2_base, meta_best, meta_rows = run_meta_experiments()
    print("\n" + "=" * 86)
    print("  ÖZET")
    print("=" * 86)
    print(f"  v2 baseline meta OOS E = {r2_base['sel_e']:+.4f}R")
    print(f"  EN İYİ meta varyant    = {meta_best[0]}  E={meta_best[1]:+.4f}R  "
          f"lift={meta_best[1]-r2_base['sel_e']:+.4f}R")
