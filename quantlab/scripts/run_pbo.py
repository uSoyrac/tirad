"""H5 — the overfitting honesty gate: Deflated Sharpe Ratio + PBO (CSCV).

Bailey & Lopez de Prado. We ran many strategy configurations; under the null, the best
in-sample Sharpe is inflated by selection. This quantifies whether the combo's edge
survives that:
  * Deflated Sharpe Ratio (DSR): P(true Sharpe > 0) after adjusting for the number of
    trials N, the variance of trial Sharpes, sample length T, skew and kurtosis.
  * PBO via Combinatorially-Symmetric Cross-Validation: fraction of IS/OOS splits where
    the IS-best config ranks BELOW median OOS — i.e. selection does not generalize.
    PBO < 0.5 good; -> 1 = overfit.

Strategy family = the combo parameter grid (trend ROCxtopK blended with carry lb,n,rebal
via inverse-vol weights). Usage: python scripts/run_pbo.py
"""

from __future__ import annotations

import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import kurtosis, norm, skew  # noqa: E402

from quantlab.config import load_config  # noqa: E402
from quantlab.data import cache, funding as fundmod  # noqa: E402
from quantlab.backtest import combine  # noqa: E402
from quantlab.backtest.portfolio import run_portfolio  # noqa: E402
from quantlab.backtest.carry import run_carry  # noqa: E402
from quantlab import orchestrator  # noqa: E402

MKTDATA = Path("../uyg/src/mktdata")
FUND = Path("../uyg/src/funddata")
UNIVERSE = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LTC", "ATOM", "DOT",
            "LINK", "DOGE", "ETC", "FIL", "INJ", "NEAR", "UNI", "APT", "ARB", "OP"]
TREND_GRID = [(mw, k) for mw in (30, 60, 120) for k in (1, 3, 5)]
CARRY_GRID = [(lb, n, rb) for lb in (3, 7, 14) for n in (3, 5) for rb in (1, 7)]
EMC = 0.5772156649


def deflated_sharpe(returns: np.ndarray, sr_trials_daily: np.ndarray):
    T = len(returns)
    sr = returns.mean() / returns.std(ddof=1)            # per-period (daily)
    sk = float(skew(returns))
    ku = float(kurtosis(returns, fisher=False))          # Pearson (normal = 3)
    N = len(sr_trials_daily)
    var_sr = np.var(sr_trials_daily, ddof=1)
    z1, z2 = norm.ppf(1 - 1.0 / N), norm.ppf(1 - 1.0 / (N * np.e))
    sr0 = np.sqrt(var_sr) * ((1 - EMC) * z1 + EMC * z2)  # expected max Sharpe under null
    num = (sr - sr0) * np.sqrt(T - 1)
    den = np.sqrt(1 - sk * sr + (ku - 1) / 4.0 * sr**2)
    return float(norm.cdf(num / den)), sr, float(sr0), N, T


def pbo_cscv(M: np.ndarray, S: int = 16):
    T, N = M.shape
    blocks = np.array_split(np.arange(T), S)
    logits = []
    for is_combo in combinations(range(S), S // 2):
        is_rows = np.concatenate([blocks[b] for b in is_combo])
        oos_rows = np.concatenate([blocks[b] for b in range(S) if b not in is_combo])
        is_sr = M[is_rows].mean(0) / (M[is_rows].std(0, ddof=1) + 1e-12)
        oos_sr = M[oos_rows].mean(0) / (M[oos_rows].std(0, ddof=1) + 1e-12)
        n_star = int(np.argmax(is_sr))
        rank = float((oos_sr <= oos_sr[n_star]).sum()) / (N + 1)  # relative OOS rank
        w = min(max(rank, 1e-6), 1 - 1e-6)
        logits.append(np.log(w / (1 - w)))
    logits = np.array(logits)
    return float((logits < 0).mean()), logits


def main():
    cfg = load_config(str(Path(__file__).resolve().parents[1] / "config" / "default.yaml"))
    root = Path(__file__).resolve().parents[1]
    frames, targets, fundings = {}, {}, {}
    for sym in UNIVERSE:
        csv = (root / MKTDATA / f"{sym}_USDT_4h.csv").resolve()
        fp = (root / FUND / f"{sym}_funding.csv").resolve()
        if not (csv.exists() and fp.exists()):
            continue
        df = cache.load_ohlcv(f"{sym}/USDT", "4h", cache_dir=root / cfg.data.cache_dir,
                              start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
        hd = cache.load_ohlcv(f"{sym}/USDT", "1d", cache_dir=root / cfg.data.cache_dir,
                              start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
        frames[sym], targets[sym] = df, orchestrator.build_target(df, cfg, hd)
        fundings[sym] = fundmod.load_funding(fp)
    print(f"Loaded {len(frames)} coins. Building combo config grid for PBO/DSR...")

    trend = {tk: combine.equity_to_daily_returns(
        run_portfolio(frames, targets, {s: frames[s]["close"].pct_change(tk[0]) for s in frames},
                      cfg, top_k=tk[1]).equity) for tk in TREND_GRID}
    carry = {ck: run_carry(frames, fundings, cfg, lookback_days=ck[0], n_side=ck[1],
                           rebalance_days=ck[2]).daily_returns for ck in CARRY_GRID}

    # config family = every (trend, carry) inverse-vol blend over full history
    cols, names = [], []
    for tk, tr in trend.items():
        for ck, cr in carry.items():
            a, b = combine.align(tr, cr)
            wt, wc = combine.inverse_vol_weights(a, b)
            cols.append(combine.blend(a, b, wt, wc).rename(f"{tk}|{ck}"))
            names.append(f"{tk}|{ck}")
    M_df = pd.concat(cols, axis=1).dropna()
    M = M_df.to_numpy()
    sr_trials = M.mean(0) / M.std(0, ddof=1)  # per-period Sharpe of each config

    # the deployed combo = default (60,3) trend + (7,3,1) carry
    deployed = M_df["(60, 3)|(7, 3, 1)"].to_numpy()
    dsr, sr_d, sr0, N, T = deflated_sharpe(deployed, sr_trials)
    ann = np.sqrt(365)

    print("Running CSCV (this is C(16,8)=12870 splits)...")
    pbo, logits = pbo_cscv(M, S=16)

    lines = ["# Overfitting honesty gate — Deflated Sharpe + PBO (combo family)", "",
             f"Strategy family: {N} combo configs (trend ROCxtopK x carry lb,n,rebal, "
             f"inverse-vol blend). Daily obs T={T} (full history).", "",
             "## Deflated Sharpe Ratio (deployed combo = trend(60,3)+carry(7,3,1))", "",
             f"- Observed daily Sharpe: {sr_d:.4f}  (annualized ~{sr_d*ann:.2f})",
             f"- Expected-max Sharpe under null (selection bias, N={N}): {sr0:.4f}  "
             f"(annualized ~{sr0*ann:.2f})",
             f"- Return skew {float(skew(deployed)):+.2f}, kurtosis {float(kurtosis(deployed, fisher=False)):.2f}",
             f"- **Deflated Sharpe Ratio (P[true Sharpe>0] after deflation): {dsr:.3f}**",
             "", "## PBO (Probability of Backtest Overfitting, CSCV S=16)", "",
             f"- **PBO = {pbo:.3f}**  (fraction of splits where IS-best config ranks below "
             "median OOS)",
             f"- Median logit: {np.median(logits):+.2f}  (positive = IS-best generalizes OOS)",
             "", "## Verdict", ""]
    ok_dsr = dsr > 0.95
    ok_pbo = pbo < 0.5
    if ok_dsr and ok_pbo:
        lines.append(f"**Edge SURVIVES the honesty gate:** DSR {dsr:.2f} (>0.95) and PBO "
                     f"{pbo:.2f} (<0.5). After deflating for {N} trials, non-normality and "
                     "IS/OOS generalization, the combo's positive Sharpe is statistically "
                     "credible — NOT just the lucky pick of the grid. (Still survivorship-capped.)")
    elif ok_pbo:
        lines.append(f"**Mixed:** PBO {pbo:.2f}<0.5 (selection generalizes) but DSR {dsr:.2f} "
                     "is not >0.95 — the edge is real-ish but not high-confidence after "
                     "deflation; treat size conservatively.")
    else:
        lines.append(f"**Likely OVERFIT:** PBO {pbo:.2f} (>=0.5 = IS-best does not generalize) "
                     f"and/or DSR {dsr:.2f} low. The grid's apparent edge is substantially a "
                     "selection artifact — do not trust the headline Sharpe.")
    report = "\n".join(lines)
    print("\n" + report)
    (root / "reports_out" / "pbo.md").write_text(report)
    print(f"\nSaved -> {root / 'reports_out' / 'pbo.md'}")


if __name__ == "__main__":
    main()
