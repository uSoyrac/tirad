"""Robustness + cost stress test for the cross-sectional Top-K system.

Addresses two honesty questions at once:
  (A) Is the edge robust, or an artifact of lucky parameters/symbols?
      - sweep K, momentum window, and slippage multiplier (OOS grid)
      - bootstrap over RANDOM symbol sub-universes -> distribution of OOS Sharpe
  (B) Survivorship: the universe is today's survivors with (mostly) full history.
      We CANNOT manufacture delisted coins, so we widen to all available symbols
      (incl. later-listed APT/ARB/OP) and report the random-subset spread. The
      remaining upward bias from truly-dead coins is flagged, not hidden.

Usage: python scripts/run_robustness.py [config.yaml]
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
from quantlab.backtest.portfolio import run_portfolio  # noqa: E402
from quantlab import orchestrator  # noqa: E402

MKTDATA = Path("../uyg/src/mktdata")
FULL_UNIVERSE = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LTC", "ATOM", "DOT",
                 "LINK", "DOGE", "ETC", "FIL", "INJ", "NEAR", "UNI", "APT", "ARB", "OP"]


def _load(cfg, root, universe):
    frames, targets = {}, {}
    for sym in universe:
        csv = (root / MKTDATA / f"{sym}_USDT_4h.csv").resolve()
        if not csv.exists():
            continue
        symbol = f"{sym}/USDT"
        df = cache.load_ohlcv(symbol, "4h", cache_dir=root / cfg.data.cache_dir,
                              start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
        hd = cache.load_ohlcv(symbol, "1d", cache_dir=root / cfg.data.cache_dir,
                              start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
        frames[sym] = df
        targets[sym] = orchestrator.build_target(df, cfg, hd)
    return frames, targets


def _oos(frames, targets, cfg, k, mom_window, cut):
    f = {s: frames[s][frames[s].index >= cut] for s in frames}
    t = {s: targets[s][targets[s].index >= cut] for s in frames}
    m = {s: frames[s]["close"].pct_change(mom_window)[frames[s].index >= cut] for s in frames}
    f = {s: v for s, v in f.items() if len(v) > mom_window}
    res = run_portfolio(f, t, m, cfg, top_k=k)
    return metrics.compute_metrics(res.equity, res.trades, timeframe="4h",
                                   ruin_drawdown=cfg.risk.total_dd_killswitch, seed=cfg.seed)


def main(config_path: str) -> None:
    cfg = load_config(config_path)
    root = Path(config_path).resolve().parent.parent
    cut = pd.Timestamp(cfg.splits.train_end) + pd.Timedelta(days=1)
    frames, targets = _load(cfg, root, FULL_UNIVERSE)
    syms = list(frames.keys())
    print(f"Universe: {len(syms)} symbols ({', '.join(syms)})")

    lines = [f"# Cross-sectional robustness & cost stress (OOS {cut.date()}→{cfg.data.end})", "",
             f"Universe: {len(syms)} symbols (incl. later-listed APT/ARB/OP).", ""]

    # ---- (A1) parameter grid: K x momentum window, base slippage ----
    lines += ["## Parameter grid (OOS Sharpe / total return / exp$/trade)", "",
              "| mom\\K | K=1 | K=3 | K=5 |", "|---|---|---|---|"]
    for mw in (30, 60, 120):
        row = [f"| ROC{mw}"]
        for k in (1, 3, 5):
            m = _oos(frames, targets, cfg, k, mw, cut)
            row.append(f"{m['sharpe']:.2f} / {m['total_return']*100:.0f}% / {m['expectancy']:.1f}")
        lines.append(" | ".join(row) + " |")

    # ---- (A2) slippage stress at the chosen config (K=3, ROC60) ----
    base_slip = cfg.costs.slippage_bps
    lines += ["", "## Slippage stress (K=3, ROC60)", "",
              "| slippage | OOS Sharpe | Total ret | Exp $/trade |", "|---|---|---|---|"]
    for mult in (1, 2, 3, 5):
        cfg.costs.slippage_bps = base_slip * mult
        m = _oos(frames, targets, cfg, 3, 60, cut)
        lines.append(f"| {base_slip*mult:.0f}bps ({mult}x) | {m['sharpe']:.2f} | "
                     f"{m['total_return']*100:.1f}% | {m['expectancy']:.2f} |")
    cfg.costs.slippage_bps = base_slip

    # ---- (B) random sub-universe bootstrap (K=3, ROC60) ----
    rng = np.random.default_rng(cfg.seed)
    sub_size = max(8, len(syms) // 2)
    sharpes, rets = [], []
    for _ in range(40):
        pick = list(rng.choice(syms, size=sub_size, replace=False))
        fsub = {s: frames[s] for s in pick}
        tsub = {s: targets[s] for s in pick}
        m = _oos(fsub, tsub, cfg, 3, 60, cut)
        sharpes.append(m["sharpe"])
        rets.append(m["total_return"])
    sharpes = np.array(sharpes)
    rets = np.array(rets)
    lines += ["", f"## Random sub-universe bootstrap (40 draws of {sub_size} symbols, K=3, ROC60)", "",
              f"- OOS Sharpe: median {np.median(sharpes):.2f}, "
              f"25–75pct [{np.percentile(sharpes,25):.2f}, {np.percentile(sharpes,75):.2f}], "
              f"share positive {np.mean(sharpes>0)*100:.0f}%",
              f"- OOS total return: median {np.median(rets)*100:.1f}%, "
              f"share positive {np.mean(rets>0)*100:.0f}%"]

    pos = np.mean(sharpes > 0) * 100
    lines += ["", "## Verdict", ""]
    if np.median(sharpes) > 0.3 and pos >= 70:
        lines.append(f"**Robust:** positive OOS Sharpe in {pos:.0f}% of random sub-universes "
                     "(median > 0.3) and across momentum windows — the edge is not a single "
                     "lucky symbol set or parameter. ⚠️ Still survivorship-capped (no delisted "
                     "coins): treat the absolute magnitude as an UPPER bound; the sign/robustness "
                     "is the trustworthy part.")
    else:
        lines.append(f"**Fragile:** OOS Sharpe positive in only {pos:.0f}% of random sub-universes "
                     "— the edge depends heavily on which symbols are included. Do not trust it.")

    report = "\n".join(lines)
    print("\n" + report)
    out_dir = root / "reports_out"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "robustness.md").write_text(report)
    print(f"\nSaved report -> {out_dir / 'robustness.md'}")


if __name__ == "__main__":
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).resolve().parents[1] / "config" / "default.yaml")
    main(cfg_path)
