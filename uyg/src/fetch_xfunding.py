#!/usr/bin/env python3
"""fetch_xfunding.py — Çoklu-borsa (Bybit, OKX) perpetual funding rate geçmişi.

Binance zaten funddata/ altında mevcut, atlanıyor.
Her borsa için: xfunddata/{EXCHANGE}_{COIN}_funding.csv (kolonlar: ts,funding).
Sembol formatı: BTC/USDT:USDT (linear perp, hem Bybit hem OKX).

Pagination notları (gerçek testle doğrulandı, 2026-06-01):
  - Bybit: GERİYE-yön (until ile, now->geçmiş) sayfalama her coin için listeleme
    tarihine kadar tam geçmiş verir. (since=2021 ileri-yön çoğu coinde 0 döndürüyor.)
  - OKX: public funding-history endpoint yalnız son ~3 ay servis eder;
    geriye sayfalama daha derine inemiyor (borsa-tarafı limit). Ne veriyorsa o alınır.
"""
import os, time, ccxt, pandas as pd, warnings, datetime as dt
warnings.filterwarnings("ignore")

OUT = "xfunddata"
COINS = ["BTC","ETH","SOL","BNB","XRP","ADA","AVAX","DOGE","DOT","LINK",
         "LTC","UNI","ATOM","NEAR","APT","ARB","OP","FIL","INJ","ETC"]
SINCE_ISO = "2021-01-01T00:00:00Z"


def fetch_backward(ex, sym, since, limit, max_pages=400):
    """Geriye-yön sayfalama: now'dan başla, 'until' ile geçmişe doğru in.
    since'ten eskisine ulaşınca veya yeni veri gelmeyince dur."""
    rows = []; pages = 0
    until = ex.milliseconds()
    while True:
        b = ex.fetch_funding_rate_history(sym, limit=limit, params={"until": until})
        if not b:
            break
        rows += [(x["timestamp"], x["fundingRate"]) for x in b]
        pages += 1
        oldest = min(x["timestamp"] for x in b)
        if oldest >= until or len(b) < limit or oldest <= since:
            break
        until = oldest - 1
        if pages >= max_pages:
            break
        time.sleep(ex.rateLimit / 1000)
    # since filtresi (istenen başlangıçtan eski barları at)
    rows = [r for r in rows if r[0] >= since]
    return rows


def fetch_paginate(ex, sym, since, limit):
    """ccxt yerleşik paginate:True. OKX gibi borsalar için en derin pencereyi verir."""
    b = ex.fetch_funding_rate_history(sym, since=since, limit=limit, params={"paginate": True})
    return [(x["timestamp"], x["fundingRate"]) for x in b]


def save(rows, exch, coin):
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["ts", "funding"]).dropna()
    df = df.drop_duplicates("ts").sort_values("ts")
    df["ts"] = pd.to_datetime(df["ts"], unit="ms")
    df = df.sort_values("ts").reset_index(drop=True)
    path = f"{OUT}/{exch}_{coin}_funding.csv"
    df.to_csv(path, index=False)
    return df, path


def run_exchange(exch_name, limit, method):
    ex = getattr(ccxt, exch_name)({"enableRateLimit": True, "timeout": 30000})
    try:
        ex.load_markets()
    except Exception as e:
        print(f"[{exch_name}] load_markets ERR {str(e)[:80]}", flush=True)
    since = ex.parse8601(SINCE_ISO)
    results = []; fails = []
    for c in COINS:
        sym = f"{c}/USDT:USDT"
        try:
            if method == "paginate":
                rows = fetch_paginate(ex, sym, since, limit)
            else:
                rows = fetch_backward(ex, sym, since, limit)
        except Exception as e:
            fails.append((exch_name, c, str(e)[:90]))
            print(f"[{exch_name}] {c} SKIP {str(e)[:80]}", flush=True)
            continue
        out = save(rows, exch_name, c)
        if out is None:
            fails.append((exch_name, c, "no rows"))
            print(f"[{exch_name}] {c} boş", flush=True)
            continue
        df, path = out
        d0, d1 = df["ts"].iloc[0].date(), df["ts"].iloc[-1].date()
        results.append((exch_name, c, len(df), str(d0), str(d1), path))
        print(f"[{exch_name}] {c} {len(df)} rows ({d0} -> {d1})", flush=True)
    return results, fails


def main():
    os.makedirs(OUT, exist_ok=True)
    all_res = []; all_fail = []
    # (borsa, limit, method): Bybit geriye-yön; OKX yerleşik paginate (en derin pencere)
    for exch_name, limit, method in [("bybit", 200, "backward"), ("okx", 1000, "paginate")]:
        print(f"==== {exch_name.upper()} ====", flush=True)
        r, f = run_exchange(exch_name, limit, method)
        all_res += r; all_fail += f

    print("\n==== ÖZET TABLOSU ====", flush=True)
    print(f"{'EXCH':<7}{'COIN':<6}{'ROWS':>7}  {'START':<12}{'END':<12}", flush=True)
    for exch, c, n, d0, d1, _ in all_res:
        print(f"{exch:<7}{c:<6}{n:>7}  {d0:<12}{d1:<12}", flush=True)
    print(f"\nBaşarılı: {len(all_res)} borsa×coin | Başarısız: {len(all_fail)}", flush=True)
    if all_fail:
        print("BAŞARISIZLAR:", flush=True)
        for exch, c, why in all_fail:
            print(f"  {exch} {c}: {why}", flush=True)
    print("TAMAM", flush=True)


if __name__ == "__main__":
    main()
