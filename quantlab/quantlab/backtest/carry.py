"""Market-neutral cross-sectional funding-CARRY backtest.

Idea (the one orthogonal, documented retail edge): perpetual funding is paid by the
crowded side. Rank coins by their recent funding; SHORT the highest-funding perps
(receive funding from over-leveraged longs) and LONG the lowest/most-negative-funding
perps (receive funding paid to shorts), dollar-neutral so market beta roughly cancels
and we harvest the funding spread.

Honest accounting, per daily step:
  net_ret = Σ wᵢ·price_retᵢ            (price P&L of each leg; longs +, shorts −)
          − Σ wᵢ·fundingᵢ              (funding: holding wᵢ notional pays wᵢ·rate;
                                         a short (wᵢ<0) RECEIVES positive funding)
          − turnover·(fee + slippage)  (rebalancing cost on both legs)

No look-ahead: the position for day t is chosen from funding/return data through
day t−1 (scores are shifted) and then earns day t's price move and funding.

Decomposition (price vs funding) is returned so we can see whether any edge is the
real funding harvest or just price luck.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..config import BacktestConfig


@dataclass
class CarryResult:
    equity: pd.Series
    daily_returns: pd.Series
    funding_pnl: pd.Series   # cumulative funding-harvest component
    price_pnl: pd.Series     # cumulative price component
    cost_pnl: pd.Series      # cumulative cost drag (negative)
    meta: dict = field(default_factory=dict)


def run_funding_harvest(
    frames: dict,
    fundings: dict,
    cfg: BacktestConfig,
    *,
    lookback_days: int = 7,
    threshold: float = 0.0,
    rebalance_days: int = 1,
) -> CarryResult:
    """TRUE delta-neutral funding harvest (the literature's low-risk carry).

    Per coin: when trailing funding is expected positive (> threshold), hold a
    delta-neutral book — long spot + SHORT perp — and collect funding (a short
    receives when funding is positive). The two price legs cancel, so this captures
    the PURE funding component with ~no directional price risk. Equal-weight across
    the active coins; costs charged on BOTH legs at every weight change.

    ⚠️ Models the hedge as perfect (one price series): real basis moves between spot
    and perp are NOT captured here — an optimistic simplification, flagged in reports.
    Decisions use funding through yesterday (shift 1): no look-ahead.
    """
    _, funding = _daily_panels(frames, fundings)
    syms = list(funding.columns)
    idx = funding.index
    cost_rate = cfg.costs.taker_fee + cfg.costs.slippage_bps / 10_000.0

    score = funding.rolling(lookback_days, min_periods=lookback_days).mean().shift(1)
    w_prev = pd.Series(0.0, index=syms)
    eq = 1.0
    eq_curve, dret, fpnl, ppnl, cpnl = [], [], [], [], []
    cum_f = cum_c = 0.0

    for i, day in enumerate(idx):
        sc = score.loc[day]
        active = [s for s in syms if sc.get(s, float("nan")) > threshold
                  and not np.isnan(funding.loc[day, s])]
        w = pd.Series(0.0, index=syms)
        if active and i % rebalance_days == 0:
            w[active] = 1.0 / len(active)   # capital split across active coins
        elif i % rebalance_days != 0:
            w = w_prev

        f = funding.loc[day].reindex(syms).fillna(0.0)
        funding_income = float((w * f).sum())   # short perp receives positive funding
        turnover = float((w - w_prev).abs().sum())
        cost = turnover * cost_rate * 2.0        # two legs (spot + perp)
        net = funding_income - cost
        eq *= (1.0 + net)
        cum_f += funding_income
        cum_c -= cost
        eq_curve.append(eq * cfg.risk.bankroll)
        dret.append(net)
        fpnl.append(cum_f)
        ppnl.append(0.0)  # delta-neutral: price legs cancel by construction
        cpnl.append(cum_c)
        w_prev = w

    return CarryResult(
        equity=pd.Series(eq_curve, index=idx, name="equity"),
        daily_returns=pd.Series(dret, index=idx, name="ret"),
        funding_pnl=pd.Series(fpnl, index=idx),
        price_pnl=pd.Series(ppnl, index=idx),
        cost_pnl=pd.Series(cpnl, index=idx),
        meta={"mode": "delta_neutral_harvest", "lookback_days": lookback_days,
              "threshold": threshold, "n_symbols": len(syms)},
    )


def _daily_panels(frames: dict, fundings: dict):
    """Build aligned daily close-return and daily-funding panels across coins."""
    close_cols, fund_cols = {}, {}
    for s, df in frames.items():
        dc = df["close"].resample("1D", label="left", closed="left").last()
        close_cols[s] = dc
        if s in fundings:
            fund_cols[s] = fundings[s].resample("1D", label="left", closed="left").sum()
    close = pd.DataFrame(close_cols).sort_index()
    funding = pd.DataFrame(fund_cols).reindex(close.index)
    ret = close.pct_change()
    return ret, funding


def run_carry(
    frames: dict,
    fundings: dict,
    cfg: BacktestConfig,
    *,
    lookback_days: int = 7,
    n_side: int = 3,
    rebalance_days: int = 1,
) -> CarryResult:
    ret, funding = _daily_panels(frames, fundings)
    syms = list(ret.columns)
    idx = ret.index

    fee = cfg.costs.taker_fee
    slip = cfg.costs.slippage_bps / 10_000.0
    cost_rate = fee + slip

    # carry score: trailing-mean daily funding, known only THROUGH yesterday (shift 1)
    score = funding.rolling(lookback_days, min_periods=lookback_days).mean().shift(1)

    weights_prev = pd.Series(0.0, index=syms)
    eq = 1.0
    eq_curve, dret, fpnl, ppnl, cpnl = [], [], [], [], []
    cum_f = cum_p = cum_c = 0.0

    for i, day in enumerate(idx):
        sc = score.loc[day].dropna()
        # need enough names with both a score and a defined return today
        valid = [s for s in sc.index if not np.isnan(ret.loc[day, s])]
        sc = sc.loc[valid]

        w = pd.Series(0.0, index=syms)
        if len(sc) >= 2 * n_side and (i % rebalance_days == 0):
            ranked = sc.sort_values()
            longs = ranked.index[:n_side]      # lowest funding -> long
            shorts = ranked.index[-n_side:]    # highest funding -> short
            w[longs] = 0.5 / n_side
            w[shorts] = -0.5 / n_side
        elif i % rebalance_days != 0:
            w = weights_prev  # hold between rebalances

        # P&L for holding w through day `day`
        r = ret.loc[day].reindex(syms).fillna(0.0)
        f = funding.loc[day].reindex(syms).fillna(0.0)
        price_component = float((w * r).sum())
        funding_component = float(-(w * f).sum())
        turnover = float((w - weights_prev).abs().sum())
        cost = turnover * cost_rate

        net = price_component + funding_component - cost
        eq *= (1.0 + net)
        cum_f += funding_component
        cum_p += price_component
        cum_c -= cost

        eq_curve.append(eq * cfg.risk.bankroll)
        dret.append(net)
        fpnl.append(cum_f)
        ppnl.append(cum_p)
        cpnl.append(cum_c)
        weights_prev = w

    equity = pd.Series(eq_curve, index=idx, name="equity")
    return CarryResult(
        equity=equity,
        daily_returns=pd.Series(dret, index=idx, name="ret"),
        funding_pnl=pd.Series(fpnl, index=idx),
        price_pnl=pd.Series(ppnl, index=idx),
        cost_pnl=pd.Series(cpnl, index=idx),
        meta={"lookback_days": lookback_days, "n_side": n_side,
              "rebalance_days": rebalance_days, "n_symbols": len(syms)},
    )
