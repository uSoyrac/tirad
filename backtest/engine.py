"""
Basit backtesting motoru — anti-repainting garantili.
Tüm sinyaller kapanmış mumlar üzerinden üretilir.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    entry_bar: int
    entry_price: float
    direction: str
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    exit_price: float = 0.0
    exit_bar: int = 0
    pnl_pct: float = 0.0
    result: str = "OPEN"  # WIN, LOSS, BREAKEVEN


@dataclass
class BacktestResult:
    symbol: str
    timeframe: str
    start_date: str
    end_date: str
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    total_return: float = 0.0
    trades: list = field(default_factory=list)


def run_backtest(
    df: pd.DataFrame,
    signal_fn: Callable,
    symbol: str = "UNKNOWN",
    timeframe: str = "4h",
    tp_pct: float = 0.06,
    sl_pct: float = 0.03,
    risk_reward: float = 2.0,
) -> BacktestResult:
    """
    Walk-forward backtest.
    signal_fn(df_slice) → 'LONG' | 'SHORT' | None
    Her bar için df.iloc[:i] ile çağrılır — geleceği görmez (anti-repainting).
    """
    if df.empty or len(df) < 50:
        logger.warning(f"Backtest için yetersiz veri: {symbol}")
        return BacktestResult(symbol=symbol, timeframe=timeframe,
                              start_date="", end_date="")

    trades = []
    equity = [1.0]
    in_trade = False
    current_trade = None

    start_date = str(df.index[0].date())
    end_date = str(df.index[-1].date())

    for i in range(50, len(df) - 1):
        df_slice = df.iloc[:i]  # Sadece kapanmış mumlar
        close = df["close"].iloc[i]
        high = df["high"].iloc[i]
        low = df["low"].iloc[i]

        # Açık pozisyon var mı — exit kontrolü
        if in_trade and current_trade:
            t = current_trade
            if t.direction == "LONG":
                if low <= t.stop_loss:
                    t.exit_price = t.stop_loss
                    t.exit_bar = i
                    t.pnl_pct = (t.stop_loss - t.entry_price) / t.entry_price
                    t.result = "LOSS"
                    in_trade = False
                elif high >= t.tp1:
                    t.exit_price = t.tp1
                    t.exit_bar = i
                    t.pnl_pct = (t.tp1 - t.entry_price) / t.entry_price * 0.4
                    t.result = "WIN"
                    in_trade = False
            else:  # SHORT
                if high >= t.stop_loss:
                    t.exit_price = t.stop_loss
                    t.exit_bar = i
                    t.pnl_pct = -(t.stop_loss - t.entry_price) / t.entry_price
                    t.result = "LOSS"
                    in_trade = False
                elif low <= t.tp1:
                    t.exit_price = t.tp1
                    t.exit_bar = i
                    t.pnl_pct = (t.entry_price - t.tp1) / t.entry_price * 0.4
                    t.result = "WIN"
                    in_trade = False

            if not in_trade:
                trades.append(current_trade)
                equity.append(equity[-1] * (1 + current_trade.pnl_pct * 0.02))  # %2 risk
                current_trade = None
            continue

        # Sinyal üret (sadece kapanmış mumlarla)
        if not in_trade:
            try:
                signal = signal_fn(df_slice)
            except Exception:
                signal = None

            if signal in ("LONG", "SHORT"):
                entry = close
                if signal == "LONG":
                    sl = entry * (1 - sl_pct)
                    tp1 = entry * (1 + tp_pct)
                    tp2 = entry * (1 + tp_pct * 2)
                    tp3 = entry * (1 + tp_pct * 3.5)
                else:
                    sl = entry * (1 + sl_pct)
                    tp1 = entry * (1 - tp_pct)
                    tp2 = entry * (1 - tp_pct * 2)
                    tp3 = entry * (1 - tp_pct * 3.5)

                current_trade = BacktestTrade(
                    entry_bar=i, entry_price=entry, direction=signal,
                    stop_loss=sl, tp1=tp1, tp2=tp2, tp3=tp3,
                )
                in_trade = True

    # Metrikler
    result = BacktestResult(
        symbol=symbol, timeframe=timeframe,
        start_date=start_date, end_date=end_date,
    )

    if not trades:
        return result

    result.total_trades = len(trades)
    wins = [t for t in trades if t.result == "WIN"]
    losses = [t for t in trades if t.result == "LOSS"]
    result.winning_trades = len(wins)
    result.losing_trades = len(losses)
    result.win_rate = len(wins) / len(trades)

    win_pnls = [t.pnl_pct for t in wins]
    loss_pnls = [abs(t.pnl_pct) for t in losses]
    result.avg_win_pct = np.mean(win_pnls) if win_pnls else 0
    result.avg_loss_pct = np.mean(loss_pnls) if loss_pnls else 0

    total_wins = sum(win_pnls)
    total_losses = sum(loss_pnls)
    result.profit_factor = total_wins / total_losses if total_losses > 0 else float("inf")

    # Max Drawdown
    equity_arr = np.array(equity)
    peak = np.maximum.accumulate(equity_arr)
    drawdown = (equity_arr - peak) / peak
    result.max_drawdown = abs(drawdown.min())

    # Sharpe (basit)
    returns = np.diff(equity_arr) / equity_arr[:-1]
    if returns.std() > 0:
        result.sharpe_ratio = returns.mean() / returns.std() * np.sqrt(252)

    result.total_return = equity[-1] - 1.0
    result.trades = trades

    logger.info(
        f"Backtest {symbol}: {result.total_trades} işlem, "
        f"win rate={result.win_rate:.1%}, PF={result.profit_factor:.2f}, "
        f"DD={result.max_drawdown:.1%}"
    )

    return result
