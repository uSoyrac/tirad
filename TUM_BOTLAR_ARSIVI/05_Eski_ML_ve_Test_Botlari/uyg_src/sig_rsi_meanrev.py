#!/usr/bin/env python3
"""
sig_rsi_meanrev.py — RSI mean-reversion (counter-trend) sinyal ailesi.

Mantık: range/yatay piyasada aşırılıklardan ortalamaya dönüş.
  rsi < oversold  -> LONG  (dipten dönüş beklentisi)
  rsi > overbought -> SHORT (tepeden dönüş beklentisi)

İki mod denenir:
  1) PURE range modu: saf RSI counter-trend (trend filtresi yok)
  2) TREND-ALIGNED modu: sadece ana trend (ema200) yönünde counter-pullback al.
     close>ema200 iken sadece LONG (oversold dip alımı),
     close<ema200 iken sadece SHORT (overbought tepe satışı).

oversold in {25,30,35}, overbought in {65,70,75} süpürülür.
sl_atr / tp_r küçük süpürülür. EN İYİ OOS-ROBUST config seçilir.

CAUSAL: pos[i] yalnız i ve öncesini kullanır. Giriş i+1 açılışında (harness).
"""
import json
import numpy as np
from signal_lab import evaluate, report, rsi, ema


def make_pure(oversold, overbought):
    def sig(df):
        c = df["close"].to_numpy(float)
        r = rsi(c, 14)
        pos = np.zeros(len(df))
        for i in range(200, len(df)):
            if r[i] < oversold:
                pos[i] = 1
            elif r[i] > overbought:
                pos[i] = -1
        return pos
    return sig


def make_trend(oversold, overbought):
    def sig(df):
        c = df["close"].to_numpy(float)
        r = rsi(c, 14)
        e = ema(c, 200)
        pos = np.zeros(len(df))
        for i in range(200, len(df)):
            # ana trend yönünde counter-pullback
            if c[i] > e[i] and r[i] < oversold:
                pos[i] = 1            # uptrend dip alımı
            elif c[i] < e[i] and r[i] > overbought:
                pos[i] = -1           # downtrend tepe satışı
        return pos
    return sig


def main():
    configs = []
    # küçük süpürme (3-6 kombinasyon hedefi, iki mod)
    sweep = [
        ("pure", 30, 70, 1.5, 2.0),
        ("pure", 25, 75, 1.5, 2.0),
        ("pure", 35, 65, 1.0, 1.5),
        ("trend", 30, 70, 1.5, 2.0),
        ("trend", 35, 65, 1.5, 1.5),
        ("trend", 25, 75, 2.0, 2.0),
    ]
    results = []
    for mode, os_, ob, sl, tp in sweep:
        fn = make_pure(os_, ob) if mode == "pure" else make_trend(os_, ob)
        label = f"{mode} os={os_} ob={ob} sl={sl} tp={tp}"
        res = evaluate(fn, data="mktdata", tf="4h", sl_atr=sl, tp_r=tp, label=label)
        res["_cfg"] = {"mode": mode, "oversold": os_, "overbought": ob,
                       "sl_atr": sl, "tp_r": tp}
        report(res)
        results.append(res)

    # seçim: önce robust olanlar, sonra test avg_r'ye göre (OOS odaklı)
    robust = [r for r in results if r["robust"]]
    pool = robust if robust else results
    best = max(pool, key=lambda r: (r["robust"], r["test"].get("avg_r", -9),
                                    r["pool"].get("avg_r", -9)))
    print("\n=== BEST ===")
    report(best)
    print("BEST_JSON:" + json.dumps({
        "cfg": best["_cfg"],
        "pool": best["pool"], "train": best["train"], "test": best["test"],
        "pos_coins": best["pos_coins"], "tot_coins": best["tot_coins"],
        "freq_yr": best["freq_yr"], "robust": best["robust"],
    }))


if __name__ == "__main__":
    main()
