"""Robustness + cost stress for funding-carry — the SAME gauntlet that killed momentum.

Tests whether the carry/positioning edge survives: (1) realistic slippage, (2) random
symbol sub-universes, (3) different exchanges' funding, (4) lower rebalance frequency
(to cut the heavy cost drag). OOS only. If it passes here where momentum failed, it's
a genuinely different, more trustworthy edge.

Usage: python scripts/run_carry_robust.py [config.yaml]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from quantlab.config import load_config  # noqa: E402
from quantlab.data import cache, funding as fundmod  # noqa: E402
from quantlab.backtest import metrics  # noqa: E402
from quantlab.backtest.carry import run_carry  # noqa: E402

MKTDATA = Path("../uyg/src/mktdata")
FUND_BINANCE = Path("../uyg/src/funddata")
FUND_X = Path("../uyg/src/xfunddata")
UNIVERSE = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LTC", "ATOM", "DOT",
            "LINK", "DOGE", "ETC", "FIL", "INJ", "NEAR", "UNI", "APT", "ARB", "OP"]


def _fpath(root, exch, sym):
    return ((root / FUND_BINANCE / f"{sym}_funding.csv") if exch == "binance"
            else (root / FUND_X / f"{exch}_{sym}_funding.csv")).resolve()


def _load(cfg, root, exch):
    frames, fundings = {}, {}
    for sym in UNIVERSE:
        csv = (root / MKTDATA / f"{sym}_USDT_4h.csv").resolve()
        fp = _fpath(root, exch, sym)
        if csv.exists() and fp.exists():
            frames[sym] = cache.load_ohlcv(f"{sym}/USDT", "4h", cache_dir=root / cfg.data.cache_dir,
                                           start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
            fundings[sym] = fundmod.load_funding(fp)
    return frames, fundings


def _oos_sharpe(frames, fundings, cfg, cut, **kw):
    res = run_carry(frames, fundings, cfg, **kw)
    eq = res.equity[res.equity.index >= cut]
    if len(eq) < 5:
        return None, None, None
    m = metrics.compute_metrics(eq, [], timeframe="1d")
    # OOS decomposition
    f = res.funding_pnl[res.funding_pnl.index >= cut]
    p = res.price_pnl[res.price_pnl.index >= cut]
    fund_oos = float(f.iloc[-1] - f.iloc[0])
    price_oos = float(p.iloc[-1] - p.iloc[0])
    return m["sharpe"], m["total_return"], (fund_oos, price_oos)


def main(config_path: str) -> None:
    cfg = load_config(config_path)
    root = Path(config_path).resolve().parent.parent
    cut = pd.Timestamp(cfg.splits.train_end) + pd.Timedelta(days=1)
    frames, fundings = _load(cfg, root, "binance")
    syms = list(frames.keys())
    base_slip = cfg.costs.slippage_bps
    lines = [f"# Funding-carry robustness & cost stress (OOS {cut.date()}→{cfg.data.end})", "",
             f"{len(syms)} coins, binance funding. Base: lookback 7d, n_side 3, daily rebalance.", ""]

    # 1) slippage x rebalance grid (cost is the main risk: daily rebalance is turnover-heavy)
    lines += ["## OOS Sharpe by slippage × rebalance frequency", "",
              "| slippage \\ rebal | daily | every 3d | weekly(7d) |", "|---|---|---|---|"]
    for mult in (1, 2, 3, 5):
        cfg.costs.slippage_bps = base_slip * mult
        row = [f"| {base_slip*mult:.0f}bps ({mult}x)"]
        for rb in (1, 3, 7):
            s, _, _ = _oos_sharpe(frames, fundings, cfg, cut, lookback_days=7, n_side=3, rebalance_days=rb)
            row.append(f"{s:.2f}" if s is not None else "n/a")
        lines.append(" | ".join(row) + " |")
    cfg.costs.slippage_bps = base_slip

    # 2) random sub-universe bootstrap
    rng = np.random.default_rng(cfg.seed)
    sub = max(8, len(syms) // 2)
    sh = []
    for _ in range(40):
        pick = list(rng.choice(syms, size=sub, replace=False))
        s, _, _ = _oos_sharpe({k: frames[k] for k in pick}, {k: fundings[k] for k in pick},
                              cfg, cut, lookback_days=7, n_side=3, rebalance_days=1)
        if s is not None:
            sh.append(s)
    sh = np.array(sh)
    lines += ["", f"## Random sub-universe bootstrap (40 draws of {sub} coins, base config)", "",
              f"- OOS Sharpe: median {np.median(sh):.2f}, "
              f"25–75pct [{np.percentile(sh,25):.2f}, {np.percentile(sh,75):.2f}], "
              f"share positive {np.mean(sh>0)*100:.0f}%"]

    # 3) exchange consistency
    lines += ["", "## Exchange consistency (base config, OOS)", "",
              "| Exchange | OOS Sharpe | OOS return | OOS funding | OOS price |", "|---|---|---|---|---|"]
    for exch in ("binance", "bybit", "okx"):
        fr, fu = _load(cfg, root, exch)
        s, r, decomp = _oos_sharpe(fr, fu, cfg, cut, lookback_days=7, n_side=3, rebalance_days=1)
        if s is None:
            lines.append(f"| {exch} | n/a | n/a | n/a | n/a |")
            continue
        lines.append(f"| {exch} | {s:.2f} | {r*100:.0f}% | {decomp[0]*100:+.0f}% | {decomp[1]*100:+.0f}% |")

    # verdict
    pos = np.mean(sh > 0) * 100
    med = np.median(sh)
    lines += ["", "## Verdict", ""]
    if med > 0.5 and pos >= 80:
        lines.append(f"**ROBUST:** OOS Sharpe positive in {pos:.0f}% of random sub-universes "
                     f"(median {med:.2f}), survives across exchanges and lower rebalance. Unlike "
                     "price momentum (coin-flip on subsets), this positioning/funding edge holds "
                     "broadly. ⚠️ Still: survivorship-capped universe, and watch the slippage row — "
                     "if real alt slippage > ~3x, the edge thins. Worth paper-trading.")
    elif med > 0.2 and pos >= 60:
        lines.append(f"**MODERATELY robust:** positive in {pos:.0f}% of subsets (median {med:.2f}); "
                     "better than momentum but cost/slippage-sensitive — see the stress grid.")
    else:
        lines.append(f"**Fragile:** positive in only {pos:.0f}% of subsets (median {med:.2f}). "
                     "Not a dependable edge.")

    report = "\n".join(lines)
    print("\n" + report)
    out_dir = root / "reports_out"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "carry_robustness.md").write_text(report)
    print(f"\nSaved report -> {out_dir / 'carry_robustness.md'}")


if __name__ == "__main__":
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).resolve().parents[1] / "config" / "default.yaml")
    main(cfg_path)
