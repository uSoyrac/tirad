"""Paper-trading harness for the cross-sectional Top-K system.

NO live orders — this only produces the target holdings the system would take and
keeps a JSON ledger, so forward (survivorship-free) evidence can be collected at zero
risk. Adding any real-exchange execution requires explicit sign-off (see CLAUDE.md).

`live_targets` mirrors EXACTLY the selection rule inside `backtest.portfolio`: among
symbols whose trend target is long at the most recent CLOSED bar, rank by momentum and
keep the top-K. (Those would be entered at the next bar's open in the backtest, so this
is the honest "what to hold next" set — computed with no look-ahead.)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from ..config import BacktestConfig
from .. import orchestrator


def live_targets(frames: dict, cfg: BacktestConfig, top_k: int = 3, mom_window: int = 60) -> list[str]:
    """Symbols to hold for the NEXT bar, decided on the latest closed bar."""
    common = None
    for f in frames.values():
        common = f.index if common is None else common.intersection(f.index)
    last = common.sort_values()[-1]

    scored = []
    for s, df in frames.items():
        hd = df.resample("1D", label="left", closed="left").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
        ).dropna()
        tgt = orchestrator.build_target(df, cfg, hd)
        if tgt.reindex([last]).fillna(0.0).iloc[0] <= 0:
            continue  # not signalling long at the last close
        mom = df["close"].pct_change(mom_window).reindex([last]).iloc[0]
        if mom == mom:  # not NaN
            scored.append((s, float(mom)))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [s for s, _ in scored[:top_k]]


@dataclass
class PaperLedger:
    as_of: str
    holdings: list[str] = field(default_factory=list)
    cash: float = 0.0
    equity: float = 0.0
    note: str = ""
    history: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> "PaperLedger | None":
        p = Path(path)
        if not p.exists():
            return None
        return cls(**json.loads(p.read_text()))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2))

    def record(self, as_of: str, holdings: list[str], equity: float) -> None:
        self.history.append({"as_of": self.as_of, "holdings": self.holdings, "equity": self.equity})
        self.as_of, self.holdings, self.equity = as_of, holdings, equity


def rebalance_orders(current: list[str], target: list[str]) -> dict:
    """Paper orders to move from current holdings to target (no execution)."""
    return {"exit": sorted(set(current) - set(target)),
            "enter": sorted(set(target) - set(current)),
            "hold": sorted(set(current) & set(target))}


def last_close_date(frames: dict) -> pd.Timestamp:
    common = None
    for f in frames.values():
        common = f.index if common is None else common.intersection(f.index)
    return common.sort_values()[-1]
