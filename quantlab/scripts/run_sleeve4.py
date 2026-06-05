"""LEVER #1 — hunt a 4th ORTHOGONAL sleeve to lift the cross-asset book above 2.40.

The proven mechanism (H2): adding a low-correlation return stream raises Sharpe AND
cuts drawdown via √N breadth. The 3 existing sleeves are crypto-trend, crypto-funding,
US-momentum. A 4th sleeve only helps if it is genuinely orthogonal to all three.

Two honest candidates, both with realistic costs (no-lookahead: positions lagged 1 day):
  A. MACRO TSMOM — time-series momentum (Moskowitz-Ooi-Pedersen) on macro ETFs
     (gold/silver/bonds/commodities/oil/dollar). The canonical managed-futures
     diversifier; structurally uncorrelated to both crypto and equity momentum.
  B. EQUITY STR — short-term reversal on the US large-cap universe (fade last week's
     winners/losers). Classically NEGATIVELY correlated to momentum, but high turnover.

For each candidate: correlation to the 3 sleeves + the 4-sleeve inverse-vol OOS Sharpe
vs the 3-sleeve 2.40 baseline. Report the bad numbers too.

Usage: python scripts/run_sleeve4.py
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from quantlab.config import load_config  # noqa: E402
from quantlab.data import cache, funding as fundmod  # noqa: E402
from quantlab.backtest import combine  # noqa: E402
from quantlab.backtest.portfolio import run_portfolio  # noqa: E402
from quantlab.backtest.carry import run_carry  # noqa: E402
from quantlab import orchestrator  # noqa: E402

US = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "JPM", "V", "JNJ", "WMT",
      "PG", "XOM", "UNH", "HD", "MA", "BAC", "KO", "PEP", "CVX", "ABBV", "COST", "MRK",
      "AVGO", "PFE", "CSCO", "ADBE", "CRM", "NFLX", "AMD"]
CRYPTO = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LTC", "ATOM", "DOT",
          "LINK", "DOGE", "ETC", "FIL", "INJ", "NEAR", "UNI", "APT", "ARB", "OP"]
# macro ETFs: gold, silver, 20y+7-10y treasuries, broad commodities, oil, natgas, dollar, ag
MACRO = ["GLD", "SLV", "TLT", "IEF", "DBC", "USO", "UNG", "UUP", "DBA"]
CUT = pd.Timestamp("2025-01-01")
MKTDATA = Path("../uyg/src/mktdata")
FUND = Path("../uyg/src/funddata")
PPY = 252
COST = 0.0005  # 5 bps per unit turnover (ETF spreads are tight; equities a touch more)


def _sharpe(r):
    return float(r.mean() / r.std() * np.sqrt(PPY)) if r.std() > 0 else float("nan")


def _stats(r):
    eq = (1 + r).cumprod()
    cagr = eq.iloc[-1] ** (PPY / len(r)) - 1 if len(r) else float("nan")
    mdd = float((eq / eq.cummax() - 1).min()) if len(r) else float("nan")
    return _sharpe(r), cagr, mdd


def _three_sleeves(cfg, root):
    cf, ct, cm, fu = {}, {}, {}, {}
    for s in CRYPTO:
        csv = (root / MKTDATA / f"{s}_USDT_4h.csv").resolve()
        fp = (root / FUND / f"{s}_funding.csv").resolve()
        if not (csv.exists() and fp.exists()):
            continue
        df = cache.load_ohlcv(f"{s}/USDT", "4h", cache_dir=root / cfg.data.cache_dir,
                              start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
        hd = cache.load_ohlcv(f"{s}/USDT", "1d", cache_dir=root / cfg.data.cache_dir,
                              start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
        cf[s], ct[s], cm[s], fu[s] = df, orchestrator.build_target(df, cfg, hd), \
            df["close"].pct_change(60), fundmod.load_funding(fp)
    trend = combine.equity_to_daily_returns(run_portfolio(cf, ct, cm, cfg, top_k=3).equity)
    funding = run_carry(cf, fu, cfg, lookback_days=7, n_side=3, rebalance_days=1).daily_returns

    import yfinance as yf
    scfg = cfg.model_copy(deep=True)
    scfg.orchestrator.use_mtf = False
    raw = yf.download(US, start="2021-01-01", end="2026-06-01", interval="1d",
                      progress=False, auto_adjust=True)
    sf, st, sm = {}, {}, {}
    for t in US:
        try:
            df = pd.DataFrame({"open": raw["Open"][t], "high": raw["High"][t], "low": raw["Low"][t],
                               "close": raw["Close"][t], "volume": raw["Volume"][t]}).dropna()
        except Exception:  # noqa: BLE001
            continue
        if len(df) < 300:
            continue
        df.index = pd.DatetimeIndex(df.index).as_unit("ns")
        df.index.name = "ts"
        sf[t], st[t], sm[t] = df, orchestrator.build_target(df, scfg, None), df["close"].pct_change(90)
    usmom = combine.equity_to_daily_returns(run_portfolio(sf, st, sm, scfg, top_k=5).equity)
    return pd.DataFrame({"crypto_trend": trend, "crypto_funding": funding, "us_momentum": usmom}).dropna()


def _macro_tsmom(lookback=90):
    """Time-series momentum on macro ETFs: each instrument inverse-vol weighted, position =
    sign of trailing-lookback return (LAGGED 1 day), daily, turnover cost applied."""
    import yfinance as yf
    raw = yf.download(MACRO, start="2020-06-01", end="2026-06-01", interval="1d",
                      progress=False, auto_adjust=True)
    closes = {}
    for t in MACRO:
        try:
            c = raw["Close"][t].dropna()
        except Exception:  # noqa: BLE001
            continue
        if len(c) > 300:
            closes[t] = c
    px = pd.DataFrame(closes).dropna()
    px.index = pd.DatetimeIndex(px.index).as_unit("ns")
    rets = px.pct_change()
    # inverse-vol instrument weights (rolling 60d), position = sign(trailing momentum), lagged
    sig = np.sign(px.pct_change(lookback)).shift(1)               # no-lookahead
    invvol = (1.0 / rets.rolling(60).std()).shift(1)
    invvol = invvol.div(invvol.sum(axis=1), axis=0)
    pos = (sig * invvol).fillna(0.0)
    gross = (pos * rets).sum(axis=1)
    turn = pos.diff().abs().sum(axis=1).fillna(0.0)
    sleeve = (gross - COST * turn).dropna()
    sleeve.name = "macro_tsmom"
    return sleeve


def _equity_str(root, cfg, lookback=5):
    """Short-term reversal on US large caps: long the biggest losers / short biggest winners
    of the past `lookback` days, dollar-neutral, weekly hold, costed. Reuses yf via 3-sleeve
    cache is overkill — re-download closes (cheap)."""
    import yfinance as yf
    raw = yf.download(US, start="2021-01-01", end="2026-06-01", interval="1d",
                      progress=False, auto_adjust=True)
    closes = {}
    for t in US:
        try:
            c = raw["Close"][t].dropna()
        except Exception:  # noqa: BLE001
            continue
        if len(c) > 300:
            closes[t] = c
    px = pd.DataFrame(closes).dropna()
    px.index = pd.DatetimeIndex(px.index).as_unit("ns")
    rets = px.pct_change()
    past = px.pct_change(lookback)
    # cross-sectional demean -> short winners (+), long losers (-): weight = -z(past), lagged
    z = past.sub(past.mean(axis=1), axis=0).div(past.std(axis=1) + 1e-9, axis=0)
    w = (-z).shift(1)
    w = w.div(w.abs().sum(axis=1) + 1e-9, axis=0)  # dollar-neutral gross=1
    gross = (w * rets).sum(axis=1)
    turn = w.diff().abs().sum(axis=1).fillna(0.0)
    sleeve = (gross - COST * turn).dropna()
    sleeve.name = "equity_str"
    return sleeve


def _inv_vol_oos(R, cols):
    Rtr, Rte = R[R.index < CUT], R[R.index >= CUT]
    iv = 1.0 / Rtr[cols].std().to_numpy()
    w = iv / iv.sum()
    r = pd.Series(Rte[cols].to_numpy() @ w, index=Rte.index)
    return (*_stats(r), dict(zip(cols, w.round(2))))


def main():
    cfg = load_config(str(Path(__file__).resolve().parents[1] / "config" / "default.yaml"))
    root = Path(__file__).resolve().parents[1]
    print("3 sleeve kuruluyor (crypto trend/funding, US momentum)...")
    R3 = _three_sleeves(cfg, root)
    print("4. sleeve adayları: macro TSMOM + equity STR...")
    macro = _macro_tsmom()
    estr = _equity_str(root, cfg)

    R = R3.join(macro, how="inner").join(estr, how="inner").dropna()
    base = ["crypto_trend", "crypto_funding", "us_momentum"]

    lines = ["# LEVER #1 — 4. ortogonal sleeve avı (cross-asset kitabı 2.40'ın üstüne çıkar)", "",
             f"Ortak-gün örneklem: {len(R)} gün ({R.index[0].date()}→{R.index[-1].date()}). "
             "Tüm maliyetler dahil; pozisyonlar 1-gün gecikmeli (no-lookahead).", "",
             "## Korelasyon matrisi (full — 4. sleeve gerçekten ortogonal mi?)", "",
             "```", R.corr().round(2).to_string(), "```", "",
             "## OOS Sharpe (inverse-vol, ağırlıklar TRAIN'de fit, OOS 2025-26)", "",
             "| Kitap | OOS Sharpe | CAGR | MaxDD | ağırlıklar |", "|---|---|---|---|---|"]

    sh3, cg3, md3, w3 = _inv_vol_oos(R, base)
    lines.append(f"| 3-sleeve (baseline) | {sh3:.2f} | {cg3*100:.0f}% | {md3*100:.0f}% | {w3} |")
    results = {}
    for name, extra in (("+ macro_tsmom", "macro_tsmom"), ("+ equity_str", "equity_str"),
                        ("+ her ikisi", None)):
        cols = base + ([extra] if extra else ["macro_tsmom", "equity_str"])
        sh, cg, md, w = _inv_vol_oos(R, cols)
        results[name] = sh
        lines.append(f"| 4/5-sleeve {name} | {sh:.2f} | {cg*100:.0f}% | {md*100:.0f}% | {w} |")

    # standalone OOS sharpe of each candidate (is it even positive alone?)
    Rte = R[R.index >= CUT]
    lines += ["", "## Adayların TEK BAŞINA OOS Sharpe'ı (sleeve kendi başına para kazanıyor mu?)", ""]
    for c in ("macro_tsmom", "equity_str"):
        s, cg, md = _stats(Rte[c])
        lines.append(f"- **{c}**: OOS Sharpe {s:.2f}, CAGR {cg*100:.0f}%, MaxDD {md*100:.0f}%")

    best = max(results, key=lambda k: results[k] if results[k] == results[k] else -9)
    lift = results[best] - sh3
    lines += ["", "## Yorum (dürüst)", "",
              f"- 3-sleeve baseline OOS Sharpe **{sh3:.2f}**. En iyi 4. sleeve eklemesi: "
              f"**{best} → {results[best]:.2f}** ({'+' if lift>=0 else ''}{lift:.2f}).",
              "- Bir sleeve ancak (a) baseline'a düşük korele VE (b) tek başına pozitif/nötr "
              "OOS ise blended Sharpe'ı yükseltir. Yukarıdaki korelasyon + standalone tabloları "
              "buna karar verir.",
              "- Eğer lift ≤ ~0.1 ise: 4. sleeve breadth katmıyor (ya korele ya tek başına zayıf) "
              "→ **eklemeyin**, dürüst sonuç baseline. Eğer lift belirginse → yeni en iyi kitap.",
              "- ⚠️ yfinance survivorship-capped; OOS 2025-26 örneklemi kısa; mutlak büyüklüğe "
              "haircut uygula. Karar Sharpe + MaxDD birlikte okunarak verilmeli."]
    report = "\n".join(lines)
    print("\n" + report)
    (root / "reports_out" / "sleeve4.md").write_text(report)
    print(f"\nSaved -> {root / 'reports_out' / 'sleeve4.md'}")


if __name__ == "__main__":
    main()
