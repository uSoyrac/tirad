"""ML4T-grade retrain of the signal-quality model (XGBoost + LightGBM).

Applies the Machine-Learning-for-Trading / Lopez de Prado methodology our earlier runs
lacked, to honestly re-check the 'coin-flip' verdict:
  * PURGED + EMBARGOED walk-forward CV — our triple-barrier labels span `horizon_bars`,
    so adjacent samples' label windows overlap; standard CV leaks. Purging drops train
    samples whose label window overlaps the test block.
  * Information Coefficient (IC = Spearman rank corr of prediction vs outcome) per fold,
    the ML4T factor-evaluation standard, alongside AUC.
  * Naive (un-purged) single split vs purged — to quantify any label-overlap leakage in
    the old number.
  * SHAP feature importance (not misleading gain importance).

Reads the cached pooled panel (scripts/build_feature_panel.py). Usage:
    python scripts/ml4t_train.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
HORIZON_TD = pd.Timedelta(hours=4 * 42)   # triple-barrier horizon (42 4h-bars)
EMBARGO_TD = pd.Timedelta(hours=4 * 5)


def _xgb():
    from xgboost import XGBClassifier
    return XGBClassifier(n_estimators=200, max_depth=4, learning_rate=0.05, subsample=0.8,
                         colsample_bytree=0.8, reg_lambda=1.0, eval_metric="logloss",
                         random_state=42, n_jobs=2)


def _lgb():
    from lightgbm import LGBMClassifier
    return LGBMClassifier(n_estimators=200, num_leaves=15, max_depth=4, learning_rate=0.05,
                          min_child_samples=50, subsample=0.8, colsample_bytree=0.8,
                          reg_lambda=1.0, random_state=42, n_jobs=2, verbose=-1)


def _fit_eval(model, Xtr, ytr, Xte, yte):
    model.fit(Xtr.to_numpy(), ytr.to_numpy())
    p = model.predict_proba(Xte.to_numpy())[:, 1]
    auc = roc_auc_score(yte, p) if yte.nunique() == 2 else float("nan")
    ic = spearmanr(p, yte).statistic if yte.nunique() == 2 else float("nan")
    return auc, ic, p


def purged_walk_forward(panel, cols, mk):
    """Expanding purged walk-forward over time blocks. Returns pooled (auc, ic)."""
    ts = panel["__ts"]
    # 6 contiguous time blocks
    edges = list(ts.quantile(np.linspace(0, 1, 7)))  # unit-safe datetime quantiles
    aucs, ics, n = [], [], 0
    for k in range(1, 6):
        a, b = edges[k], edges[k + 1]
        test = panel[(ts >= a) & (ts < b)]
        # train = strictly before block, PURGE samples whose label overlaps [a, b)
        train = panel[ts < a - HORIZON_TD - EMBARGO_TD]
        if len(train) < 500 or test["__y"].nunique() < 2 or len(test) < 100:
            continue
        auc, ic, _ = _fit_eval(mk(), train[cols], train["__y"], test[cols], test["__y"])
        aucs.append(auc)
        ics.append(ic)
        n += len(test)
    return (np.nanmean(aucs) if aucs else float("nan"),
            np.nanmean(ics) if ics else float("nan"), n)


def main():
    panel = pd.read_parquet(ROOT / "reports_out" / "feature_panel.parquet").sort_values("__ts")
    fams = json.loads((ROOT / "reports_out" / "feature_families.json").read_text())
    base = [c for c in fams["base"] if c in panel.columns]
    allc = [c for c in panel.columns if c not in ("__y", "__ts", "__coin")]
    cut = pd.Timestamp("2025-01-01")

    lines = ["# ML4T-grade retrain (purged walk-forward CV + IC + SHAP)", "",
             f"Pooled panel: {len(panel)} candidates, {len(allc)} features, "
             f"triple-barrier horizon {HORIZON_TD}.", ""]

    # 1) naive vs purged single split (leakage check), price-only features
    tr_naive = panel[panel["__ts"] < cut]
    te = panel[panel["__ts"] >= cut]
    tr_purged = panel[panel["__ts"] < cut - HORIZON_TD - EMBARGO_TD]
    lines += ["## 1) Naive vs PURGED single split (price-only) — leakage check", "",
              "| Model | split | OOS AUC | OOS IC |", "|---|---|---|---|"]
    for name, mk in (("XGBoost", _xgb), ("LightGBM", _lgb)):
        an, icn, _ = _fit_eval(mk(), tr_naive[base], tr_naive["__y"], te[base], te["__y"])
        ap, icp, _ = _fit_eval(mk(), tr_purged[base], tr_purged["__y"], te[base], te["__y"])
        lines.append(f"| {name} | naive | {an:.3f} | {icn:+.3f} |")
        lines.append(f"| {name} | purged | {ap:.3f} | {icp:+.3f} |")

    # 2) purged walk-forward IC/AUC, price-only vs all features
    lines += ["", "## 2) Purged walk-forward CV (5 folds) — does any signal survive?", "",
              "| Model | features | mean AUC | mean IC |", "|---|---|---|---|"]
    for name, mk in (("XGBoost", _xgb), ("LightGBM", _lgb)):
        for fname, cols in (("price-only", base), ("all", allc)):
            auc, ic, n = purged_walk_forward(panel, cols, mk)
            lines.append(f"| {name} | {fname} | {auc:.3f} | {ic:+.3f} |")

    # 3) SHAP top features (XGBoost on price-only, train split)
    try:
        import shap
        m = _xgb()
        m.fit(tr_purged[base].to_numpy(), tr_purged["__y"].to_numpy())
        sample = te[base].sample(min(2000, len(te)), random_state=42)
        sv = shap.TreeExplainer(m).shap_values(sample.to_numpy())
        imp = pd.Series(np.abs(sv).mean(axis=0), index=base).sort_values(ascending=False)
        lines += ["", "## 3) SHAP importance (XGBoost, price-only)", "",
                  ", ".join(f"{k}={v:.3f}" for k, v in imp.head(8).items())]
    except Exception as e:  # noqa: BLE001
        lines += ["", f"## 3) SHAP skipped: {e}"]

    # verdict
    auc_x, ic_x, _ = purged_walk_forward(panel, base, _xgb)
    lines += ["", "## Verdict", ""]
    if auc_x > 0.55 and ic_x > 0.05:
        lines.append(f"**Signal survives best-practice CV:** purged WF AUC {auc_x:.3f}, IC {ic_x:+.3f} "
                     "(>0). ML4T rigor reveals real predictive power our earlier run understated. "
                     "Re-test gating with this model.")
    else:
        lines.append(f"**Coin-flip CONFIRMED under ML4T methodology:** purged walk-forward AUC "
                     f"{auc_x:.3f}, IC {ic_x:+.3f} ≈ 0. Best-practice CV (purge+embargo) does NOT "
                     "rescue the model — if anything it removes leakage that inflated the naive "
                     "number. There is no learnable directional edge in these features; the verdict "
                     "stands. The real edge remains structural (cross-sectional momentum + funding), "
                     "not ML signal prediction.")

    report = "\n".join(lines)
    print("\n" + report)
    (ROOT / "reports_out" / "ml4t_train.md").write_text(report)
    print(f"\nSaved -> {ROOT / 'reports_out' / 'ml4t_train.md'}")


if __name__ == "__main__":
    main()
