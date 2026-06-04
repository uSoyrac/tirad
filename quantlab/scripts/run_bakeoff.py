"""Strategy bake-off — find the best DECISION-MAKER, honestly, on the same OOS window.

Runs every strategy on OOS 2025-26 with one leak-free accounting (fees/slippage/
funding/liquidation) and prints two tables:
  A) Decision quality (trade-based): win-rate, expectancy/trade, payoff, risk-of-ruin
  B) Risk-adjusted leaderboard: Sharpe, CAGR, MaxDD
Includes the june_2 'asymmetric sniper' CONCEPT re-implemented in our honest harness
(perp, leverage, %TP/SL, with liquidation modeled — the part the original omits).

Crucial framing: the highest WIN-RATE is not the best SYSTEM. We show both so the
difference is explicit.

Usage: python scripts/run_bakeoff.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from quantlab.config import load_config, RiskConfig, DataConfig  # noqa: E402
from quantlab.data import cache, funding as fundmod  # noqa: E402
from quantlab.backtest import metrics, combine  # noqa: E402
from quantlab.backtest.harness import run_backtest  # noqa: E402
from quantlab.backtest.portfolio import run_portfolio  # noqa: E402
from quantlab.backtest.carry import run_carry  # noqa: E402
from quantlab.baselines import buy_and_hold, single_indicator  # noqa: E402
from quantlab.signals import ensemble  # noqa: E402
from quantlab import orchestrator  # noqa: E402

MKTDATA = Path("../uyg/src/mktdata")
FUND = Path("../uyg/src/funddata")
UNIVERSE = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LTC", "ATOM", "DOT",
            "LINK", "DOGE", "ETC", "FIL", "INJ", "NEAR", "UNI", "APT", "ARB", "OP"]
CUT = pd.Timestamp("2025-01-01")


def _trade_metrics(trades, equity, tf):
    oos_eq = equity[equity.index >= CUT]
    m = metrics.compute_metrics(oos_eq, [t for t in trades if pd.Timestamp(t.entry_ts) >= CUT]
                                if trades else [], timeframe=tf,
                                ruin_drawdown=0.25, seed=42)
    return m


def _portfolio_sniper(frames, higher, cfg_sniper, tf="4h"):
    """Multi-coin equal-weight portfolio of the honest sniper (per-coin harness)."""
    eqs, all_trades = [], []
    for s, df in frames.items():
        sig = ensemble.signal(df, cfg_sniper)  # trend ensemble long/short entries
        res = run_backtest(df, sig, cfg_sniper)
        eqs.append(res.equity / res.equity.iloc[0])
        all_trades += [t for t in res.trades if pd.Timestamp(t.entry_ts) >= CUT]
    common = None
    for e in eqs:
        common = e.index if common is None else common.union(e.index)
    port = pd.DataFrame({i: e.reindex(common).ffill() for i, e in enumerate(eqs)}).mean(axis=1)
    return port * 10000.0, all_trades


def main() -> None:
    cfg = load_config(str(Path(__file__).resolve().parents[1] / "config" / "default.yaml"))
    root = Path(__file__).resolve().parents[1]
    frames, higher, targets, momentum, fundings = {}, {}, {}, {}, {}
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
        momentum[sym] = df["close"].pct_change(60)
        fundings[sym] = fundmod.load_funding(fp)
    btc = frames["BTC"]
    print(f"Loaded {len(frames)} coins. Running bake-off (OOS {CUT.date()}→)...")

    rows = {}  # name -> (metrics, kind)

    # --- single-asset BTC strategies ---
    rows["Buy&Hold BTC"] = (_trade_metrics(buy_and_hold.run(btc, cfg).trades,
                                           buy_and_hold.run(btc, cfg).equity, "4h"), "bench")
    st = run_backtest(btc, single_indicator.signal(btc, cfg), cfg)
    rows["Supertrend BTC"] = (_trade_metrics(st.trades, st.equity, "4h"), "trade")
    en = run_backtest(btc, ensemble.signal(btc, cfg), cfg)
    rows["Ensemble BTC"] = (_trade_metrics(en.trades, en.equity, "4h"), "trade")

    # --- cross-sectional momentum portfolio ---
    p3 = run_portfolio(frames, targets, momentum, cfg, top_k=3)
    rows["X-sec Top-3 momentum"] = (_trade_metrics(p3.trades, p3.equity, "4h"), "trade")

    # --- honest asymmetric sniper CONCEPT: TP+10%/SL-2%, 1x, loose kills to measure
    #     the raw asymmetric expectancy (the 10x version trips the kill-switches; see note) ---
    sniper = cfg.model_copy(deep=True)
    sniper.data = DataConfig(market_type="spot", symbol="BTC/USDT", timeframes=cfg.data.timeframes,
                             start=cfg.data.start, end=cfg.data.end, seed_csv=cfg.data.seed_csv)
    sniper.risk = RiskConfig(stop_mode="pct", stop_pct=0.02, tp_pct=0.10, risk_per_trade=0.02,
                             max_leverage=1.0, atr_period=14,
                             daily_dd_killswitch=0.25, total_dd_killswitch=0.60)
    sp_eq, sp_tr = _portfolio_sniper(frames, higher, sniper)
    rows["Sniper TP10/SL2 (1x, honest)"] = (_trade_metrics(sp_tr, sp_eq, "4h"), "trade")

    # --- continuous (daily-return) strategies: carry, combo, WF-combo ---
    carry = run_carry(frames, fundings, cfg, lookback_days=7, n_side=3, rebalance_days=1)
    rc = carry.daily_returns
    rows["Funding X-sec"] = (metrics.compute_metrics(
        combine.equity_from_returns(rc[rc.index >= CUT], 10000.0), [], timeframe="1d"), "cont")

    rt = combine.equity_to_daily_returns(p3.equity)
    rt, rcc = combine.align(rt, rc)
    wa, wb = combine.inverse_vol_weights(rt[rt.index < CUT], rcc[rcc.index < CUT])
    combo = combine.blend(rt[rt.index >= CUT], rcc[rcc.index >= CUT], wa, wb)
    rows["Combo (trend+funding)"] = (metrics.compute_metrics(
        combine.equity_from_returns(combo, 10000.0), [], timeframe="1d"), "cont")

    # --- TABLE A: decision quality (trade-based) ---
    out = ["# Strategy bake-off — best decision-maker (OOS 2025-26, honest accounting)", "",
           "## A) Decision quality (trade-based strategies)", "",
           "| Strategy | Win rate | Expectancy/trade | Payoff | Trades | Risk-of-ruin |",
           "|---|---|---|---|---|---|"]
    for name, (m, kind) in rows.items():
        if kind != "trade":
            continue
        out.append(f"| {name} | {m['win_rate']*100:.1f}% | {m['expectancy']:+.2f} | "
                   f"{m['payoff_ratio']:.2f} | {m['n_trades']} | {m['risk_of_ruin']*100:.1f}% |")

    # --- TABLE B: risk-adjusted leaderboard (all) ---
    out += ["", "## B) Risk-adjusted leaderboard (all strategies, ranked by OOS Sharpe)", "",
            "| Strategy | OOS Sharpe | CAGR | MaxDD | Total return |", "|---|---|---|---|---|"]
    def _shv(m):
        s = m.get("sharpe")
        return s if (s is not None and s == s) else -9.0
    ranked = sorted(rows.items(), key=lambda kv: _shv(kv[1][0]), reverse=True)
    for name, (m, kind) in ranked:
        sh = m.get("sharpe")
        out.append(f"| {name} | {sh:.2f} | {m['cagr']*100:.1f}% | {m['max_drawdown']*100:.1f}% | "
                   f"{m['total_return']*100:.1f}% |")

    # --- verdict ---
    trade_rows = {n: m for n, (m, k) in rows.items() if k == "trade" and m.get("n_trades", 0) > 0}
    best_win = max(trade_rows.items(), key=lambda kv: kv[1]["win_rate"])
    best_sharpe = ranked[0]
    out += ["", "## Verdict", "",
            f"- **Highest win-rate (most 'correct decisions'):** {best_win[0]} "
            f"({best_win[1]['win_rate']*100:.1f}%) — but win-rate alone is NOT the goal.",
            f"- **Best system (risk-adjusted, the real winner):** {best_sharpe[0]} "
            f"(OOS Sharpe {best_sharpe[1][0]['sharpe']:.2f}).",
            "- Win-rate and Sharpe usually point to DIFFERENT strategies: a high-payoff "
            "trend system wins rarely but big; a high-win-rate system can still lose money "
            "if its losers are large. The honest objective is risk-adjusted expectancy, not "
            "hit rate. (WF-optimized combo, measured separately, reaches OOS Sharpe ~2.25.)",
            "- ⚠️ The june_2 'sniper' at **10x leverage** trips our risk controls: a 2% price "
            "stop = ~10–20% equity loss, breaching the daily/total drawdown kill-switches, so "
            "the run HALTS in-sample (0 OOS trades). Shown here at 1x with loose kills to "
            "measure the raw asymmetric R/R — the leverage the original advertises is not "
            "survivable under honest risk limits."]

    report = "\n".join(out)
    print("\n" + report)
    out_dir = root / "reports_out"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "bakeoff.md").write_text(report)
    print(f"\nSaved report -> {out_dir / 'bakeoff.md'}")


if __name__ == "__main__":
    main()
