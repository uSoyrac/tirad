"""Cross-sectional portfolio harness (spot, long-only).

Instead of trading every signalling symbol, each bar it ranks the symbols whose
trend target is long by a momentum score and holds only the TOP-K — concentrating
capital on the strongest horses (the project's 'cross-sectional alpha' idea). One
shared bankroll; each of the K slots risks a fixed fraction sized off its ATR stop,
capped so total notional stays within equity. Fees + slippage on every fill; stops
and take-profits checked intrabar per symbol.

Long-only spot keeps the accounting simple and honest (no funding/liquidation). The
target series are executed at the NEXT bar's open (shift by one) — same no-look-ahead
rule as the single-asset harness.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ..config import BacktestConfig
from ..indicators import atr
from ..risk.sizing import fixed_fractional_units
from . import costs
from .harness import Trade


@dataclass
class PortfolioResult:
    equity: pd.Series
    trades: list[Trade]
    meta: dict = field(default_factory=dict)


def run_portfolio(
    frames: dict[str, pd.DataFrame],
    targets: dict[str, pd.Series],
    momentum: dict[str, pd.Series],
    cfg: BacktestConfig,
    top_k: int = 3,
) -> PortfolioResult:
    syms = list(frames.keys())
    index = None
    for f in frames.values():
        index = f.index if index is None else index.intersection(f.index)
    index = index.sort_values()

    r, c = cfg.risk, cfg.costs
    # Pre-align everything to the common index as numpy for speed.
    o = {s: frames[s]["open"].reindex(index).to_numpy() for s in syms}
    hi = {s: frames[s]["high"].reindex(index).to_numpy() for s in syms}
    lo = {s: frames[s]["low"].reindex(index).to_numpy() for s in syms}
    cl = {s: frames[s]["close"].reindex(index).to_numpy() for s in syms}
    atrp = {s: atr(frames[s], r.atr_period).shift(1).reindex(index).to_numpy() for s in syms}
    desired = {s: targets[s].reindex(index).fillna(0.0).shift(1).fillna(0.0).to_numpy() for s in syms}
    mom = {s: momentum[s].reindex(index).to_numpy() for s in syms}

    cash = r.bankroll
    pos = {}  # sym -> dict(units, entry_price, stop, tp, entry_ts, entry_equity, fees)
    equity_curve = []
    trades: list[Trade] = []

    def mark(i):
        eq = cash
        for s, p in pos.items():
            eq += p["units"] * (cl[s][i] - p["entry_price"])
        return eq

    def close(s, i, fill, reason):
        nonlocal cash
        p = pos.pop(s)
        realized = p["units"] * (fill - p["entry_price"])
        f = costs.fee(p["units"] * fill, c)
        cash += realized - f
        total_fees = p["fees"] + f
        pnl = realized - total_fees
        trades.append(Trade(
            entry_ts=p["entry_ts"], exit_ts=index[i], side=1, entry_price=p["entry_price"],
            exit_price=fill, units=p["units"], pnl=pnl,
            return_pct=pnl / p["entry_equity"] if p["entry_equity"] else 0.0,
            exit_reason=reason, fees=total_fees, funding=0.0))

    for i in range(len(index)):
        # eligible longs this bar (target says long AND ATR ready)
        eligible = [s for s in syms if desired[s][i] > 0 and atrp[s][i] > 0]
        eligible.sort(key=lambda s: (mom[s][i] if mom[s][i] == mom[s][i] else -1e18), reverse=True)
        selected = set(eligible[:top_k])

        # exit positions that dropped out of the selection or whose signal ended
        for s in list(pos.keys()):
            if s not in selected or desired[s][i] <= 0:
                close(s, i, costs.fill_price(o[s][i], -1, c.slippage_bps), "rotate")

        # open newly selected, equal-weighting the K slots of current equity
        eq_now = mark(i)
        for s in selected:
            if s in pos:
                continue
            atr_i = atrp[s][i]
            stop_dist = r.stop_atr_mult * atr_i
            fill = costs.fill_price(o[s][i], +1, c.slippage_bps)
            units = fixed_fractional_units(eq_now, fill, stop_dist, r)
            # cap each slot's notional to equity/top_k
            units = min(units, (eq_now / top_k) / fill)
            if units <= 0:
                continue
            f = costs.fee(units * fill, c)
            cash -= f
            pos[s] = {"units": units, "entry_price": fill,
                      "stop": fill - stop_dist,
                      "tp": fill + r.tp_atr_mult * atr_i if r.tp_atr_mult else float("nan"),
                      "entry_ts": index[i], "entry_equity": eq_now, "fees": f}

        # intrabar stop / tp per held position (stop checked first = conservative)
        for s in list(pos.keys()):
            p = pos[s]
            if lo[s][i] <= p["stop"]:
                close(s, i, costs.fill_price(p["stop"], -1, c.slippage_bps), "stop")
            elif p["tp"] == p["tp"] and hi[s][i] >= p["tp"]:
                close(s, i, costs.fill_price(p["tp"], -1, c.slippage_bps), "tp")

        equity_curve.append(mark(i))

    equity = pd.Series(equity_curve, index=index, name="equity")
    open_now = {s: {"units": p["units"], "entry_price": p["entry_price"],
                    "entry_ts": str(p["entry_ts"])} for s, p in pos.items()}
    return PortfolioResult(equity=equity, trades=trades,
                           meta={"top_k": top_k, "n_symbols": len(syms),
                                 "open_positions": open_now})
