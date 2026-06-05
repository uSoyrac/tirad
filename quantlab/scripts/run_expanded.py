"""Expanded-universe robustness test (survivorship proxy): does the combo edge hold on a
BROAD, non-cherry-picked crypto universe (~50-60 liquid coins) instead of the hand-picked 20?

Fetches 4h OHLCV + funding history via ccxt for the top liquid perps with enough history,
caches them, then re-runs the crypto combo (Top-3 momentum + funding-positioning) and
reports OOS 2025-26 Sharpe vs the 20-coin baseline + random-subset robustness.

Honest limit: still survivor-biased (all coins alive today; truly-delisted ones are gone
from the API) — but a much broader set bounds the SELECTION bias. Usage:
    python scripts/run_expanded.py [N]
"""

from __future__ import annotations

import sys
import time
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from quantlab.config import load_config  # noqa: E402
from quantlab.data import cache  # noqa: E402
from quantlab.backtest import combine, metrics  # noqa: E402
from quantlab.backtest.portfolio import run_portfolio  # noqa: E402
from quantlab.backtest.carry import run_carry  # noqa: E402
from quantlab import orchestrator  # noqa: E402

CUT = pd.Timestamp("2025-01-01")
START = pd.Timestamp("2023-01-01")          # enough for train (2023-24) + OOS (2025-26)
CACHE = Path(__file__).resolve().parents[1] / "data_cache_exp"
CACHE.mkdir(exist_ok=True)


def _ex():
    import ccxt
    return ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "future"}})


def pick_universe(ex, n):
    """Top-n USDT perps by 24h quote volume (active, non-leveraged-token)."""
    m = ex.load_markets()
    tk = ex.fetch_tickers()
    cand = []
    for s, v in m.items():
        if not (v.get("swap") and v.get("quote") == "USDT" and v.get("active")):
            continue
        base = v.get("base", "")
        if base.endswith(("UP", "DOWN", "BULL", "BEAR")):
            continue
        qv = (tk.get(s) or {}).get("quoteVolume") or 0
        cand.append((base, s, qv))
    cand.sort(key=lambda x: x[2], reverse=True)
    return cand[:n]


def fetch_ohlcv(ex, symbol):
    step = 14_400_000
    since = int(START.timestamp() * 1000)
    rows, cur = [], since
    while True:
        b = ex.fetch_ohlcv(symbol, "4h", since=cur, limit=1000)
        if not b:
            break
        rows.extend(b)
        cur = b[-1][0] + step
        if len(b) < 1000:
            break
        time.sleep(ex.rateLimit / 1000)
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"]).drop_duplicates("ts")
    df["ts"] = pd.to_datetime(df["ts"], unit="ms")
    return df.set_index("ts")[["open", "high", "low", "close", "volume"]].astype(float)


def fetch_funding(ex, symbol):
    since = int(START.timestamp() * 1000)
    rows, cur = [], since
    while True:
        try:
            b = ex.fetch_funding_rate_history(symbol, since=cur, limit=1000)
        except Exception:
            break
        if not b:
            break
        rows.extend(b)
        nxt = b[-1]["timestamp"] + 1
        if nxt <= cur:
            break
        cur = nxt
        if len(b) < 1000:
            break
        time.sleep(ex.rateLimit / 1000)
    if not rows:
        return None
    s = pd.Series({pd.to_datetime(r["timestamp"], unit="ms"): float(r["fundingRate"]) for r in rows})
    return s[~s.index.duplicated()].sort_index()


def load_or_fetch(ex, base, symbol):
    pq = CACHE / f"{base}_4h.parquet"
    fp = CACHE / f"{base}_funding.parquet"
    if pq.exists() and fp.exists():
        return pd.read_parquet(pq), pd.read_parquet(fp)["funding"]
    df = fetch_ohlcv(ex, symbol)
    fu = fetch_funding(ex, symbol)
    if df is None or fu is None or len(df) < 2000:
        return None, None
    df.to_parquet(pq)
    fu.rename("funding").to_frame().to_parquet(fp)
    return df, fu


def main(n=60):
    cfg = load_config(str(Path(__file__).resolve().parents[1] / "config" / "default.yaml"))
    ex = _ex()
    uni = pick_universe(ex, n + 25)  # extra to survive history filter
    print(f"Aday {len(uni)} coin, hedef {n}. Veri çekiliyor (4h+funding)...")
    frames, targets, momentum, fundings = {}, {}, {}, {}
    for base, sym, qv in uni:
        if len(frames) >= n:
            break
        df, fu = load_or_fetch(ex, base, sym)
        if df is None:
            continue
        hd = cache.resample(cache._validate(df), "1d")
        frames[base] = cache._validate(df)
        targets[base] = orchestrator.build_target(frames[base], cfg, hd)
        momentum[base] = frames[base]["close"].pct_change(60)
        fundings[base] = fu
        if len(frames) % 10 == 0:
            print(f"  {len(frames)} coin hazır...")
    print(f"Toplam {len(frames)} coin yüklendi. Combo çalıştırılıyor...")

    def combo_oos(fr, tg, mo, fn):
        trend = combine.equity_to_daily_returns(run_portfolio(fr, tg, mo, cfg, top_k=3).equity)
        carry = run_carry(fr, fn, cfg, lookback_days=7, n_side=3, rebalance_days=1).daily_returns
        rt, rc = combine.align(trend, carry)
        wt, wc = combine.inverse_vol_weights(rt[rt.index < CUT], rc[rc.index < CUT])
        oos = combine.blend(rt[rt.index >= CUT], rc[rc.index >= CUT], wt, wc)
        m = metrics.compute_metrics(combine.equity_from_returns(oos, 10000.0), [], timeframe="1d")
        return m["sharpe"], m["cagr"], m["max_drawdown"]

    sh, cg, md = combo_oos(frames, targets, momentum, fundings)
    # random-subset robustness (20-coin draws from the big universe)
    rng = np.random.default_rng(42)
    keys = list(frames)
    subs = []
    for _ in range(20):
        pick = list(rng.choice(keys, size=min(20, len(keys)), replace=False))
        try:
            s2, _, _ = combo_oos({k: frames[k] for k in pick}, {k: targets[k] for k in pick},
                                 {k: momentum[k] for k in pick}, {k: fundings[k] for k in pick})
            subs.append(s2)
        except Exception:
            pass
    subs = np.array(subs)

    rep = [
        "# Genişletilmiş-evren combo testi (survivorship/selection proxy)", "",
        f"Evren: {len(frames)} likit coin (20 yerine). OOS 2025-26, tüm maliyetler dahil.", "",
        f"- **{len(frames)}-coin combo OOS Sharpe: {sh:.2f}** | CAGR {cg*100:.0f}% | MaxDD {md*100:.0f}%",
        "- 20-coin baseline combo OOS Sharpe: ~1.74 (referans)",
        f"- Random 20-coin alt-evren (büyük evrenden, 20 çekiliş): medyan Sharpe "
        f"{np.median(subs):.2f}, %pozitif {np.mean(subs>0)*100:.0f}%" if len(subs) else "- alt-evren: n/a",
        "", "## Yorum", "",
    ]
    if sh >= 1.2:
        rep.append(f"**Edge GENİŞ evrende DE duruyor (Sharpe {sh:.2f}).** 20-coin kiraz-toplama "
                   "değildi; combo seçim-yanlılığına dayanıklı. (Yine de truly-delisted coinler "
                   "yok → mutlak büyüklük literatür haircut'ı (~%15-22/yıl) ile aşağı düzeltilmeli.)")
    else:
        rep.append(f"**Edge geniş evrende ZAYIFLADI (Sharpe {sh:.2f} vs ~1.74).** 20-coin sonucu "
                   "kısmen seçim-yanlılığıydı; gerçekçi beklenti daha düşük.")
    report = "\n".join(rep)
    print("\n" + report)
    (Path(__file__).resolve().parents[1] / "reports_out" / "expanded.md").write_text(report)
    print("\nSaved -> reports_out/expanded.md")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 60)
