"""LEVER #2 — VOL-TARGETING / risk sizing on the best book (3-sleeve, OOS Sharpe 2.40).

The honest 'more money' lever that needs NO new alpha: Sharpe is leverage-invariant, so
raw leverage just rescales risk — but DYNAMIC vol-targeting (de-lever when realized vol
spikes, re-lever when calm) tames drawdowns and can lift growth-per-unit-drawdown. We:
  1. Build the 3-sleeve inverse-vol book's daily returns (cached to parquet for reuse).
  2. Vol-target it to several annual targets (10/15/20/25%) using LAGGED realized vol
     (no-lookahead), capped at 3x leverage; report Sharpe/CAGR/MaxDD/terminal/avg-lev.
  3. Compare to static fractional-Kelly. The deliverable: which risk level maximises
     compounding for a drawdown you can actually stomach.

Usage: python scripts/run_sizing.py
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
CUT = pd.Timestamp("2025-01-01")
MKTDATA = Path("../uyg/src/mktdata")
FUND = Path("../uyg/src/funddata")
PPY = 252
MAX_LEV = 3.0
SLEEVE_CACHE = Path(__file__).resolve().parents[1] / "reports_out" / "_sleeves3.parquet"


def _sharpe(r):
    return float(r.mean() / r.std() * np.sqrt(PPY)) if r.std() > 0 else float("nan")


def _stats(r):
    eq = (1 + r).cumprod()
    cagr = eq.iloc[-1] ** (PPY / len(r)) - 1 if len(r) else float("nan")
    mdd = float((eq / eq.cummax() - 1).min()) if len(r) else float("nan")
    return _sharpe(r), cagr, mdd, eq.iloc[-1]


def _build_sleeves(cfg, root):
    if SLEEVE_CACHE.exists():
        return pd.read_parquet(SLEEVE_CACHE)
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
    R = pd.DataFrame({"crypto_trend": trend, "crypto_funding": funding, "us_momentum": usmom}).dropna()
    R.to_parquet(SLEEVE_CACHE)
    return R


def _book_returns(R):
    """Inverse-vol blended book, weights fit on TRAIN only (no-lookahead)."""
    Rtr = R[R.index < CUT]
    iv = 1.0 / Rtr.std().to_numpy()
    w = iv / iv.sum()
    return pd.Series(R.to_numpy() @ w, index=R.index), dict(zip(R.columns, w.round(3)))


def _vol_target(r, target_ann, lookback=20):
    """Scale by target/realized-vol using LAGGED rolling vol; capped leverage."""
    realized = r.rolling(lookback).std().shift(1) * np.sqrt(PPY)
    lev = (target_ann / realized).clip(upper=MAX_LEV).fillna(0.0)
    return r * lev, lev


def main():
    cfg = load_config(str(Path(__file__).resolve().parents[1] / "config" / "default.yaml"))
    root = Path(__file__).resolve().parents[1]
    print("3-sleeve kitabı kuruluyor (cache varsa okunuyor)...")
    R = _build_sleeves(cfg, root)
    book, w = _book_returns(R)
    oos = book[book.index >= CUT]

    lines = ["# LEVER #2 — vol-targeting / risk sizing (3-sleeve kitap, OOS 2025-26)", "",
             f"Kitap = inverse-vol blend {w} (ağırlıklar TRAIN'de fit). OOS örneklem {len(oos)} gün. "
             f"Vol-hedefleme 20g LAGGED gerçekleşen vol ile, kaldıraç ≤{MAX_LEV:.0f}x. "
             "Sharpe kaldıraçtan bağımsızdır; asıl kazanç DİNAMİK de-risk'in drawdown'ı küçültmesi.", "",
             "## Raw (kaldıraçsız) baseline", ""]
    sh, cg, md, tw = _stats(oos)
    lines.append(f"- OOS Sharpe **{sh:.2f}**, CAGR {cg*100:.0f}%, MaxDD {md*100:.0f}%, terminal x{tw:.2f}")
    lines += ["", "## Vol-targeting (DİNAMİK — turbulansta de-lever, sakinde re-lever)", "",
              "| hedef vol | OOS Sharpe | CAGR | MaxDD | terminal x | ort. kaldıraç |",
              "|---|---|---|---|---|---|"]
    for tgt in (0.10, 0.15, 0.20, 0.25):
        rt, lev = _vol_target(book, tgt)
        rto = rt[rt.index >= CUT]
        s, c, m, t = _stats(rto)
        lines.append(f"| {tgt*100:.0f}% | {s:.2f} | {c*100:.0f}% | {m*100:.0f}% | {t:.2f} | "
                     f"{lev[lev.index >= CUT].mean():.2f}x |")

    # static fractional Kelly (for contrast — constant leverage, Sharpe-invariant)
    mu, var = oos.mean(), oos.var()
    f_star = mu / var if var > 0 else 0.0
    lines += ["", "## Statik fractional-Kelly (sabit kaldıraç — Sharpe değişmez, kontrast için)", "",
              f"Full-Kelly f* ≈ {f_star:.1f}x (OOS μ/σ², şişirilmiş — survivorship+fat-tail). Honest "
              "ceiling ≤¼-Kelly:", "",
              "| kaldıraç | CAGR | MaxDD | terminal x |", "|---|---|---|---|"]
    for frac, name in ((0.25, "¼-Kelly"), (0.5, "½-Kelly"), (1.0, "full-Kelly")):
        f = frac * f_star
        rk = oos * f
        eq = (1 + rk).cumprod()
        if (eq <= 0).any():
            lines.append(f"| {name} ({f:.1f}x) | RUIN | -100% | 0 |")
            continue
        c = eq.iloc[-1] ** (PPY / len(rk)) - 1
        m = float((eq / eq.cummax() - 1).min())
        lines.append(f"| {name} ({f:.1f}x) | {c*100:.0f}% | {m*100:.0f}% | {eq.iloc[-1]:.2f} |")

    lines += ["", "## Yorum (dürüst)", "",
              "- **Vol-targeting Sharpe'ı KÖKTEN değiştirmez** (kaldıraç-değişmez) ama dinamik "
              "de-risk genelde MaxDD'yi düşürür / drawdown-başına-büyümeyi iyileştirir — tablodan "
              "hangi hedefin en iyi Sharpe×(düşük DD) verdiği okunur.",
              "- **'Daha çok para' = stomach edebildiğin DD'ye göre risk seviyesi seç.** Yüksek "
              "hedef vol → yüksek CAGR ama yüksek DD; ≤¼-Kelly fat-tail altında dürüst tavan.",
              "- ⚠️ f* OOS-μ ile şişkin (survivorship + 2025-26 iyi geçti) → gerçek f* çok daha "
              "düşük; full/½-Kelly'yi gerçek parada KULLANMA. Vol-hedef %10-15 + ≤¼-Kelly güvenli "
              "bant. Geniş-44-coin kitabının −27% DD'si de aynı vol-hedefle ehlileştirilir."]
    report = "\n".join(lines)
    print("\n" + report)
    (root / "reports_out" / "sizing.md").write_text(report)
    print(f"\nSaved -> {root / 'reports_out' / 'sizing.md'}")


if __name__ == "__main__":
    main()
