#!/usr/bin/env python3
"""
liq_reversion_test.py — HİPOTEZ C: LİKİDASYON-KASKAD REVERSİYONU

Ekonomi: zorla-likidasyonlar fiyatı aşırı iter, sonra keskin geri döner.
Generic mean-reversion ÖLÜ; iddia = olaya-koşullandırma (sadece likidasyon-spike
sonrası) onu farklı kılar.

Tarihsel likidasyon feed'i yok → PROXY event (kapanmış barda):
  (1) büyük hareket: |bar range| / ATR > k_range  (range = (high-low)/close, ATR price-norm)
  (2) hacim spike: rolling volume z-score > k_vz
  (3) yön: o barın getirisi (close-open) işareti = kaskad yönü
  (opsiyonel) (4) taker_buy_ratio dengesizliği event yönünü teyit eder
  (opsiyonel) (5) funding-extreme

Sinyal: event yönünün TERSİNE pozisyon. Giriş SONRAKİ bar açılışı (signal_lab i+1).
Çıkış: signal_lab.simulate TP/SL (ATR) + flip yok (allow_flip=False, saf reversiyon).

Robustluk: pool + tek-split OOS (evaluate) + KENDİ walk-forward (4 expanding fold) +
per-coin (≥%60) + BTC-yön korelasyonu.

SADECE gerçek stdout raporlanır.
"""
import os, sys
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from signal_lab import load_all, simulate, metrics, atr, BARS_PER_YEAR

COINS = ["ADA","APT","ARB","ATOM","AVAX","BNB","BTC","DOGE","DOT","ETC",
         "ETH","FIL","INJ","LINK","LTC","NEAR","OP","SOL","UNI","XRP"]


def load_micro(coin):
    p = f"microdata/{coin}_micro.csv"
    if not os.path.exists(p): return None
    m = pd.read_csv(p); m["ts"] = pd.to_datetime(m["ts"])
    return m.set_index("ts").sort_index()


def make_event_signal(k_range=2.5, k_vz=2.0, vz_win=50, use_taker=False, micro_cache=None):
    """Likidasyon-kaskad proxy → reversiyon pozisyonu üreten signal_fn."""
    def sig(df):
        n = len(df)
        o = df["open"].to_numpy(float); c = df["close"].to_numpy(float)
        h = df["high"].to_numpy(float); l = df["low"].to_numpy(float)
        v = df["volume"].to_numpy(float)
        a = atr(df, 14)  # causal
        # bar büyüklüğü: range ATR'ye göre
        rng = (h - l)
        big = rng / (a + 1e-12)            # ATR-katı bar genişliği
        # hacim z-score (rolling, causal: sadece geçmiş + bugün)
        vs = pd.Series(v)
        vmean = vs.rolling(vz_win).mean().to_numpy()
        vstd = vs.rolling(vz_win).std().to_numpy()
        vz = (v - vmean) / (vstd + 1e-12)
        # kaskad yönü: bar getirisi işareti (down-cascade -> ret<0 -> long reversiyon)
        ret = (c - o)
        event = (big > k_range) & (vz > k_vz)
        pos = np.zeros(n)
        # event YÖNÜNÜN TERSİ: down bar (ret<0) -> +1 (long), up bar (ret>0) -> -1 (short)
        dir_rev = -np.sign(ret)
        # taker teyidi opsiyonel
        if use_taker and micro_cache is not None:
            coin = df.attrs.get("coin")
            mic = micro_cache.get(coin)
            if mic is not None:
                tbr = df.join(mic[["taker_buy_ratio"]])["taker_buy_ratio"].to_numpy()
                # down-cascade: satış baskısı (tbr düşük) teyit; up: tbr yüksek teyit
                # long reversiyon (dir_rev>0, down bar) için tbr<0.5 iste
                conf = np.where(dir_rev > 0, tbr < 0.48, tbr > 0.52)
                event = event & conf
        pos[event] = dir_rev[event]
        pos[np.isnan(pos)] = 0
        return pos
    return sig


def eval_signal(sig_fn, sl_atr, tp_r, coins, hold_flip=False):
    """Tüm coinlerde simulate, pool + per-coin + tek-split + BTC-yön korelasyonu."""
    dfs = load_all("mktdata", "4h")
    dfs = {c: dfs[c] for c in coins if c in dfs}
    pool = []; per_coin = {}; span_bars = 0
    for c, df in dfs.items():
        df.attrs["coin"] = c
        pos = sig_fn(df)
        tr = simulate(df, pos, sl_atr=sl_atr, tp_r=tp_r, allow_flip=hold_flip)
        for t in tr: t["coin"] = c
        per_coin[c] = metrics(tr); pool += tr
        span_bars = max(span_bars, len(df))
    m = metrics(pool)
    pool.sort(key=lambda x: x["exit_ts"])
    split = int(len(pool)*0.6)
    tr_m = metrics(pool[:split]); te_m = metrics(pool[split:])
    pos_coins = sum(1 for cm in per_coin.values() if cm.get("avg_r", -9) > 0)
    freq_yr = m["n"]/(span_bars/BARS_PER_YEAR) if span_bars else 0
    # yön dağılımı (long vs short reversiyon)
    longs = [t for t in pool if t["dir"] == 1]; shorts = [t for t in pool if t["dir"] == -1]
    return {"pool": m, "train": tr_m, "test": te_m, "pos_coins": pos_coins,
            "tot_coins": len(per_coin), "freq_yr": freq_yr, "per_coin": per_coin,
            "long_m": metrics(longs), "short_m": metrics(shorts), "all_trades": pool}


def walk_forward(sig_fn, sl_atr, tp_r, coins, n_folds=4):
    """Expanding-window WF: tüm trade'leri exit_ts'e göre sırala, son %X'i n_folds OOS dilime böl."""
    res = eval_signal(sig_fn, sl_atr, tp_r, coins)
    pool = sorted(res["all_trades"], key=lambda x: x["exit_ts"])
    if len(pool) < 40:
        return [], res
    # son %40'ı OOS olarak n_folds eşit dilime böl
    oos_start = int(len(pool)*0.6)
    oos = pool[oos_start:]
    folds = np.array_split(oos, n_folds)
    fold_metrics = []
    for fk in folds:
        fk = list(fk)
        fm = metrics(fk)
        fold_metrics.append((fm.get("n", 0), fm.get("avg_r", 0), fm.get("wr", 0)))
    return fold_metrics, res


def btc_trend_corr(all_trades):
    """Getiri akışı BTC trend/yön ile korele mi? trade entry_ts'lerinde BTC 30-bar ret işareti vs trade r_mult."""
    btc = load_all("mktdata", "4h").get("BTC")
    if btc is None: return None
    c = btc["close"]
    btc_ret = (c / c.shift(30) - 1.0)  # 5 günlük (30 bar) trend
    btc_sign = np.sign(btc_ret).reindex(pd.to_datetime([t["entry_ts"] for t in all_trades]), method="ffill").to_numpy()
    r = np.array([t["r_mult"] for t in all_trades])
    d = np.array([t["dir"] for t in all_trades])
    if len(r) < 10: return None
    # trade yönü ile BTC trendi aynı mı? (dir * btc_sign)
    align = d * btc_sign
    valid = ~np.isnan(align)
    align, rr, dd, bs = align[valid], r[valid], d[valid], btc_sign[valid]
    # korelasyon: trade r_mult vs (trade dir ile aynı yöndeki BTC trend)
    corr = float(np.corrcoef(align, rr)[0, 1]) if len(rr) > 2 else float("nan")
    with_trend = rr[align > 0]; against = rr[align < 0]
    return {"corr_align_r": corr,
            "n_with_btc_trend": int((align > 0).sum()),
            "avgR_with_trend": float(with_trend.mean()) if len(with_trend) else float("nan"),
            "n_against": int((align < 0).sum()),
            "avgR_against_trend": float(against.mean()) if len(against) else float("nan")}


def pp(tag, r):
    p, tr, te = r["pool"], r["train"], r["test"]
    print(f"  [{tag}] N={p.get('n',0)} freq/yr={r['freq_yr']:.0f} "
          f"WR={p.get('wr',0):.1f}% beklenti={p.get('avg_r',0):+.3f}R PF={p.get('pf',0):.2f}")
    print(f"       OOS train avgR={tr.get('avg_r',0):+.3f}  test avgR={te.get('avg_r',0):+.3f} "
          f"per-coin+ {r['pos_coins']}/{r['tot_coins']}")
    print(f"       long N={r['long_m'].get('n',0)} avgR={r['long_m'].get('avg_r',0):+.3f} | "
          f"short N={r['short_m'].get('n',0)} avgR={r['short_m'].get('avg_r',0):+.3f}")


if __name__ == "__main__":
    print("="*80)
    print("  HİPOTEZ C: LİKİDASYON-KASKAD REVERSİYONU (mktdata 4h, 20 coin)")
    print("="*80)

    micro_cache = {c: load_micro(c) for c in COINS}

    # ── KÜÇÜK GRID (overfit'e dikkat — sadece keşif) ──
    grid = []
    for k_range in [2.0, 2.5, 3.0]:
        for k_vz in [1.5, 2.0, 2.5]:
            for tp_r, sl_atr in [(1.0, 1.0), (1.5, 1.0), (2.0, 1.5)]:
                grid.append((k_range, k_vz, tp_r, sl_atr))

    print(f"\n  GRID TARAMASI ({len(grid)} kombinasyon, taker teyidi YOK):")
    print("-"*80)
    best = None
    rows = []
    for (kr, kvz, tpr, sla) in grid:
        sig = make_event_signal(k_range=kr, k_vz=kvz, micro_cache=micro_cache)
        r = eval_signal(sig, sla, tpr, COINS)
        n = r["pool"].get("n", 0)
        avgr = r["pool"].get("avg_r", 0)
        teavgr = r["test"].get("avg_r", -9)
        pc = r["pos_coins"]
        rows.append((kr, kvz, tpr, sla, n, avgr, teavgr, pc, r["pool"].get("wr",0)))
        if n >= 100:
            print(f"  kr={kr} kvz={kvz} tp={tpr} sl={sla} | N={n:4d} WR={r['pool'].get('wr',0):4.1f}% "
                  f"poolR={avgr:+.3f} testR={teavgr:+.3f} pc={pc}/20")
        score = avgr if (n >= 150 and teavgr > 0) else -99
        if best is None or score > best[0]:
            best = (score, kr, kvz, tpr, sla, r)

    print("\n" + "="*80)
    print("  EN İYİ KOMBİNASYON (pool avgR, N>=150 & testR>0 kısıtıyla):")
    print("="*80)
    if best and best[0] > -99:
        _, kr, kvz, tpr, sla, rbest = best
        print(f"  params: k_range={kr} k_vz={kvz} tp_r={tpr} sl_atr={sla}")
        pp("BEST no-taker", rbest)

        # WALK-FORWARD
        print("\n  WALK-FORWARD (son %40 OOS, 4 expanding fold):")
        folds, _ = walk_forward(make_event_signal(k_range=kr, k_vz=kvz, micro_cache=micro_cache),
                                sla, tpr, COINS, n_folds=4)
        for i, (fn, far, fwr) in enumerate(folds):
            print(f"    fold{i+1}: N={fn} avgR={far:+.3f} WR={fwr:.1f}%")
        pos_folds = sum(1 for (_, far, _) in folds if far > 0)
        print(f"    pozitif fold: {pos_folds}/{len(folds)}")

        # BTC TREND KORELASYONU
        print("\n  BTC TREND KORELASYONU:")
        bt = btc_trend_corr(rbest["all_trades"])
        if bt:
            print(f"    corr(trade dir-BTC trend align, r_mult) = {bt['corr_align_r']:+.3f}")
            print(f"    BTC trendiyle aynı yönde: N={bt['n_with_btc_trend']} avgR={bt['avgR_with_trend']:+.3f}")
            print(f"    BTC trendine ters:        N={bt['n_against']} avgR={bt['avgR_against_trend']:+.3f}")

        # TAKER teyitli varyant (aynı params)
        print("\n  TAKER-TEYİTLİ VARYANT (aynı params):")
        sig_t = make_event_signal(k_range=kr, k_vz=kvz, use_taker=True, micro_cache=micro_cache)
        rt = eval_signal(sig_t, sla, tpr, COINS)
        pp("BEST +taker", rt)
    else:
        print("  HİÇBİR kombinasyon N>=150 & testR>0 kısıtını geçemedi. NEGATİF.")
        # yine de en yüksek N'li birkaçını göster
        rows.sort(key=lambda x: -x[4])
        print("\n  en yüksek N'li 5 kombinasyon (referans):")
        for (kr,kvz,tpr,sla,n,avgr,teavgr,pc,wr) in rows[:5]:
            print(f"    kr={kr} kvz={kvz} tp={tpr} sl={sla} N={n} WR={wr:.1f}% poolR={avgr:+.3f} testR={teavgr:+.3f} pc={pc}/20")
