"""Phase 4 paper-trading (NO live orders).

Computes the cross-sectional Top-K holdings the system would hold right now, diffs
them against the persisted paper ledger, prints the paper orders, marks the ledger to
the latest close, and saves it. Run it whenever fresh bars arrive to accumulate
forward, survivorship-free evidence — at zero risk.

Usage: python scripts/run_paper.py [config.yaml] [top_k]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quantlab.config import load_config  # noqa: E402
from quantlab.data import cache  # noqa: E402
from quantlab.backtest import metrics  # noqa: E402
from quantlab.backtest.portfolio import run_portfolio  # noqa: E402
from quantlab import orchestrator  # noqa: E402
from quantlab.paper import engine as paper  # noqa: E402

MKTDATA = Path("../uyg/src/mktdata")
UNIVERSE = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LTC", "ATOM", "DOT",
            "LINK", "DOGE", "ETC", "FIL", "INJ", "NEAR", "UNI", "APT", "ARB", "OP"]
MOM_WINDOW = 60


def main(config_path: str, top_k: int) -> None:
    cfg = load_config(config_path)
    root = Path(config_path).resolve().parent.parent

    frames, targets, momentum = {}, {}, {}
    for sym in UNIVERSE:
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
        momentum[sym] = df["close"].pct_change(MOM_WINDOW)

    as_of = paper.last_close_date(frames)
    target = paper.live_targets(frames, cfg, top_k=top_k, mom_window=MOM_WINDOW)

    # context: the historical backtest equity + what it currently holds (consistency)
    res = run_portfolio(frames, targets, momentum, cfg, top_k=top_k)
    m = metrics.compute_metrics(res.equity, res.trades, timeframe="4h",
                                ruin_drawdown=cfg.risk.total_dd_killswitch, seed=cfg.seed)

    ledger_path = root / "reports_out" / "paper_ledger.json"
    ledger = paper.PaperLedger.load(ledger_path)
    current = ledger.holdings if ledger else []
    orders = paper.rebalance_orders(current, target)

    print(f"=== PAPER TRADING (no live orders) — as of {as_of} ===")
    print(f"Strategy: cross-sectional Top-{top_k}, ROC{MOM_WINDOW} momentum, "
          f"{cfg.data.market_type}, {len(frames)} symbols")
    print(f"Current ledger holdings: {current or '(none)'}")
    print(f"Target holdings now:     {target}")
    print(f"Paper orders -> EXIT {orders['exit']} | ENTER {orders['enter']} | HOLD {orders['hold']}")
    print(f"\nBacktest context (survivorship-capped): full-history equity "
          f"{res.equity.iloc[0]:.0f} -> {res.equity.iloc[-1]:.0f}, "
          f"Sharpe {m['sharpe']:.2f}, MaxDD {m['max_drawdown']*100:.1f}%")
    print("⚠️  Robustness test flagged this edge as FRAGILE (near coin-flip on random "
          "symbol subsets, slippage-sensitive). Paper only — do NOT risk capital yet.")

    if ledger is None:
        ledger = paper.PaperLedger(as_of=str(as_of))
    ledger.record(str(as_of), target, float(res.equity.iloc[-1]))
    ledger.note = "PAPER ONLY. Edge fragile per robustness test. No live execution without sign-off."
    ledger.save(ledger_path)
    print(f"\nSaved paper ledger -> {ledger_path}")


if __name__ == "__main__":
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).resolve().parents[1] / "config" / "default.yaml")
    k = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    main(cfg_path, k)
