"""The ONE testable kernel from the Winning Circle corpus: liquidity-sweep / failed-
breakout FADE (stop-hunt reversal). Causal, on 4h, pooled across 20 coins.

Downside sweep (long): bar low < prior N-bar low BUT close > that low (failed breakdown).
Upside sweep (short): bar high > prior N-bar high BUT close < that high (failed breakout).

Two honest tests:
  1) Forward-return study: do sweep bars predict reversal forward returns OOS vs an
     unconditional baseline? (falsification test the corpus reader proposed)
  2) Sleeve + correlation: build a dollar-neutral sweep-fade sleeve and measure its OOS
     Sharpe AND its correlation to the existing trend+funding combo. It only matters if
     it is BOTH positive-OOS AND low-correlation (a genuine new sleeve).

Usage: python scripts/run_sweepfade.py
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
CUT = pd.Timestamp("2025-01-01")


def sweep_signal(df: pd.DataFrame, n: int) -> pd.Series:
    """+1 downside-sweep (fade long), -1 upside-sweep (fade short), 0 else. Causal."""
    hi_lvl = df["high"].rolling(n).max().shift(1)
    lo_lvl = df["low"].rolling(n).min().shift(1)
    down_sweep = (df["low"] < lo_lvl) & (df["close"] > lo_lvl)   # failed breakdown -> long
    up_sweep = (df["high"] > hi_lvl) & (df["close"] < hi_lvl)    # failed breakout -> short
    sig = pd.Series(0.0, index=df.index)
    sig[down_sweep] = 1.0
    sig[up_sweep] = -1.0
    return sig


def main():
    cfg = load_config(str(Path(__file__).resolve().parents[1] / "config" / "default.yaml"))
    root = Path(__file__).resolve().parents[1]
    frames, targets, momentum, fundings = {}, {}, {}, {}
    for sym in UNIVERSE:
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
        momentum[sym] = df["close"].pct_change(60)
        fundings[sym] = fundmod.load_funding(fp)

    lines = ["# Liquidity-sweep / failed-breakout FADE — the corpus's one testable kernel", "",
             "## 1) Forward-return study (OOS 2025-26, pooled 20 coins, fees not applied here)", "",
             "| N | signal | mean fwd-3bar ret | hit-rate | n |", "|---|---|---|---|---|"]
    for n in (10, 20, 40):
        long_r, short_r, base_r = [], [], []
        for s, df in frames.items():
            sig = sweep_signal(df, n)
            fwd = df["close"].pct_change(3).shift(-3)  # forward 3-bar return
            oos = df.index >= CUT
            long_r += list(fwd[(sig > 0) & oos].dropna())
            short_r += list(fwd[(sig < 0) & oos].dropna())
            base_r += list(fwd[oos].dropna())
        lr, sr, br = np.array(long_r), np.array(short_r), np.array(base_r)
        lines.append(f"| {n} | fade-LONG (down-sweep) | {lr.mean()*100:+.3f}% | "
                     f"{(lr > 0).mean()*100:.1f}% | {len(lr)} |")
        lines.append(f"| {n} | fade-SHORT (up-sweep) | {sr.mean()*100:+.3f}% | "
                     f"{(sr < 0).mean()*100:.1f}% | {len(sr)} |")
        lines.append(f"| {n} | (unconditional base) | {br.mean()*100:+.3f}% | "
                     f"{(br > 0).mean()*100:.1f}% | {len(br)} |")

    # 2) sleeve: equal-weight dollar-neutral daily book from sweep signals, + correlation to combo
    # build daily sweep returns: hold each coin's sweep direction for the next day
    n = 20
    daily_rets = {}
    for s, df in frames.items():
        sig = sweep_signal(df, n)
        # position held next bar; daily resample of (signal_shifted * next-bar return)
        bar_ret = df["close"].pct_change()
        pos = sig.shift(1).fillna(0.0)
        pnl = (pos * bar_ret).resample("1D", label="left", closed="left").sum()
        daily_rets[s] = pnl
    sweep_daily = pd.DataFrame(daily_rets).mean(axis=1).dropna()  # equal-weight across coins

    # combo daily returns for correlation
    trend = run_portfolio(frames, targets, momentum, cfg, top_k=3)
    carry = run_carry(frames, fundings, cfg, lookback_days=7, n_side=3, rebalance_days=1)
    rt = combine.equity_to_daily_returns(trend.equity)
    rc = carry.daily_returns
    rt, rc = combine.align(rt, rc)
    wt, wc = combine.inverse_vol_weights(rt[rt.index < CUT], rc[rc.index < CUT])
    combo_daily = combine.blend(rt, rc, wt, wc)

    sw_oos = sweep_daily[sweep_daily.index >= CUT]
    m = metrics.compute_metrics(combine.equity_from_returns(sw_oos, 10000.0), [], timeframe="1d")
    corr = combine.correlation(sweep_daily, combo_daily)
    lines += ["", "## 2) Sweep-fade sleeve (N=20, dollar-neutral equal-weight), OOS", "",
              f"- OOS Sharpe: {m['sharpe']:.2f} | CAGR {m['cagr']*100:.1f}% | MaxDD {m['max_drawdown']*100:.1f}%",
              f"- Correlation to trend+funding combo: {corr:+.2f}",
              "", "## Verdict", ""]
    if m["sharpe"] > 0.3 and abs(corr) < 0.3:
        lines.append(f"**Possible new sleeve:** positive OOS Sharpe {m['sharpe']:.2f} AND low "
                     f"correlation {corr:+.2f} to the combo — the corpus's one real contribution. "
                     "Verify with costs + robustness before adding.")
    else:
        lines.append(f"**No edge:** OOS Sharpe {m['sharpe']:.2f}, corr {corr:+.2f}. The sweep-fade "
                     "does not beat noise / adds nothing orthogonal — consistent with the prior "
                     "mean-reversion rejection. The corpus yields no new edge. (No fees applied "
                     "above, so the real result is if anything WORSE.)")

    report = "\n".join(lines)
    print("\n" + report)
    out = root / "reports_out" / "sweepfade.md"
    out.write_text(report)
    print(f"\nSaved -> {out}")


if __name__ == "__main__":
    main()
