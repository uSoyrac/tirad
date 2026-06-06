#!/usr/bin/env python3
"""
basis_test.py — HİPOTEZ B: BASIS / TERM-STRUCTURE CARRY (delta-nötr roll-yield)
═══════════════════════════════════════════════════════════════════════════════
Ekonomi: Quarterly (dated) futures spot/perp üzerinde contango/backwardation primi
taşır. Vade yaklaştıkça basis 0'a yakınsar → delta-nötr "cash-and-carry":
  contango'da  SHORT quarterly + LONG perp  → yakınsama kârı (yönsüz)
  backwardation'da tersi.
Perp funding (Hipotez A) ≈ basis integrali olduğundan, FARKLI bir kaynak için
DATED quarterly futures'ın spot/perp'e göre primi GEREKLİ. Bu script onu test eder.

VERİ: Binance USDM quarterly (dated) kontrat zinciri ccxt fapiPublicGetKlines ile
çekilebiliyor (expired kontratlar dahil, ~Dec-2022'den bugüne). Perp/spot bacağı
yerel mktdata/{COIN}_USDT_4h.csv (perp 4H). Her ikisi de aynı 4H gridde.

DÜRÜSTLÜK: sadece gerçekten çekilen veriyle. Maliyet net (taker 7bps/taraf, RT).
Leak-free: tüm kararlar kapanmış bar üzerinde; carry pozisyonu bir SONRAKİ barda
açılır. Yönsüzlük testi: günlük getiri akışının BTC günlük getirisiyle korelasyonu.
"""
import os, json, time, calendar, datetime as dt
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

import ccxt

FEE_PER_SIDE = 0.0007          # taker ~7bps/taraf (brief konvansiyonu)
CACHE_DIR = "basis_cache"
COINS = ["BTC", "ETH"]         # quarterly dated mevcut olan likit majörler

# ── 1) quarterly kontrat zinciri çek (cache'li) ──
def last_friday(y, m):
    cal = calendar.Calendar()
    fr = [d for d in cal.itermonthdates(y, m) if d.month == m and d.weekday() == 4]
    return fr[-1]

def contract_ids(coin):
    """coin için (expiry_date, binance_id) listesi — 2022Q4..2026Q3."""
    out = []
    for y in [2022, 2023, 2024, 2025, 2026]:
        for m in [3, 6, 9, 12]:
            d = last_friday(y, m)
            out.append((dt.datetime(d.year, d.month, d.day),
                        f"{coin}USDT_{y%100:02d}{m:02d}{d.day:02d}"))
    return out

def fetch_contract(ex, cid):
    """Tüm 4H klines'ı startTime ile paginate ederek çek. -> DataFrame(ts,close) veya None."""
    rows = []
    start = None
    while True:
        p = {"symbol": cid, "interval": "4h", "limit": 1500}
        if start is not None:
            p["startTime"] = start
        try:
            o = ex.fapiPublicGetKlines(p)
        except Exception as e:
            if not rows:
                return None
            break
        if not o:
            break
        rows += o
        last_ts = int(o[-1][0])
        nxt = last_ts + 4 * 3600 * 1000
        if len(o) < 1500:
            break
        if start is not None and nxt <= start:
            break
        start = nxt
        time.sleep(0.12)
    if not rows:
        return None
    seen = {}
    for r in rows:
        seen[int(r[0])] = float(r[4])  # close
    ts = sorted(seen)
    return pd.DataFrame({"ts": pd.to_datetime(ts, unit="ms", utc=True).tz_localize(None),
                         "qclose": [seen[t] for t in ts]})

def build_quarterly_panel(coin, ex):
    """Her 4H bar için FRONT (en yakın vadesi gelmemiş) quarterly kapanışı + expiry.
    Cache: basis_cache/{coin}_quarterly_front.csv"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = f"{CACHE_DIR}/{coin}_quarterly_front.csv"
    if os.path.exists(cache):
        d = pd.read_csv(cache, parse_dates=["ts", "expiry"])
        return d
    chain = []
    for expiry, cid in contract_ids(coin):
        df = fetch_contract(ex, cid)
        if df is None or len(df) == 0:
            continue
        df = df[df["ts"] <= expiry]              # vade sonrası satır gelmesin
        df["expiry"] = expiry
        df["cid"] = cid
        chain.append(df)
        print(f"  {cid}: {len(df)} bar  {df['ts'].min()} -> {df['ts'].max()}")
    if not chain:
        return None
    allc = pd.concat(chain, ignore_index=True)
    # FRONT seçimi: her ts'te, ts < expiry olan ve EN YAKIN expiry (front month)
    allc = allc[allc["ts"] < allc["expiry"]]
    allc["dte_days"] = (allc["expiry"] - allc["ts"]).dt.total_seconds() / 86400.0
    allc = allc.sort_values(["ts", "dte_days"])
    front = allc.groupby("ts", as_index=False).first()  # en küçük dte = front
    front = front[["ts", "qclose", "expiry", "dte_days", "cid"]].sort_values("ts").reset_index(drop=True)
    front.to_csv(cache, index=False)
    return front

# ── 2) yerel perp bacağı ──
def load_perp(coin):
    f = f"mktdata/{coin}_USDT_4h.csv"
    d = pd.read_csv(f, parse_dates=["ts"])
    return d[["ts", "open", "close"]].rename(columns={"close": "pclose", "open": "popen"})

# ── 3) basis + carry simülasyonu ──
def run_coin(coin, ex, entry_bps_ann=5.0, verbose=True):
    """
    Delta-nötr cash-and-carry:
      basis_ann = (qclose/pclose - 1) * (365/dte_days)   # yıllıklaştırılmış prim
    Sinyal (kapanmış bar i): |basis_ann| > entry eşiği → carry pozisyonu AÇIK.
      contango (basis>0): short quarterly + long perp.
    Getiri (bar i->i+1, delta-nötr): pozisyonun toplam PnL'i = -(quarterly getirisi)+(perp getirisi)
      = -(q_{i+1}/q_i - 1) + (p_{i+1}/p_i - 1)   [contango: short q, long p]
      backwardation simetrik (işaret ters).
    Leak-free: pozisyon i barında karar, i->i+1 getirisi gerçekleşir (next-bar).
    Maliyet: pozisyon AÇILIŞ ve KAPANIŞINDA 2 bacak × FEE_PER_SIDE (4 taraf toplam round-trip).
      Roll: front kontrat değişince eski 2 bacak kapanır + yeni 2 bacak açılır.

    KRİTİK (ROLL BUG düzeltmesi): front kontrat değiştiği bar'da q[i+1]/q[i]
    FARKLI iki enstrümanın fiyatını karşılaştırır → sahte sıçrama. Bu adımda
    getiri BOOK EDİLMEZ (eski kapatılır, yeni açılır, gap'te PnL yok). Yalnız
    AYNI kontrat içindeki bar->bar getiriler delta-nötr PnL'e girer.
    """
    front = build_quarterly_panel(coin, ex)
    if front is None:
        return None
    perp = load_perp(coin)
    m = pd.merge(front, perp, on="ts", how="inner").sort_values("ts").reset_index(drop=True)
    if len(m) < 100:
        return None

    q = m["qclose"].to_numpy(float)
    p = m["pclose"].to_numpy(float)
    dte = m["dte_days"].to_numpy(float)
    cid = m["cid"].to_numpy()
    ts = m["ts"].to_numpy()

    basis = q / p - 1.0
    basis_ann = basis * (365.0 / np.clip(dte, 0.5, None))

    n = len(m)
    # eşik: entry_bps_ann doğrudan yıllık % cinsinden (ör 5.0 = %5/yıl)
    thr = entry_bps_ann / 100.0
    # POZİSYON: sign her KONTRAT için GİRİŞ barında (causal) sabitlenir; vade boyunca
    # tutulur, expiry'de roll edilir. Sadece |entry basis_ann| > thr ise o kontratta
    # carry açılır (contango→+1: short q+long p, backwardation→-1). Bar-bar flip YOK
    # (bar-bar sign flip churn yaratıp gerçek-olmayan whipsaw maliyeti üretirdi).
    pos = np.zeros(n)
    cur = None; s = 0
    for i in range(n):
        if cid[i] != cur:
            cur = cid[i]
            ba = basis_ann[i]
            s = 1 if ba > thr else (-1 if ba < -thr else 0)
        pos[i] = s
    # leak-free: pos[i] kararı i kapanışında; getiri i->i+1
    qret = q[1:] / q[:-1] - 1.0
    pret = p[1:] / p[:-1] - 1.0
    # contango (pos=+1): short q + long p → leg getirisi ortalaması (eşit notional, 2 bacak)
    #   pnl_notional = (-qret + pret)/2   (her bacak yarım sermaye varsayımı; net delta ~0)
    # backwardation (pos=-1): long q + short p → (+qret - pret)/2
    leg = np.zeros(n)
    leg[:-1] = pos[:-1] * ((-qret + pret) / 2.0)
    # ROLL BUG FIX: i->i+1 adımı kontrat sınırını geçiyorsa (cid[i+1]!=cid[i]) getiri book etme
    cross_next = np.zeros(n, bool)
    cross_next[:-1] = cid[1:] != cid[:-1]
    leg[cross_next] = 0.0
    # maliyet: pozisyon değişiminde (aç/kapa/roll). 1 bacak = FEE_PER_SIDE; /2 → leg ölçeği.
    cost = np.zeros(n)
    for i in range(1, n):
        rolled = (cid[i] != cid[i - 1])
        changed = (pos[i] != pos[i - 1])
        legs = 0
        if rolled and pos[i] != 0 and pos[i - 1] != 0:
            legs = 4                # roll: 2 kapat + 2 aç
        else:
            if pos[i - 1] != 0 and (changed or rolled):
                legs += 2           # eski 2 bacağı kapat
            if pos[i] != 0 and (changed or rolled):
                legs += 2           # yeni 2 bacağı aç
        cost[i] = legs * FEE_PER_SIDE / 2.0
    if pos[0] != 0:
        cost[0] = 2 * FEE_PER_SIDE / 2.0   # ilk açılış
    net = leg - cost

    # metrikler (4H bar → yıllık 2190 bar)
    BPY = 6 * 365
    active = pos != 0
    exposure = active.mean()
    mu = net.mean()
    sd = net.std()
    sharpe = mu / sd * np.sqrt(BPY) if sd > 0 else 0.0
    cum = np.cumprod(1 + net)
    total_ret = cum[-1] - 1
    years = n / BPY
    cagr = cum[-1] ** (1 / years) - 1 if years > 0 and cum[-1] > 0 else float("nan")
    peak = np.maximum.accumulate(cum)
    mdd = ((cum - peak) / peak).min()
    # BTC yön korelasyonu: net getiri akışı vs perp getirisi
    valid = np.abs(net) > 0
    corr_dir = np.corrcoef(net[:-1], pret)[0, 1] if pret.std() > 0 else float("nan")
    # ortalama basis seviyesi
    avg_basis_ann = float(np.nanmean(basis_ann))
    # per-contract pozitiflik (robustluk: contango her vadede yakınsadı mı)
    dfp = pd.DataFrame({"cid": cid, "net": net})
    pc = dfp.groupby("cid")["net"].sum()
    pos_contracts = int((pc > 0).sum()); tot_contracts = int(len(pc))
    # zaman-stabilite: ilk %60 / son %40 ortalama getiri
    split = int(n * 0.6)
    tr_mu = float(net[:split].mean()); te_mu = float(net[split:].mean())

    res = {
        "coin": coin, "n_bars": int(n),
        "span": f"{pd.Timestamp(ts[0])} -> {pd.Timestamp(ts[-1])}",
        "avg_basis_ann_pct": round(avg_basis_ann * 100, 3),
        "exposure": round(float(exposure), 3),
        "entry_thr_ann_pct": entry_bps_ann,
        "sharpe": round(float(sharpe), 3),
        "cagr_pct": round(float(cagr) * 100, 3) if cagr == cagr else None,
        "total_ret_pct": round(float(total_ret) * 100, 3),
        "mdd_pct": round(float(mdd) * 100, 3),
        "corr_to_btc_dir": round(float(corr_dir), 4) if corr_dir == corr_dir else None,
        "net_mu_per_bar_bps": round(float(mu) * 1e4, 4),
        "pos_contracts": f"{pos_contracts}/{tot_contracts}",
        "oos_train_mu_bps": round(tr_mu * 1e4, 4),
        "oos_test_mu_bps": round(te_mu * 1e4, 4),
    }
    if verbose:
        print(json.dumps(res, indent=2, default=str))
    return res, net, pret, m


def main():
    ex = ccxt.binance({"options": {"defaultType": "future"}})
    all_res = []
    streams = {}
    for coin in COINS:
        print(f"\n===== {coin} =====")
        out = run_coin(coin, ex, entry_bps_ann=5.0)
        if out is None:
            print(f"  {coin}: yetersiz veri")
            continue
        res, net, pret, m = out
        all_res.append(res)
        streams[coin] = (net, pret)

    # threshold duyarlılığı (BTC) + 0 eşik (her zaman carry)
    print("\n===== BTC threshold duyarlılık =====")
    for thr in [0.0, 2.0, 5.0, 10.0]:
        out = run_coin("BTC", ex, entry_bps_ann=thr, verbose=False)
        if out:
            r = out[0]
            print(f"  thr={thr:>5.1f}%/yr  Sharpe={r['sharpe']:+.2f}  CAGR={r['cagr_pct']}%  "
                  f"MDD={r['mdd_pct']}%  expo={r['exposure']}  corrBTC={r['corr_to_btc_dir']}")

    print("\n===== ÖZET =====")
    for r in all_res:
        print(f"  {r['coin']}: avgBasis={r['avg_basis_ann_pct']}%/yr  Sharpe={r['sharpe']}  "
              f"CAGR={r['cagr_pct']}%  MDD={r['mdd_pct']}%  expo={r['exposure']}  "
              f"corrBTCdir={r['corr_to_btc_dir']}  posContracts={r['pos_contracts']}  "
              f"OOS(tr/te)bps={r['oos_train_mu_bps']}/{r['oos_test_mu_bps']}  N={r['n_bars']}")
    return all_res


if __name__ == "__main__":
    main()
