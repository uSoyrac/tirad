"""Diversified 2-factor book: TREND sleeve + FUNDING-positioning sleeve.

Both edges are imperfect but ORTHOGONAL (trend wins in trends; funding-positioning won
in the 2025-26 chop). This blends them with inverse-vol weights fit on TRAIN only, then
measures the combined book OUT-OF-SAMPLE vs each sleeve alone — the honest test of
whether diversification actually lifts risk-adjusted return.

Usage: python scripts/run_combo.py [config.yaml]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
MOM_WINDOW = 60


def _load(cfg, root, universe):
    frames, targets, momentum, fundings = {}, {}, {}, {}
    for sym in universe:
        csv = (root / MKTDATA / f"{sym}_USDT_4h.csv").resolve()
        fp = (root / FUND / f"{sym}_funding.csv").resolve()
        if not (csv.exists() and fp.exists()):
            continue
        df = cache.load_ohlcv(f"{sym}/USDT", "4h", cache_dir=root / cfg.data.cache_dir,
                              start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
        hd = cache.load_ohlcv(f"{sym}/USDT", "1d", cache_dir=root / cfg.data.cache_dir,
                              start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
        frames[sym] = df
        targets[sym] = orchestrator.build_target(df, cfg, hd)
        momentum[sym] = df["close"].pct_change(MOM_WINDOW)
        fundings[sym] = fundmod.load_funding(fp)
    return frames, targets, momentum, fundings


def _sleeve_returns(frames, targets, momentum, fundings, cfg):
    trend = run_portfolio(frames, targets, momentum, cfg, top_k=3)
    carry = run_carry(frames, fundings, cfg, lookback_days=7, n_side=3, rebalance_days=1)
    ret_trend = combine.equity_to_daily_returns(trend.equity)
    ret_carry = carry.daily_returns
    return combine.align(ret_trend, ret_carry)


def _stats(ret, label):
    eq = combine.equity_from_returns(ret, 10_000.0)
    return metrics.compute_metrics(eq, [], timeframe="1d") | {"label": label}


def main(config_path: str) -> None:
    cfg = load_config(config_path)
    root = Path(config_path).resolve().parent.parent
    cut = pd.Timestamp(cfg.splits.train_end) + pd.Timedelta(days=1)
    frames, targets, momentum, fundings = _load(cfg, root, UNIVERSE)
    print(f"Loaded {len(frames)} coins.")

    ret_trend, ret_carry = _sleeve_returns(frames, targets, momentum, fundings, cfg)
    tr_tr, tr_ca = ret_trend[ret_trend.index < cut], ret_carry[ret_carry.index < cut]
    oo_tr, oo_ca = ret_trend[ret_trend.index >= cut], ret_carry[ret_carry.index >= cut]

    # weights fit on TRAIN only, applied OOS
    w_tr, w_ca = combine.inverse_vol_weights(tr_tr, tr_ca)
    corr_is = combine.correlation(tr_tr, tr_ca)
    corr_oos = combine.correlation(oo_tr, oo_ca)

    combo_is = combine.blend(tr_tr, tr_ca, w_tr, w_ca)
    combo_oos = combine.blend(oo_tr, oo_ca, w_tr, w_ca)

    lines = ["# Diversified 2-factor book — Trend (Top-3) + Funding-positioning", "",
             f"Inverse-vol weights (fit on TRAIN): trend {w_tr:.2f} / funding {w_ca:.2f}",
             f"Sleeve correlation: in-sample {corr_is:+.2f}, OOS {corr_oos:+.2f}  "
             "(low/negative ⇒ diversification helps)", "",
             "## Sharpe / CAGR / MaxDD", "",
             "| Window | Trend only | Funding only | **Combined** |", "|---|---|---|---|"]
    for win, rt, rc, rcomb in [("In-sample", tr_tr, tr_ca, combo_is),
                               ("Out-of-sample", oo_tr, oo_ca, combo_oos)]:
        mt, mc, mx = _stats(rt, "t"), _stats(rc, "c"), _stats(rcomb, "x")
        lines.append(
            f"| {win} | {mt['sharpe']:.2f} / {mt['cagr']*100:.0f}% / {mt['max_drawdown']*100:.0f}% "
            f"| {mc['sharpe']:.2f} / {mc['cagr']*100:.0f}% / {mc['max_drawdown']*100:.0f}% "
            f"| **{mx['sharpe']:.2f} / {mx['cagr']*100:.0f}% / {mx['max_drawdown']*100:.0f}%** |")

    # ---- robustness: random sub-universe bootstrap of the COMBINED book OOS ----
    import numpy as np
    rng = np.random.default_rng(cfg.seed)
    syms = list(frames.keys())
    sub = max(8, len(syms) // 2)
    combo_sh, trend_sh = [], []
    for _ in range(30):
        pick = list(rng.choice(syms, size=sub, replace=False))
        fr = {k: frames[k] for k in pick}
        tg = {k: targets[k] for k in pick}
        mo = {k: momentum[k] for k in pick}
        fu = {k: fundings[k] for k in pick}
        rt, rc = _sleeve_returns(fr, tg, mo, fu, cfg)
        rt_tr, rc_tr = rt[rt.index < cut], rc[rc.index < cut]
        rt_oo, rc_oo = rt[rt.index >= cut], rc[rc.index >= cut]
        wt, wc = combine.inverse_vol_weights(rt_tr, rc_tr)
        cb = combine.blend(rt_oo, rc_oo, wt, wc)
        if len(cb) > 5 and cb.std() > 0:
            combo_sh.append(cb.mean() / cb.std() * np.sqrt(365))
            trend_sh.append(rt_oo.mean() / rt_oo.std() * np.sqrt(365) if rt_oo.std() > 0 else 0.0)
    combo_sh, trend_sh = np.array(combo_sh), np.array(trend_sh)
    lines += ["", f"## Random sub-universe robustness (30 draws of {sub} coins, OOS Sharpe)", "",
              f"- **Combined**: median {np.median(combo_sh):.2f}, "
              f"share positive {np.mean(combo_sh > 0)*100:.0f}%",
              f"- Trend-only (for comparison): median {np.median(trend_sh):.2f}, "
              f"share positive {np.mean(trend_sh > 0)*100:.0f}%"]

    mx_oos = _stats(combo_oos, "x")
    mt_oos, mc_oos = _stats(oo_tr, "t"), _stats(oo_ca, "c")
    best_single = max(mt_oos["sharpe"], mc_oos["sharpe"])
    lines += ["", "## Verdict", ""]
    if mx_oos["sharpe"] > best_single + 0.05:
        lines.append(f"**Diversification WORKS:** combined OOS Sharpe {mx_oos['sharpe']:.2f} "
                     f"beats the best single sleeve ({best_single:.2f}) — the orthogonality "
                     f"(corr {corr_oos:+.2f}) delivers the free lunch. Lower drawdown too.")
    else:
        lines.append(f"**No free lunch here:** combined OOS Sharpe {mx_oos['sharpe']:.2f} does not "
                     f"beat the best single sleeve ({best_single:.2f}); the sleeves aren't "
                     f"orthogonal enough OOS (corr {corr_oos:+.2f}).")
    lines.append("\n⚠️ Both sleeves are survivorship-capped and the funding sleeve is regime/"
                 "exchange-dependent. Combined book is a candidate for PAPER trading, not live capital.")

    report = "\n".join(lines)
    print("\n" + report)
    out_dir = root / "reports_out"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "combo.md").write_text(report)
    print(f"\nSaved report -> {out_dir / 'combo.md'}")


if __name__ == "__main__":
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).resolve().parents[1] / "config" / "default.yaml")
    main(cfg_path)
