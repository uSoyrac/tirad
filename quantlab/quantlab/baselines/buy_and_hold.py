"""Buy-and-hold benchmark — the first thing any strategy must beat.

Invests the full bankroll at the first bar's open (paying one round of slippage +
fee) and marks to market every bar. Booked as a single trade closed at the last
bar so it flows through the same metrics block as everything else.
"""

from __future__ import annotations

import pandas as pd

from ..config import BacktestConfig
from ..backtest import costs
from ..backtest.harness import BacktestResult, Trade


def run(df: pd.DataFrame, cfg: BacktestConfig) -> BacktestResult:
    c = cfg.costs
    bankroll = cfg.risk.bankroll
    entry = costs.fill_price(df["open"].iloc[0], +1, c.slippage_bps)
    units = bankroll / entry
    entry_fee = costs.fee(units * entry, c)
    cash_after_entry = bankroll - entry_fee

    # Equity = cash_after_entry + unrealised on the held units, every bar.
    equity = cash_after_entry + units * (df["close"] - entry)
    equity.name = "equity"
    equity.iloc[0] = bankroll - entry_fee  # mark first bar at its close already done

    exit_price = costs.fill_price(df["close"].iloc[-1], -1, c.slippage_bps)
    exit_fee = costs.fee(units * exit_price, c)
    pnl = units * (exit_price - entry) - entry_fee - exit_fee
    trade = Trade(
        entry_ts=df.index[0],
        exit_ts=df.index[-1],
        side=1,
        entry_price=entry,
        exit_price=exit_price,
        units=units,
        pnl=pnl,
        return_pct=pnl / bankroll,
        exit_reason="end_of_data",
        fees=entry_fee + exit_fee,
        funding=0.0,
    )
    return BacktestResult(equity=equity, trades=[trade], halted=False, meta={"kind": "buy_and_hold"})
