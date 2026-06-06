"""Walk-forward parameter optimization of the diversified combo — the honest edge maximiser.

We do NOT add more features (those overfit). Instead we optimise the parameters that
actually drive the combo's Sharpe, with strict walk-forward: in each rolling window we
pick the best trend-param and carry-param streams + blend weight on TRAIN, then apply
them to the untouched TEST window. Concatenating the test windows gives a fully
out-of-sample, overfit-protected curve to compare against the fixed-default combo.

Efficient: each parameter combo's full-history daily returns are computed ONCE, then
walk-forward just slices/blends those precomputed streams.

Usage: python scripts/run_wfopt.py [config.yaml]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from quantlab.config import load_config  # noqa: E402
from quantlab.data import cache, funding as fundmod  # noqa: E402
from quantlab.backtest import metrics, combine  # noqa: E402
from quantlab.backtest.portfolio import run_portfolio  # noqa: E402
from quantlab.backtest.carry import run_carry  # noqa: E402
from quantlab import orchestrator  # noqa: E402

MKTDATA = Path("../uyg/src/mktdata")
FUND = Path("../uyg/src/funddata")
UNIVERSE = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LTC", "ATOM", "DOT",
            "LINK", "DOGE", "ETC", "FIL", "INJ", "NEAR", "UNI", "APT", "ARB", "OP"]
TREND_GRID = [(mw, k) for mw in (30, 60, 120) for k in (1, 3, 5)]
CARRY_GRID = [(lb, n) for lb in (3, 7, 14) for n in (3, 5)]


def _sharpe(r: pd.Series) -> float:
    return float(r.mean() / r.std() * np.sqrt(365)) if r.std() > 0 else -9.0


def main(config_path: str) -> None:
    cfg = load_config(config_path)
    root = Path(config_path).resolve().parent.parent
    frames, higher, targets, fundings = {}, {}, {}, {}
    for sym in UNIVERSE:
        csv = (root / MKTDATA / f"{sym}_USDT_4h.csv").resolve()
        fp = (root / FUND / f"{sym}_funding.csv").resolve()
        if not (csv.exists() and fp.exists()):
            continue
        df = cache.load_ohlcv(f"{sym}/USDT", "4h", cache_dir=root / cfg.data.cache_dir,
                              start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
        hd = cache.load_ohlcv(f"{sym}/USDT", "1d", cache_dir=root / cfg.data.cache_dir,
                              start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
        frames[sym], higher[sym] = df, hd
        targets[sym] = orchestrator.build_target(df, cfg, hd)
        fundings[sym] = fundmod.load_funding(fp)
    print(f"Loaded {len(frames)} coins. Precomputing {len(TREND_GRID)} trend + "
          f"{len(CARRY_GRID)} carry parameter streams...")

    # precompute daily-return streams for every parameter combo (once)
    trend_streams = {}
    for mw, k in TREND_GRID:
        mom = {s: frames[s]["close"].pct_change(mw) for s in frames}
        eq = run_portfolio(frames, targets, mom, cfg, top_k=k).equity
        trend_streams[(mw, k)] = combine.equity_to_daily_returns(eq)
    carry_streams = {}
    for lb, n in CARRY_GRID:
        carry_streams[(lb, n)] = run_carry(frames, fundings, cfg, lookback_days=lb,
                                           n_side=n, rebalance_days=1).daily_returns

    # common daily index
    idx = None
    for r in list(trend_streams.values()) + list(carry_streams.values()):
        idx = r.index if idx is None else idx.intersection(r.index)
    idx = idx.sort_values()

    # walk-forward: 12m train / 6m test, step 6m
    wf_ret = pd.Series(dtype=float)
    picks = []
    start = idx[0]
    while True:
        tr_end = start + pd.DateOffset(months=12)
        te_end = tr_end + pd.DateOffset(months=6)
        tr = idx[(idx >= start) & (idx < tr_end)]
        te = idx[(idx >= tr_end) & (idx < te_end)]
        if len(te) < 20:
            break
        # choose best trend & carry stream + inverse-vol blend on TRAIN by Sharpe
        best, best_s = None, -1e9
        for tk, tr_ret in trend_streams.items():
            for ck, cr_ret in carry_streams.items():
                a, b = tr_ret.reindex(tr).dropna(), cr_ret.reindex(tr).dropna()
                a, b = combine.align(a, b)
                if len(a) < 30:
                    continue
                wa, wb = combine.inverse_vol_weights(a, b)
                s = _sharpe(combine.blend(a, b, wa, wb))
                if s > best_s:
                    best_s, best = s, (tk, ck, wa, wb)
        if best is None:
            start = start + pd.DateOffset(months=6)
            continue
        tk, ck, wa, wb = best
        te_blend = combine.blend(trend_streams[tk].reindex(te), carry_streams[ck].reindex(te), wa, wb)
        wf_ret = pd.concat([wf_ret, te_blend.dropna()])
        picks.append((str(te[0].date()), tk, ck, round(wa, 2)))
        start = start + pd.DateOffset(months=6)

    wf_ret = wf_ret[~wf_ret.index.duplicated()].sort_index()
    cut = pd.Timestamp(cfg.splits.train_end) + pd.Timedelta(days=1)
    wf_oos = wf_ret[wf_ret.index >= cut]

    # baseline: fixed-default combo (ROC60/top3 + carry 7/3), OOS
    base_tr = trend_streams[(60, 3)]
    base_cr = carry_streams[(7, 3)]
    a, b = combine.align(base_tr, base_cr)
    wa, wb = combine.inverse_vol_weights(a[a.index < cut], b[b.index < cut])
    base_oos = combine.blend(a[a.index >= cut], b[b.index >= cut], wa, wb)

    m_wf = metrics.compute_metrics(combine.equity_from_returns(wf_oos, cfg.risk.bankroll), [], timeframe="1d")
    m_full = metrics.compute_metrics(combine.equity_from_returns(wf_ret, cfg.risk.bankroll), [], timeframe="1d")
    m_base = metrics.compute_metrics(combine.equity_from_returns(base_oos, cfg.risk.bankroll), [], timeframe="1d")

    lines = ["# Walk-forward parameter optimization of the combo", "",
             "12m train / 6m test, step 6m. Params (trend ROC×top_k, carry lookback×n_side) "
             "+ inverse-vol weight re-selected on each TRAIN window, applied to the next TEST "
             "window. Fully out-of-sample.", "",
             "## OOS (2025-26) — walk-forward-optimized vs fixed-default combo", "",
             "| Metric | Fixed default | WF-optimized |", "|---|---|---|",
             f"| Sharpe | {m_base['sharpe']:.2f} | {m_wf['sharpe']:.2f} |",
             f"| CAGR | {m_base['cagr']*100:.1f}% | {m_wf['cagr']*100:.1f}% |",
             f"| Max drawdown | {m_base['max_drawdown']*100:.1f}% | {m_wf['max_drawdown']*100:.1f}% |",
             "", f"Full walk-forward span Sharpe (all test windows): {m_full['sharpe']:.2f}", "",
             "## Parameters picked per test window (train-selected)", "",
             "| Test from | trend(ROC,topK) | carry(lb,n) | w_trend |", "|---|---|---|---|"]
    for d, tk, ck, wa in picks:
        lines.append(f"| {d} | {tk} | {ck} | {wa} |")
    lift = m_wf["sharpe"] - m_base["sharpe"]
    lines += ["", "## Verdict", ""]
    if lift > 0.1:
        lines.append(f"**WF optimization helps:** OOS Sharpe {m_base['sharpe']:.2f}→"
                     f"{m_wf['sharpe']:.2f} ({lift:+.2f}). Adapting params per regime beats the "
                     "fixed default, and it's honest (train-selected, OOS-applied).")
    elif lift > -0.1:
        lines.append(f"**Roughly neutral:** OOS Sharpe {m_base['sharpe']:.2f}→{m_wf['sharpe']:.2f} "
                     f"({lift:+.2f}). The fixed default was already near-optimal; param-chasing "
                     "doesn't add robust OOS value (good — means the default isn't cherry-picked).")
    else:
        lines.append(f"**WF optimization HURTS:** {m_base['sharpe']:.2f}→{m_wf['sharpe']:.2f} "
                     f"({lift:+.2f}) — train-best params don't persist OOS (regime instability). "
                     "Stick with the robust fixed default.")

    report = "\n".join(lines)
    print("\n" + report)
    out_dir = root / "reports_out"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "wfopt.md").write_text(report)
    print(f"\nSaved report -> {out_dir / 'wfopt.md'}")


if __name__ == "__main__":
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).resolve().parents[1] / "config" / "default.yaml")
    main(cfg_path)
