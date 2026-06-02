"""Test whether an order-flow feature FAMILY raises out-of-sample decision quality.

Loads the cached pooled panel and, for the requested family, trains LightGBM on
train (≤2024) and evaluates OOS (2025-26): AUC of baseline vs baseline+family,
family-ALONE AUC, the in/out AUC gap (overfit check), and the OOS win-rate /
expectancy gate curve. Compact output for humans and workflow agents.

Usage: python scripts/feature_lab.py <family> [<family> ...]
       families: base volume price_action cvd_proxy vwap volatility funding
                 oi_ls_taker exhaustion  (or 'all')
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from lightgbm import LGBMClassifier  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TP, SL = 3.5, 1.5  # matches default RiskConfig
CUT = pd.Timestamp("2025-01-01")


def _fit_auc(cols, train, test):
    Xtr, ytr = train[cols], train["__y"]
    if ytr.nunique() < 2 or len(Xtr) < 100:
        return float("nan"), float("nan"), None
    m = LGBMClassifier(n_estimators=200, num_leaves=15, max_depth=4, learning_rate=0.05,
                       min_child_samples=50, subsample=0.8, colsample_bytree=0.8,
                       reg_lambda=1.0, random_state=42, n_jobs=1, verbose=-1)
    m.fit(Xtr.to_numpy(), ytr.to_numpy())
    p_oos = m.predict_proba(test[cols].to_numpy())[:, 1]
    p_is = m.predict_proba(Xtr.to_numpy())[:, 1]
    auc_oos = roc_auc_score(test["__y"], p_oos) if test["__y"].nunique() == 2 else float("nan")
    auc_is = roc_auc_score(ytr, p_is)
    return auc_is, auc_oos, p_oos


def main(fams: list[str]) -> None:
    panel = pd.read_parquet(ROOT / "reports_out" / "feature_panel.parquet")
    families = json.loads((ROOT / "reports_out" / "feature_families.json").read_text())
    base = [c for c in families["base"] if c in panel.columns]

    if fams == ["all"]:
        fam_cols = [c for k, v in families.items() if k != "base" for c in v if c in panel.columns]
        fams_label = "ALL order-flow"
    else:
        fam_cols, fams_label = [], "+".join(fams)
        for f in fams:
            fam_cols += [c for c in families.get(f, []) if c in panel.columns]
    fam_cols = list(dict.fromkeys(fam_cols))

    train, test = panel[panel["__ts"] < CUT], panel[panel["__ts"] >= CUT]
    yte = test["__y"].to_numpy()

    b_is, b_oos, _ = _fit_auc(base, train, test)
    c_is, c_oos, p = _fit_auc(base + fam_cols, train, test)
    f_is, f_oos, _ = _fit_auc(fam_cols, train, test) if fam_cols else (float("nan"),) * 3

    print(f"=== feature_lab: {fams_label} ({len(fam_cols)} cols) ===")
    print(f"baseline           : AUC IS {b_is:.3f} / OOS {b_oos:.3f}")
    print(f"baseline + family  : AUC IS {c_is:.3f} / OOS {c_oos:.3f}   "
          f"(OOS lift {c_oos - b_oos:+.3f})")
    print(f"family ALONE       : AUC IS {f_is:.3f} / OOS {f_oos:.3f}")
    base_win, base_exp = yte.mean(), (yte * TP - (1 - yte) * SL).mean()
    print(f"OOS base: win {base_win*100:.1f}% exp {base_exp:+.3f} ATR n={len(yte)}")
    if p is not None:
        print("gate (baseline+family) by top-X% predicted P(win):")
        for q in (0.5, 0.3, 0.2, 0.1):
            thr = np.quantile(p, 1 - q)
            g = p >= thr
            if g.sum() < 10:
                continue
            yg = yte[g]
            print(f"  top {int(q*100):>2}%: win {yg.mean()*100:.1f}%  "
                  f"exp {(yg*TP-(1-yg)*SL).mean():+.3f} ATR  n={int(g.sum())}")
    # honest read
    if c_oos == c_oos and b_oos == b_oos:
        verdict = ("LIFTS" if c_oos > b_oos + 0.01 else
                   "no lift" if c_oos >= b_oos - 0.01 else "HURTS (overfit)")
        print(f"VERDICT: family {verdict} OOS AUC ({c_oos - b_oos:+.3f}); "
              f"IS/OOS gap base {b_is-b_oos:+.3f} vs +fam {c_is-c_oos:+.3f}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["all"])
