"""Event-driven backtest engine.

Design goals (the non-negotiables, enforced here):
  * No look-ahead. A signal value at bar t was decided on bar t's close and is
    EXECUTED AT BAR t+1's OPEN (we shift the signal by one bar). Stop/TP levels and
    position size use the PREVIOUS bar's ATR, never the in-flight bar's range.
  * Realistic costs. Every fill pays slippage + fee. Perp positions accrue funding
    and can be LIQUIDATED — a liquidation is booked as a real loss, never skipped.
  * Fixed-fractional sizing, delegated to risk.sizing (no martingale).
  * Drawdown kill-switches: daily (pause for the day) and total (halt the run).

Accounting is futures-style: equity = cash + unrealized_pnl. Fees and funding
debit cash immediately; realized P&L settles to cash on close. Spot is forced to
1x leverage (no liquidation) so this accounting is also correct for spot.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ..config import BacktestConfig
from ..indicators import atr
from ..risk.sizing import fixed_fractional_units
from . import costs


@dataclass
class Trade:
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    side: int  # +1 long, -1 short
    entry_price: float
    exit_price: float
    units: float
    pnl: float  # net of fees + funding
    return_pct: float  # pnl / equity-at-entry
    exit_reason: str
    fees: float
    funding: float


@dataclass
class BacktestResult:
    equity: pd.Series
    trades: list[Trade]
    halted: bool = False
    meta: dict = field(default_factory=dict)


def run_backtest(
    df: pd.DataFrame,
    signal: pd.Series,
    cfg: BacktestConfig,
    funding_rates: pd.Series | None = None,
) -> BacktestResult:
    """Run `signal` (target direction in {-1,0,1} per bar close) over `df`.

    `funding_rates` (optional) is a per-interval rate Series; when funding_mode is
    'historical' it supplies the actual rate at each funding timestamp (positive =
    longs pay shorts). If absent, the flat configured rate is used. Returns the
    per-bar equity curve and the closed-trade list.
    """
    r = cfg.risk
    c = cfg.costs
    is_perp = cfg.data.market_type == "perp"
    eff_max_lev = r.max_leverage if is_perp else 1.0
    use_hist_funding = c.funding_mode == "historical" and funding_rates is not None
    if use_hist_funding:
        funding_rates = funding_rates.sort_index()

    # Decision at bar t executes at t+1 open: shift the target forward one bar.
    desired = signal.reindex(df.index).fillna(0.0).shift(1).fillna(0.0)
    atr_prev = atr(df, r.atr_period).shift(1)  # causal: prior completed bar's ATR

    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    low = df["low"].to_numpy()
    cl = df["close"].to_numpy()
    a = atr_prev.to_numpy()
    tgt = desired.to_numpy()
    idx = df.index

    cash = r.bankroll
    pos = 0  # -1 / 0 / +1
    units = 0.0
    entry_price = 0.0
    entry_ts = None
    entry_equity = 0.0
    stop = tp = liq = float("nan")
    trade_fees = 0.0
    trade_funding = 0.0

    equity_curve = []
    trades: list[Trade] = []
    halted = False

    peak = cash
    cur_day = idx[0].date()
    day_start_equity = cash
    paused_day = None  # date for which new entries are paused

    def mark(price: float) -> float:
        return cash + units * pos * (price - entry_price) if pos != 0 else cash

    def open_position(side: int, fill: float, atr_val: float, equity_now: float):
        nonlocal pos, units, entry_price, entry_ts, entry_equity, stop, tp, liq
        nonlocal cash, trade_fees, trade_funding
        stop_dist = r.stop_atr_mult * atr_val
        u = fixed_fractional_units(equity_now, fill, stop_dist, _lev_capped(r, eff_max_lev))
        if u <= 0:
            return
        pos = side
        units = u
        entry_price = fill
        entry_ts = ts
        entry_equity = equity_now
        stop = fill - side * stop_dist
        tp = fill + side * r.tp_atr_mult * atr_val if r.tp_atr_mult else float("nan")
        liq = _liq_price(fill, side, eff_max_lev) if is_perp and eff_max_lev > 1 else float("nan")
        f = costs.fee(units * fill, c)
        cash -= f
        trade_fees = f
        trade_funding = 0.0

    def close_position(fill: float, reason: str):
        nonlocal pos, units, entry_price, entry_ts, cash, trade_fees, trade_funding
        realized = units * pos * (fill - entry_price)
        f = costs.fee(units * fill, c)
        cash += realized - f
        total_fees = trade_fees + f
        pnl = realized - total_fees + trade_funding
        trades.append(
            Trade(
                entry_ts=entry_ts,
                exit_ts=ts,
                side=pos,
                entry_price=entry_price,
                exit_price=fill,
                units=units,
                pnl=pnl,
                return_pct=pnl / entry_equity if entry_equity else 0.0,
                exit_reason=reason,
                fees=total_fees,
                funding=trade_funding,
            )
        )
        pos = 0
        units = 0.0

    for i in range(len(df)):
        ts = idx[i]

        # ---- new UTC day bookkeeping for the daily kill-switch ----
        if ts.date() != cur_day:
            cur_day = ts.date()
            day_start_equity = mark(cl[i - 1]) if i > 0 else day_start_equity
            paused_day = None

        # ---- funding accrual (perp only), charged at funding-interval boundaries ----
        if pos != 0 and c.funding_enabled and ts.hour % c.funding_interval_hours == 0:
            rate = None
            if use_hist_funding:
                r_asof = funding_rates.asof(ts)
                rate = float(r_asof) if r_asof == r_asof else None  # NaN -> flat fallback
            pay = costs.funding_payment(units * pos * o[i], c, rate=rate)
            cash -= pay
            trade_funding -= pay

        # ---- execute desired change at THIS bar's open (the t+1 open rule) ----
        want = int(tgt[i])
        atr_val = a[i]
        if not (atr_val > 0):  # warm-up bars: no ATR yet, stay flat
            equity_curve.append(mark(cl[i]))
            continue

        blocked = paused_day == cur_day or halted
        if want != pos:
            if pos != 0:
                close_position(costs.fill_price(o[i], -pos, c.slippage_bps), "signal")
            if want != 0 and not blocked:
                open_position(want, costs.fill_price(o[i], want, c.slippage_bps), atr_val, mark(o[i]))

        # ---- intrabar exits on the position we now hold (adverse ordering) ----
        if pos != 0:
            if pos > 0:
                if not _isnan(liq) and low[i] <= liq:
                    close_position(costs.fill_price(liq, -pos, c.slippage_bps), "liquidation")
                elif low[i] <= stop:
                    close_position(costs.fill_price(stop, -pos, c.slippage_bps), "stop")
                elif not _isnan(tp) and h[i] >= tp:
                    close_position(costs.fill_price(tp, -pos, c.slippage_bps), "tp")
            else:
                if not _isnan(liq) and h[i] >= liq:
                    close_position(costs.fill_price(liq, -pos, c.slippage_bps), "liquidation")
                elif h[i] >= stop:
                    close_position(costs.fill_price(stop, -pos, c.slippage_bps), "stop")
                elif not _isnan(tp) and low[i] <= tp:
                    close_position(costs.fill_price(tp, -pos, c.slippage_bps), "tp")

        # ---- mark to market at close, then kill-switch checks ----
        eq = mark(cl[i])
        peak = max(peak, eq)
        if eq / peak - 1.0 <= -r.total_dd_killswitch:
            if pos != 0:
                close_position(cl[i], "killswitch_total")
            eq = cash
            halted = True
            equity_curve.append(eq)
            # fill remaining bars flat so the curve stays aligned to the index
            for j in range(i + 1, len(df)):
                equity_curve.append(eq)
            break
        if day_start_equity and eq / day_start_equity - 1.0 <= -r.daily_dd_killswitch:
            if pos != 0:
                close_position(cl[i], "killswitch_daily")
                eq = cash
            paused_day = cur_day
        equity_curve.append(eq)

    equity = pd.Series(equity_curve, index=idx[: len(equity_curve)], name="equity")
    return BacktestResult(equity=equity, trades=trades, halted=halted, meta={
        "symbol": cfg.data.symbol,
        "market_type": cfg.data.market_type,
        "n_bars": len(df),
    })


# ---- small helpers -------------------------------------------------------------

def _isnan(x: float) -> bool:
    return x != x


def _liq_price(entry: float, side: int, leverage: float) -> float:
    # Zero-maintenance-margin approximation: liquidate when loss == initial margin.
    return entry * (1.0 - side / leverage)


class _LevCapped:
    """Thin wrapper exposing a capped max_leverage to the sizing function."""

    def __init__(self, base, max_leverage):
        self._base = base
        self.max_leverage = max_leverage

    def __getattr__(self, name):
        return getattr(self._base, name)


def _lev_capped(r, eff_max_lev):
    return _LevCapped(r, eff_max_lev)
