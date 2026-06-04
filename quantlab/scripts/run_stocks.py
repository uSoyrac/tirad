"""Does the cross-sectional MOMENTUM sleeve work on US equities? (breadth, done right)

The user's insight: 80 shitcoins = fake breadth (corr ~0.8, illiquid, worst survivorship).
Real breadth = a less-correlated, liquid, large universe = STOCKS. Cross-sectional
momentum is the canonical equity anomaly (Jegadeesh-Titman 1993), so it should transfer —
and a low correlation to the crypto book would make it a genuine orthogonal sleeve.

Tests the momentum sleeve ONLY (funding is crypto-specific, doesn't transfer). Daily bars.
⚠️ Free data (yfinance) is survivorship-capped (today's large caps) — same caveat as crypto.

Usage: python scripts/run_stocks.py
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
from quantlab.data import cache  # noqa: E402
from quantlab.backtest import combine  # noqa: E402
from quantlab.backtest.portfolio import run_portfolio  # noqa: E402
from quantlab import orchestrator  # noqa: E402

US = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "JPM", "V", "JNJ", "WMT",
      "PG", "XOM", "UNH", "HD", "MA", "BAC", "KO", "PEP", "CVX", "ABBV", "COST", "MRK",
      "AVGO", "PFE", "CSCO", "ADBE", "CRM", "NFLX", "AMD"]
CRYPTO = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LTC", "ATOM", "DOT",
          "LINK", "DOGE", "ETC", "FIL", "INJ", "NEAR", "UNI", "APT", "ARB", "OP"]
CUT = pd.Timestamp("2025-01-01")
MKTDATA = Path("../uyg/src/mktdata")


def _sharpe(r, ppy):
    return float(r.mean() / r.std() * np.sqrt(ppy)) if r.std() > 0 else float("nan")


def _stock_frames(cfg):
    import yfinance as yf
    # daily stocks: no perp MTF; ensemble+regime long/flat signal is enough for the test
    scfg = cfg.model_copy(deep=True)
    scfg.orchestrator.use_mtf = False
    raw = yf.download(US, start="2021-01-01", end="2026-06-01", interval="1d",
                      progress=False, auto_adjust=True)
    frames, targets, momentum = {}, {}, {}
    for t in US:
        try:
            df = pd.DataFrame({
                "open": raw["Open"][t], "high": raw["High"][t], "low": raw["Low"][t],
                "close": raw["Close"][t], "volume": raw["Volume"][t]}).dropna()
        except Exception:  # noqa: BLE001
            continue
        if len(df) < 300:
            continue
        df.index = pd.DatetimeIndex(df.index).as_unit("ns")  # normalise resolution
        df.index.name = "ts"
        frames[t] = df
        targets[t] = orchestrator.build_target(df, scfg, None)  # no higher_df (mtf off)
        momentum[t] = df["close"].pct_change(90)  # ~4-month momentum (classic equity)
    return frames, targets, momentum


def _crypto_momentum_daily(cfg, root):
    frames, targets, momentum = {}, {}, {}
    for sym in CRYPTO:
        csv = (root / MKTDATA / f"{sym}_USDT_4h.csv").resolve()
        if not csv.exists():
            continue
        df = cache.load_ohlcv(f"{sym}/USDT", "4h", cache_dir=root / cfg.data.cache_dir,
                              start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
        hd = cache.load_ohlcv(f"{sym}/USDT", "1d", cache_dir=root / cfg.data.cache_dir,
                              start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
        frames[sym] = df
        targets[sym] = orchestrator.build_target(df, cfg, hd)
        momentum[sym] = df["close"].pct_change(60)
    res = run_portfolio(frames, targets, momentum, cfg, top_k=3)
    return combine.equity_to_daily_returns(res.equity)


def main():
    cfg = load_config(str(Path(__file__).resolve().parents[1] / "config" / "default.yaml"))
    root = Path(__file__).resolve().parents[1]
    print("Fetching US equity daily data (yfinance)...")
    sframes, stargets, smom = _stock_frames(cfg)
    print(f"  {len(sframes)} US tickers loaded.")
    res = run_portfolio(sframes, stargets, smom, cfg, top_k=5)
    sret = combine.equity_to_daily_returns(res.equity)
    sret_oos = sret[sret.index >= CUT]

    # full + OOS stock momentum performance (252 trading days/yr)
    sret_full = sret
    lines = ["# Cross-sectional momentum on US equities (breadth test)", "",
             f"Universe: {len(sframes)} liquid US large-caps, daily, top-5, 90d momentum. "
             "Survivorship-capped (today's large caps). Momentum sleeve only (funding is "
             "crypto-specific).", "",
             "## Performance", "",
             f"- Full (2021-26): Sharpe {_sharpe(sret_full, 252):.2f}, "
             f"total {( (1+sret_full).prod()-1)*100:.0f}%",
             f"- OOS (2025-26):  Sharpe {_sharpe(sret_oos, 252):.2f}, "
             f"total {((1+sret_oos).prod()-1)*100:.0f}%, "
             f"win-days {(sret_oos>0).mean()*100:.0f}%"]

    # correlation to the crypto momentum sleeve (the orthogonality / breadth question)
    print("Computing crypto momentum sleeve for correlation...")
    cret = _crypto_momentum_daily(cfg, root)
    a, b = combine.align(sret, cret)
    corr = float(np.corrcoef(a.fillna(0), b.fillna(0))[0, 1]) if len(a) > 5 else float("nan")
    # equal-vol blend of stock + crypto momentum (a cross-asset book)
    aw = a[a.index < CUT]
    bw = b[b.index < CUT]
    wt, wc = combine.inverse_vol_weights(aw, bw)
    blend_oos = combine.blend(a[a.index >= CUT], b[b.index >= CUT], wt, wc)
    lines += ["", "## Cross-asset: stock-momentum vs crypto-momentum", "",
              f"- Correlation (common days): {corr:+.2f}",
              f"- Crypto-momentum OOS Sharpe: {_sharpe(b[b.index>=CUT], 252):.2f}",
              f"- **Stock+Crypto momentum blend OOS Sharpe: {_sharpe(blend_oos, 252):.2f}** "
              f"(weights stock {wt:.2f}/crypto {wc:.2f})", "", "## Verdict", ""]
    s_oos = _sharpe(sret_oos, 252)
    if s_oos > 0.5 and abs(corr) < 0.4:
        lines.append(f"**Momentum TRANSFERS to equities (Sharpe {s_oos:.2f}) AND is low-correlation "
                     f"to crypto ({corr:+.2f}).** This is real breadth: a genuinely orthogonal "
                     "sleeve + a more-liquid, better-validated universe than shitcoins. The "
                     "cross-asset blend is the honest H1. (Equity funding-analog sleeve = future "
                     "work; momentum alone already diversifies.)")
    elif s_oos > 0.5:
        lines.append(f"**Momentum transfers (Sharpe {s_oos:.2f}) but correlation to crypto is "
                     f"{corr:+.2f}** — adds return but less diversification than hoped.")
    else:
        lines.append(f"**Weak on equities (OOS Sharpe {s_oos:.2f}).** Momentum did not transfer "
                     "cleanly here — likely the 2025-26 equity regime + survivorship-capped "
                     "free data. Inconclusive; needs point-in-time constituents.")
    report = "\n".join(lines)
    print("\n" + report)
    (root / "reports_out" / "stocks.md").write_text(report)
    print(f"\nSaved -> {root / 'reports_out' / 'stocks.md'}")


if __name__ == "__main__":
    main()
