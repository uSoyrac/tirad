"""Cross-sectional selection: hold only the top-K strongest-momentum signalling
symbols each bar, vs trading them all. Reports IS vs OOS so we see whether
concentration is a real edge or an in-sample mirage.

Usage: python scripts/run_xsection.py [config.yaml] [SYM1,SYM2,...]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from quantlab.config import load_config  # noqa: E402
from quantlab.data import cache  # noqa: E402
from quantlab.backtest import metrics  # noqa: E402
from quantlab.backtest.portfolio import run_portfolio  # noqa: E402
from quantlab import orchestrator  # noqa: E402
from quantlab.reports.report import render_report  # noqa: E402

MKTDATA = Path("../uyg/src/mktdata")
DEFAULT_UNIVERSE = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LTC", "ATOM",
                    "DOT", "LINK", "DOGE", "ETC", "FIL", "INJ", "NEAR", "UNI"]
MOM_WINDOW = 60  # ~10 days of 4h bars for the cross-sectional momentum rank


def _load(cfg, root, universe):
    frames, targets, momentum = {}, {}, {}
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
        momentum[sym] = df["close"].pct_change(MOM_WINDOW)  # causal relative strength
    return frames, targets, momentum


def _slice(frames, targets, momentum, idx):
    f = {s: frames[s].reindex(idx).dropna() for s in frames}
    t = {s: targets[s].reindex(idx) for s in frames}
    m = {s: momentum[s].reindex(idx) for s in frames}
    return f, t, m


def main(config_path: str, universe: list[str]) -> None:
    cfg = load_config(config_path)
    root = Path(config_path).resolve().parent.parent
    frames, targets, momentum = _load(cfg, root, universe)
    syms = list(frames.keys())
    print(f"Loaded {len(syms)} symbols: {', '.join(syms)}")

    common = None
    for f in frames.values():
        common = f.index if common is None else common.intersection(f.index)
    common = common.sort_values()
    cut = pd.Timestamp(cfg.splits.train_end) + pd.Timedelta(days=1)
    train_idx = common[common < cut]
    oos_idx = common[common >= cut]

    sections = []
    for win_name, idx in [("In-sample", train_idx), ("Out-of-sample", oos_idx)]:
        f, t, m = _slice(frames, targets, momentum, idx)
        cols = {}
        for k in (1, 3, 5, len(syms)):
            label = "All" if k == len(syms) else f"Top-{k}"
            res = run_portfolio(f, t, m, cfg, top_k=k)
            cols[label] = metrics.compute_metrics(
                res.equity, res.trades, timeframe="4h",
                ruin_drawdown=cfg.risk.total_dd_killswitch, seed=cfg.seed)
        sections.append((f"{win_name}  ({idx[0].date()} → {idx[-1].date()})", cols))

    report = render_report(
        f"Cross-sectional top-K selection ({len(syms)} symbols, {cfg.data.market_type})", sections)
    print("\n" + report)
    out_dir = root / "reports_out"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "xsection.md").write_text(report)
    print(f"\nSaved report -> {out_dir / 'xsection.md'}")


if __name__ == "__main__":
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).resolve().parents[1] / "config" / "default.yaml")
    uni = sys.argv[2].split(",") if len(sys.argv) > 2 else DEFAULT_UNIVERSE
    main(cfg_path, uni)
