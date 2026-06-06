import json
import numpy as np
from signal_lab import evaluate, donchian, atr, adx

# Donchian/turtle breakout: kapanış üst bandı kırarsa LONG, alt bandı kırarsa SHORT.
# Whipsaw azaltmak için ATR momentum / ADX trend onayı eklenir.
# CAUSAL: i barında donchian bandı i-1'e kadarki pencereden hesaplanır (rolling max/min
# i'yi de içerir, bu yüzden "önceki bar bandını" kullanmak için n+1 kaydırıyoruz değil;
# donchian(df,n) i-inci değer [i-n+1..i] penceresi -> i'deki kapanış bu bandın TEPESİ ise
# trivially eşit olur. Look-ahead'i önlemek için önceki barın bandını (h[i-1], l[i-1])
# referans alıp i kapanışının onu aşmasına bakarız.


def make_sig(n, mode="atr", atr_k=0.0, adx_min=0.0):
    def sig(df):
        c = df["close"].to_numpy(float)
        h, l = donchian(df, n)          # h[i],l[i] = [i-n+1..i] penceresi
        a = atr(df, 14)
        adv = None
        if mode == "adx":
            adv = adx(df, 14)[0]
        pos = np.zeros(len(df))
        for i in range(max(n + 2, 200), len(df)):
            # önceki barın bandı (causal referans, i'yi içermez)
            up_prev = h[i - 1]
            dn_prev = l[i - 1]
            long_brk = c[i] > up_prev
            short_brk = c[i] < dn_prev
            if mode == "atr":
                # kırılım gücü: bandı en az atr_k*ATR kadar aşmalı
                if long_brk and (c[i] - up_prev) >= atr_k * a[i]:
                    pos[i] = 1
                elif short_brk and (dn_prev - c[i]) >= atr_k * a[i]:
                    pos[i] = -1
            elif mode == "adx":
                if adv[i] >= adx_min:
                    if long_brk:
                        pos[i] = 1
                    elif short_brk:
                        pos[i] = -1
        return pos
    return sig


CONFIGS = [
    # (n, mode, atr_k, adx_min, sl_atr, tp_r, label)
    (20, "atr", 0.0, 0.0, 1.5, 2.0, "n20 raw"),
    (20, "atr", 0.5, 0.0, 1.5, 2.0, "n20 atr0.5"),
    (40, "atr", 0.25, 0.0, 2.0, 2.5, "n40 atr0.25"),
    (55, "atr", 0.0, 0.0, 2.0, 3.0, "n55 raw tp3"),
    (40, "adx", 0.0, 20.0, 2.0, 2.5, "n40 adx20"),
    (55, "adx", 0.0, 25.0, 2.0, 3.0, "n55 adx25"),
]


def main():
    results = []
    for n, mode, atr_k, adx_min, sl_atr, tp_r, label in CONFIGS:
        sig = make_sig(n, mode, atr_k, adx_min)
        res = evaluate(sig, data="mktdata", tf="4h", sl_atr=sl_atr, tp_r=tp_r, label=label)
        res["_cfg"] = dict(n=n, mode=mode, atr_k=atr_k, adx_min=adx_min, sl_atr=sl_atr, tp_r=tp_r)
        p = res["pool"]
        print(f"[{label}] N={p['n']} freq={res['freq_yr']:.0f} WR={p['wr']:.1f}% "
              f"avgR={p['avg_r']:+.3f} PF={p['pf']:.2f} "
              f"train={res['train'].get('avg_r',0):+.3f} test={res['test'].get('avg_r',0):+.3f} "
              f"pc={res['pos_coins']}/{res['tot_coins']} robust={res['robust']}")
        results.append(res)

    robust = [r for r in results if r["robust"]]
    pool = robust if robust else results
    best = max(pool, key=lambda r: (r["robust"], r["test"].get("avg_r", -9)))
    print("\nBEST:", best["label"], "robust=", best["robust"])
    print(json.dumps({"cfg": best["_cfg"], "pool": best["pool"],
                      "train": best["train"], "test": best["test"],
                      "freq_yr": best["freq_yr"], "pos_coins": best["pos_coins"],
                      "tot_coins": best["tot_coins"], "robust": best["robust"]}))
    return best


if __name__ == "__main__":
    main()
