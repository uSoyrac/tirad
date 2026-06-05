#!/usr/bin/env python3
"""
EMIR — Gerçek veri çekme + 3ay/4H backtest + $100 ORP (GitHub Actions için).

Bu script GitHub Actions runner'ında (gerçek internetli) çalışacak şekilde tasarlandı.
Strateji ve ORP motoru için repodaki MEVCUT kodu yeniden kullanır
(uyg/src/real_backtest_3m.py + dynamic_optimizer.run_orp_dynamic) — uydurma yok.

Çoklu-borsa fallback: Binance US-IP'den 451 yerse Bybit, sonra OKX denenir.
Hiçbir API KEY gerekmez (hepsi public market-data ucu).

Çıktı: emir/results_real.md (CI bunu repoya geri commit eder).
"""
import os
import sys
import time
import argparse
import datetime as dt
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "uyg", "src")
sys.path.insert(0, SRC)

# Mevcut gerçek strateji + ORP motoru
import real_backtest_3m as engine  # add_indicators, find_signals, ORP_PARAMS
from dynamic_optimizer import run_orp_dynamic

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results_real.md")


# ─────────────────────────── ÇOKLU-BORSA FETCH (anahtarsız) ───────────────────────────
def _norm(df):
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    df = df.sort_values("ts").reset_index(drop=True)
    return df[["ts", "open", "high", "low", "close", "volume"]]


def fetch_binance(sym, months):
    import requests
    end = int(time.time()*1000)
    start = end - int(months*30*24*3600*1000)
    out, cur = [], start
    for host in ["https://api.binance.com", "https://data-api.binance.vision"]:
        out, cur = [], start
        ok = True
        while cur < end:
            try:
                r = requests.get(f"{host}/api/v3/klines",
                                 params={"symbol": sym, "interval": "4h",
                                         "startTime": cur, "limit": 1000}, timeout=15)
                if r.status_code != 200:
                    ok = False; break
                data = r.json()
            except Exception:
                ok = False; break
            if not data:
                break
            out.extend(data)
            cur = data[-1][0] + 1
            if len(data) < 1000:
                break
            time.sleep(0.2)
        if ok and out:
            df = pd.DataFrame(out, columns=["ts","open","high","low","close","volume",
                                            "ct","qv","n","tb","tq","ig"])
            df["ts"] = pd.to_datetime(df["ts"], unit="ms")
            return _norm(df)
    raise RuntimeError("binance fail")


def fetch_bybit(sym, months):
    import requests
    end = int(time.time()*1000)
    start = end - int(months*30*24*3600*1000)
    rows, cur = [], end
    # bybit newest-first, paginate backwards with 'end'
    while True:
        r = requests.get("https://api.bybit.com/v5/market/kline",
                         params={"category": "linear", "symbol": sym,
                                 "interval": "240", "end": cur, "limit": 1000}, timeout=15)
        if r.status_code != 200:
            raise RuntimeError("bybit http")
        lst = r.json().get("result", {}).get("list", [])
        if not lst:
            break
        rows.extend(lst)
        oldest = int(lst[-1][0])
        if oldest <= start or len(lst) < 1000:
            break
        cur = oldest - 1
        time.sleep(0.2)
    if not rows:
        raise RuntimeError("bybit empty")
    df = pd.DataFrame(rows, columns=["ts","open","high","low","close","volume","turnover"])
    df["ts"] = pd.to_datetime(df["ts"].astype(np.int64), unit="ms")
    df = df[df["ts"] >= pd.to_datetime(start, unit="ms")]
    return _norm(df)


def fetch_okx(sym, months):
    import requests
    inst = sym.replace("USDT", "-USDT")
    end = int(time.time()*1000)
    start = end - int(months*30*24*3600*1000)
    rows, after = [], end
    while True:
        r = requests.get("https://www.okx.com/api/v5/market/history-candles",
                         params={"instId": inst, "bar": "4H", "after": after, "limit": 100},
                         timeout=15)
        if r.status_code != 200:
            raise RuntimeError("okx http")
        data = r.json().get("data", [])
        if not data:
            break
        rows.extend(data)
        oldest = int(data[-1][0])
        if oldest <= start or len(data) < 100:
            break
        after = oldest
        time.sleep(0.2)
    if not rows:
        raise RuntimeError("okx empty")
    df = pd.DataFrame([row[:6] for row in rows],
                      columns=["ts","open","high","low","close","volume"])
    df["ts"] = pd.to_datetime(df["ts"].astype(np.int64), unit="ms")
    df = df[df["ts"] >= pd.to_datetime(start, unit="ms")]
    return _norm(df)


def fetch_any(sym, months):
    errs = []
    for name, fn in [("binance", fetch_binance), ("bybit", fetch_bybit), ("okx", fetch_okx)]:
        try:
            df = fn(sym, months)
            if len(df) > 60:
                return df, name
        except Exception as e:
            errs.append(f"{name}:{e}")
    raise RuntimeError("tüm borsalar başarısız -> " + " | ".join(errs))


# ─────────────────────────── ÇALIŞTIR + RAPOR ───────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=float, default=3.0)
    args = ap.parse_args()

    lines = []
    def log(s=""):
        print(s); lines.append(s)

    log(f"# EMIR — Gerçek Veri Backtest Sonuçları")
    log(f"_Üretim: {dt.datetime.utcnow().isoformat()}Z (GitHub Actions, canlı internet)_")
    log(f"_Periyot: son {args.months:.0f} ay · 4H · Coinler: {', '.join(COINS)}_\n")

    all_trades, sources = [], {}
    for i, sym in enumerate(COINS):
        try:
            df, src = fetch_any(sym, args.months)
        except Exception as e:
            log(f"- **{sym}**: VERİ ÇEKİLEMEDİ — {e}")
            continue
        df = engine.add_indicators(df)
        sigs = engine.find_signals(df)
        sources[sym] = src
        log(f"- **{sym}** ({src}): {len(df)} mum, {len(sigs)} dolan işlem")
        all_trades.extend(sigs)

    if not all_trades:
        log("\n## ❌ Hiç işlem üretilmedi (veri yok ya da sinyal yok).")
        _write(lines); return

    all_trades = sorted(all_trades, key=lambda t: t["ts"])
    r = np.array([t["r_mult"] for t in all_trades])
    wins = r > 0
    n = len(all_trades)
    tp = sum(1 for t in all_trades if t["outcome"] == "TP")
    sl = sum(1 for t in all_trades if t["outcome"] == "SL")
    to = sum(1 for t in all_trades if t["outcome"] == "TIMEOUT")
    mcl = cur = 0
    for x in r:
        cur = cur+1 if x <= 0 else 0
        mcl = max(mcl, cur)

    log("\n## 📊 Özet")
    log(f"| Metrik | Değer |")
    log(f"|---|---|")
    log(f"| Toplam dolan işlem | {n} |")
    log(f"| TP / SL / Timeout | {tp} / {sl} / {to} |")
    log(f"| **Win Rate (net, fee'li)** | **%{100*wins.mean():.1f}** |")
    log(f"| Ortalama R / işlem | {r.mean():+.3f} R |")
    log(f"| Toplam R | {r.sum():+.2f} R |")
    log(f"| Max ardışık kayıp | {mcl} |")

    res = run_orp_dynamic([{"r_mult": t["r_mult"], "sl_pct": t["sl_pct"]} for t in all_trades],
                          engine.ORP_PARAMS)
    eq = 100.0
    for t in all_trades:
        eq += eq*0.04*t["r_mult"]
        if eq <= 1: eq = 0; break

    log("\n## 💵 $100 Kasa Sonucu")
    log(f"| Yöntem | 3 ay sonra | Büyüme | Max DD |")
    log(f"|---|---|---|---|")
    log(f"| **ORP** (%4 base, %20 cap, %10 cycle) | **${res['final_eq']:,.2f}** | %{((res['final_eq']/100)-1)*100:,.1f} | %{res['max_drawdown']:.1f} |")
    log(f"| Sabit %4 risk (ORP'siz) | ${eq:,.2f} | %{(eq/100-1)*100:,.1f} | — |")

    log("\n## 🔎 Dürüstlük Notu")
    log("- Veri **gerçek** (canlı borsa), komisyon+slippage **modellendi**.")
    log("- Strateji, AGENT.md kurallarının temiz uygulamasıdır; `score_slice_v2` "
        "ile birebir değildir (clean-room baseline).")
    if wins.mean() < 0.5 or r.mean() <= 0:
        log("- ⚠️ **Net beklenti pozitif değil** — sinyal kalitesi/komisyon gözden geçirilmeli.")
    _write(lines)


def _write(lines):
    with open(RESULTS, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n[yazıldı] {RESULTS}")


if __name__ == "__main__":
    main()
