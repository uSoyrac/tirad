"""Multi-symbol, full-history evaluation — the honest edge test.

The rule system (Ensemble + regime/MTF filters) fits NO parameters, so its entire
history is out-of-sample by construction. Running it across many symbols and pooling
the trades answers the real question: averaged over regimes and assets, is there a
positive per-trade edge — or only regime-dependent noise?

Reports: per-symbol metrics, pooled per-trade expectancy, expectancy BY YEAR (a
regime proxy), and an equal-weight portfolio equity curve. No parameter is tuned here.

Usage: python scripts/run_multi.py [config.yaml] [SYM1,SYM2,...]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from quantlab.config import load_config  # noqa: E402
from quantlab.data import cache  # noqa: E402
from quantlab.backtest import metrics  # noqa: E402
from quantlab.backtest.harness import run_backtest  # noqa: E402
from quantlab import orchestrator  # noqa: E402

MKTDATA = Path("../uyg/src/mktdata")
DEFAULT_UNIVERSE = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LTC", "ATOM",
                    "DOT", "LINK", "DOGE", "ETC", "FIL", "INJ", "NEAR", "UNI"]


def _run_symbol(sym: str, cfg, root) -> tuple:
    csv = (root / MKTDATA / f"{sym}_USDT_4h.csv").resolve()
    if not csv.exists():
        return None
    symbol = f"{sym}/USDT"
    df = cache.load_ohlcv(symbol, "4h", cache_dir=root / cfg.data.cache_dir,
                          start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
    hd = cache.load_ohlcv(symbol, "1d", cache_dir=root / cfg.data.cache_dir,
                          start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
    target = orchestrator.build_target(df, cfg, hd)
    res = run_backtest(df, target, cfg)
    m = metrics.compute_metrics(res.equity, res.trades, timeframe="4h",
                                ruin_drawdown=cfg.risk.total_dd_killswitch, seed=cfg.seed)
    return sym, m, res


def main(config_path: str, universe: list[str]) -> None:
    cfg = load_config(config_path)
    root = Path(config_path).resolve().parent.parent

    rows, all_trades, equities = [], [], {}
    for sym in universe:
        out = _run_symbol(sym, cfg, root)
        if out is None:
            print(f"  skip {sym}: no CSV")
            continue
        sym, m, res = out
        rows.append((sym, m))
        all_trades.extend(res.trades)
        equities[sym] = res.equity / res.equity.iloc[0]  # normalise to 1.0
        print(f"  {sym}: ret {m['total_return']*100:6.1f}%  Sharpe {m['sharpe']:5.2f}  "
              f"exp/trade {m['expectancy']:7.2f}$  trades {m['n_trades']}")

    if not rows:
        print("No symbols ran.")
        return

    # ---- per-symbol table ----
    lines = [f"# Multi-symbol full-history edge test ({cfg.data.market_type})", "",
             f"Universe: {', '.join(s for s, _ in rows)}  ({len(rows)} symbols)",
             f"Span: {cfg.data.start} → {cfg.data.end}.  No parameters tuned (rule system).",
             "", "## Per-symbol (full history = OOS by construction)", "",
             "| Symbol | Total ret | CAGR | Sharpe | MaxDD | Win% | Exp $/trade | Trades |",
             "|---|---|---|---|---|---|---|---|"]
    for sym, m in rows:
        lines.append(f"| {sym} | {m['total_return']*100:.1f}% | {m['cagr']*100:.1f}% | "
                     f"{m['sharpe']:.2f} | {m['max_drawdown']*100:.1f}% | {m['win_rate']*100:.1f}% | "
                     f"{m['expectancy']:.2f} | {m['n_trades']} |")

    # ---- pooled per-trade stats ----
    pnls = np.array([t.pnl for t in all_trades])
    rpct = np.array([t.return_pct for t in all_trades])
    win = pnls > 0
    n_pos_sym = sum(1 for _, m in rows if m["total_return"] > 0)
    lines += ["", "## Pooled across all symbols", "",
              f"- Total trades: {len(all_trades)}",
              f"- Win rate: {win.mean()*100:.1f}%",
              f"- **Mean per-trade expectancy: {pnls.mean():+.2f}$  ({rpct.mean()*100:+.3f}% of equity)**",
              f"- Payoff ratio: {abs(pnls[win].mean() / pnls[~win].mean()):.2f}"
              if (~win).any() and win.any() else "- Payoff ratio: n/a",
              f"- Symbols net-positive: {n_pos_sym}/{len(rows)}"]

    # ---- expectancy by entry year (regime proxy) ----
    by_year = {}
    for t in all_trades:
        y = t.entry_ts.year
        by_year.setdefault(y, []).append(t.pnl)
    lines += ["", "## Per-trade expectancy by year (regime proxy)", "",
              "| Year | Trades | Win% | Exp $/trade |", "|---|---|---|---|"]
    for y in sorted(by_year):
        arr = np.array(by_year[y])
        lines.append(f"| {y} | {len(arr)} | {(arr>0).mean()*100:.1f}% | {arr.mean():+.2f} |")

    # ---- equal-weight portfolio equity ----
    common = None
    for eq in equities.values():
        common = eq.index if common is None else common.union(eq.index)
    port = pd.DataFrame({s: eq.reindex(common).ffill() for s, eq in equities.items()}).mean(axis=1)
    port = port.dropna()
    port_m = metrics.compute_metrics(port * cfg.risk.bankroll, [], timeframe="4h")
    lines += ["", "## Equal-weight portfolio (avg of normalised curves)", "",
              f"- Total return: {port_m['total_return']*100:.1f}%  |  "
              f"CAGR: {port_m['cagr']*100:.1f}%  |  Sharpe: {port_m['sharpe']:.2f}  |  "
              f"MaxDD: {port_m['max_drawdown']*100:.1f}%"]

    # ---- verdict ----
    pooled_exp = rpct.mean()
    lines += ["", "## Verdict", ""]
    if pooled_exp > 0 and n_pos_sym > len(rows) / 2:
        lines.append(f"**Pooled OOS per-trade expectancy is POSITIVE ({pooled_exp*100:+.3f}%) and a "
                     f"majority of symbols ({n_pos_sym}/{len(rows)}) are net-positive.** Across "
                     "regimes and assets the trend system shows a real (if modest) edge — not just "
                     "a single-window artifact. Validate costs/slippage sensitivity, then paper.")
    elif pooled_exp > 0:
        lines.append(f"**Pooled expectancy positive ({pooled_exp*100:+.3f}%) but driven by a "
                     f"minority of symbols ({n_pos_sym}/{len(rows)} positive)** — fragile / "
                     "concentration risk, not a broad edge.")
    else:
        lines.append(f"**Pooled OOS per-trade expectancy is NEGATIVE ({pooled_exp*100:+.3f}%) "
                     f"across {len(rows)} symbols ({n_pos_sym} positive).** No broad trend edge "
                     "even across regimes — the by-year table shows where it works (trends) and "
                     "fails (chop). Honest conclusion: this is a regime tool, not a standalone alpha.")

    report = "\n".join(lines)
    print("\n" + report)
    out_dir = root / "reports_out"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "multi_symbol.md").write_text(report)
    print(f"\nSaved report -> {out_dir / 'multi_symbol.md'}")


if __name__ == "__main__":
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).resolve().parents[1] / "config" / "default.yaml")
    uni = sys.argv[2].split(",") if len(sys.argv) > 2 else DEFAULT_UNIVERSE
    main(cfg_path, uni)
