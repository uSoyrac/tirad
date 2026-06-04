"""Phase 3 end-to-end: ML signal-quality filter, leak-free, measured honestly.

Pipeline:
  1. Assemble causal features + triple-barrier labels + long-candidate mask.
  2. Walk-forward out-of-fold P(profitable) — every prediction from a model trained
     only on strictly-earlier data.
  3. Report the in-sample vs OOS AUC gap (both out-of-fold) — the overfitting check.
  4. Tune the probability threshold on the TRAIN portion only.
  5. Backtest Ensemble+Filters with vs without the ML gate, on the walk-forward-
     covered span, IS vs OOS side by side. Verdict on whether ML earned its keep.

Usage: python scripts/run_phase3.py [path/to/config.yaml]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

from quantlab.config import load_config  # noqa: E402
from quantlab.data import cache  # noqa: E402
from quantlab.backtest import metrics, splits  # noqa: E402
from quantlab.backtest.harness import run_backtest  # noqa: E402
from quantlab.baselines import buy_and_hold  # noqa: E402
from quantlab import orchestrator  # noqa: E402
from quantlab.ml import dataset  # noqa: E402
from quantlab.ml.model import SignalQualityModel  # noqa: E402
from quantlab.ml.walkforward import wf_oof_proba  # noqa: E402
from quantlab.reports.report import render_report  # noqa: E402


def _m(equity, trades, tf, cfg):
    return metrics.compute_metrics(equity, trades, timeframe=tf,
                                   ruin_drawdown=cfg.risk.total_dd_killswitch, seed=cfg.seed)


def _tune_threshold(proba, y, cfg) -> tuple[float, str]:
    """Pick the threshold maximising a train-only expectancy proxy (in ATR units)."""
    tp, sl = cfg.risk.tp_atr_mult, cfg.risk.stop_atr_mult
    best_thr, best_exp, note = cfg.ml.threshold, -1e9, ""
    for thr in np.arange(0.30, 0.71, 0.02):
        sel = proba >= thr
        if sel.sum() < 30:
            continue
        labels = y[sel]
        exp = (labels * tp - (1 - labels) * sl).mean()  # per-trade ATR-units expectancy
        if exp > best_exp:
            best_exp, best_thr = exp, float(thr)
    note = f"tuned on train: thr={best_thr:.2f}, train expectancy proxy={best_exp:.3f} ATR/trade"
    return best_thr, note


def main(config_path: str) -> None:
    cfg = load_config(config_path)
    root = Path(config_path).resolve().parent.parent
    cache_dir = root / cfg.data.cache_dir
    seed_csv = (root / cfg.data.seed_csv).resolve() if cfg.data.seed_csv else None
    tf = cfg.data.primary_tf

    df = cache.load_ohlcv(cfg.data.symbol, tf, cache_dir=cache_dir,
                          start=cfg.data.start, end=cfg.data.end, seed_csv=seed_csv)
    higher_df = cache.load_ohlcv(cfg.data.symbol, cfg.mtf.higher_tf, cache_dir=cache_dir,
                                 start=cfg.data.start, end=cfg.data.end, seed_csv=seed_csv)

    X, y, mask = dataset.assemble(df, cfg, higher_df)
    proba, info = wf_oof_proba(df, cfg, higher_df)
    if proba.empty:
        print("No walk-forward predictions produced (not enough data/candidates). Aborting.")
        return

    covered = proba.index
    cut = pd.Timestamp(cfg.splits.train_end) + pd.Timedelta(days=1)

    # ---- AUC in/out gap (both out-of-fold) ----
    resolved = mask & y.notna()
    ev = resolved.reindex(covered, fill_value=False) & proba.notna()
    ev_idx = covered[ev.to_numpy()]
    is_idx = ev_idx[ev_idx < cut]
    oos_idx = ev_idx[ev_idx >= cut]

    def _auc(idx):
        if len(idx) < 20 or y.loc[idx].nunique() < 2:
            return float("nan")
        return roc_auc_score(y.loc[idx].astype(int), proba.loc[idx])

    is_auc, oos_auc = _auc(is_idx), _auc(oos_idx)

    # ---- threshold tuned on TRAIN-covered candidates only ----
    if cfg.ml.tune_threshold and len(is_idx) >= 30:
        thr, thr_note = _tune_threshold(proba.loc[is_idx], y.loc[is_idx].astype(int), cfg)
    else:
        thr, thr_note = cfg.ml.threshold, f"fixed threshold={cfg.ml.threshold}"

    # ---- targets: Phase 2 (no ML) vs Phase 3 (ML gate), evaluated on covered span ----
    tgt_no_ml = orchestrator.build_target(df, cfg, higher_df)
    tgt_ml = orchestrator.build_target(df, cfg, higher_df, ml_proba=proba, ml_threshold=thr)

    cov_df = df.loc[covered.min(): covered.max()]
    train, oos = splits.train_oos_split(cov_df, cfg.splits.train_end)

    sections, oos_cols = [], {}
    for win_name, wdf in [("In-sample (covered)", train), ("Out-of-sample (covered)", oos)]:
        if len(wdf) < 30:
            continue
        idx = wdf.index
        bh = buy_and_hold.run(wdf, cfg)
        p2 = run_backtest(wdf, tgt_no_ml.reindex(idx), cfg)
        p3 = run_backtest(wdf, tgt_ml.reindex(idx), cfg)
        cols = {
            "Buy & Hold": _m(bh.equity, bh.trades, tf, cfg),
            "Ens+Filters": _m(p2.equity, p2.trades, tf, cfg),
            "Ens+Filters+ML": _m(p3.equity, p3.trades, tf, cfg),
        }
        sections.append((f"{win_name}  ({idx[0].date()} → {idx[-1].date()})", cols))
        if win_name.startswith("Out"):
            oos_cols = cols

    # ---- ML diagnostics + feature importance (model on all IS candidates) ----
    Xtr_all, ytr_all = dataset.training_rows(X, y, mask, df.loc[:cut].index)
    importance = ""
    if len(Xtr_all) >= cfg.ml.min_train_samples and ytr_all.nunique() == 2:
        fi = SignalQualityModel(cfg).fit(Xtr_all, ytr_all).feature_importance()
        importance = ", ".join(f"{k}={int(v)}" for k, v in fi.head(8).items())

    diag = [
        "## ML diagnostics (honest overfitting check)", "",
        f"- Walk-forward windows trained: {sum(w['trained'] for w in info['windows'])}"
        f" / {len(info['windows'])} (skipped {info['skipped']})",
        f"- Covered span: {covered.min().date()} → {covered.max().date()}  ({len(covered)} bars)",
        f"- Long candidates resolved — IS: {len(is_idx)}, OOS: {len(oos_idx)}",
        f"- Base rate P(profitable) — IS: {y.loc[is_idx].mean():.3f}, "
        f"OOS: {y.loc[oos_idx].mean():.3f}" if len(oos_idx) else "- OOS base rate: n/a",
        f"- **AUC in-sample: {is_auc:.3f}  vs  out-of-sample: {oos_auc:.3f}**  "
        f"(gap {is_auc - oos_auc:+.3f}; ~0.50 = coin flip / no edge)",
        f"- {thr_note}",
        f"- Top features (gain): {importance}" if importance else "",
    ]

    report = render_report(
        f"Phase 3 ML quality filter — {cfg.data.symbol} {tf} ({cfg.data.market_type})", sections)
    report += "\n\n" + "\n".join(x for x in diag if x)
    if oos_cols:
        report += "\n\n" + _verdict(oos_cols["Ens+Filters"], oos_cols["Ens+Filters+ML"], is_auc, oos_auc)
    report += "\n"
    print("\n" + report)

    out_dir = root / "reports_out"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "phase3_ml.md").write_text(report)
    print(f"\nSaved report -> {out_dir / 'phase3_ml.md'}")


def _verdict(prev: dict, new: dict, is_auc: float, oos_auc: float) -> str:
    lines = ["## Did the ML filter earn its keep? (OOS, vs Ens+Filters)", ""]
    for key, label in [("expectancy_pct", "Expectancy/trade"), ("total_return", "Total return"),
                       ("sharpe", "Sharpe"), ("max_drawdown", "Max drawdown"),
                       ("risk_of_ruin", "Risk of ruin"), ("n_trades", "Trades")]:
        pv, nv = prev.get(key), new.get(key)
        if pv is None or nv is None or pv != pv or nv != nv:
            lines.append(f"- {label}: n/a")
            continue
        d = nv - pv
        arrow = "↑" if d > 0 else ("↓" if d < 0 else "→")
        lines.append(f"- {label}: {pv:.4f} → {nv:.4f}  ({arrow} {d:+.4f})")
    exp_prev = prev.get("expectancy_pct", -9.0)
    exp_new = new.get("expectancy_pct", -9.0)
    exp_improved = exp_new > exp_prev + 1e-6
    pos = exp_new > 0
    n_prev, n_new = prev.get("n_trades", 0), new.get("n_trades", 0)
    trades_cut = n_new < 0.6 * n_prev
    no_edge = not (oos_auc == oos_auc) or oos_auc < 0.55  # 0.55 is generous already
    lines.append("")
    if no_edge:
        msg = (f"**Verdict:** OOS AUC {oos_auc:.3f} ≈ coin flip and in-sample AUC {is_auc:.3f} "
               "is itself ~0.5 — there is NO reliable learnable signal in these features for this "
               "label. The model has no real predictive edge on unseen data.")
        if trades_cut and not pos:
            msg += (f" The lower drawdown/return is an ARTIFACT of trading far less "
                    f"({int(n_prev)}→{int(n_new)} trades) while per-trade expectancy stays "
                    f"NEGATIVE ({exp_prev:.4f}→{exp_new:.4f}) — it is exposure reduction, not "
                    "trade selection. A blunt 'trade less' rule would reproduce it.")
        msg += " Do not trust the apparent lift. (Matches the project's prior ML coin-flip finding.)"
        lines.append(msg)
    elif pos and exp_improved:
        lines.append("**Verdict:** OOS AUC > 0.55, positive OOS per-trade expectancy, AND it beats "
                     "the rule system — the ML filter earned its keep. Validate further before trusting.")
    elif exp_improved:
        lines.append("**Verdict:** ML improves OOS per-trade expectancy but it is still not "
                     "positive — partial, not yet an edge.")
    else:
        lines.append("**Verdict:** ML does NOT improve OOS per-trade expectancy — it did not earn "
                     "its keep (any return/drawdown change is just exposure, not skill).")
    return "\n".join(lines)


if __name__ == "__main__":
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).resolve().parents[1] / "config" / "default.yaml")
    main(cfg_path)
