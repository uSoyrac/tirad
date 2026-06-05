"""Read the live shadow-paper-trade DOMAIN (shadow_papertrade.py outputs) and report.

This is READ-ONLY: it inspects the files the live monitor writes
(shadow_state.json + shadow_trades.jsonl + .log) and produces a status report —
current decisions, PnL, open positions, win-rate, and a LIVE-vs-BACKTEST divergence
check. It NEVER places orders. When enough resolved live trades accumulate, the same
shadow_trades.jsonl becomes the (look-ahead-free, survivorship-free) dataset to retrain
the XGBoost on REAL forward outcomes — see train_xgb_from_live().

Run on demand, or from a scheduled task, to monitor the live test.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

BOTLAR = Path.home() / "trade" / "uyg" / "Botlar"
STATE = BOTLAR / "shadow_state.json"
TRADES = BOTLAR / "shadow_trades.jsonl"
LOG = BOTLAR / "shadow_papertrade.log"


@dataclass
class LiveStatus:
    equity: float
    peak: float
    drawdown: float
    n_trades: int
    n_wins: int
    win_rate: float
    open_positions: dict
    resolved: list   # closed trades with realized pnl
    last_heartbeat: str | None


def read_status() -> LiveStatus:
    st = json.loads(STATE.read_text()) if STATE.exists() else {
        "eq": 250.0, "peak": 250.0, "positions": {}, "n_trades": 0, "n_wins": 0}
    resolved = []
    if TRADES.exists():
        for line in TRADES.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    resolved.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    eq, peak = float(st.get("eq", 250)), float(st.get("peak", 250))
    n = int(st.get("n_trades", 0))
    w = int(st.get("n_wins", 0))
    hb = None
    if LOG.exists():
        lines = [ln for ln in LOG.read_text().splitlines() if ln.strip()]
        hb = lines[-1] if lines else None
    return LiveStatus(
        equity=eq, peak=peak, drawdown=(eq / peak - 1.0) if peak else 0.0,
        n_trades=n, n_wins=w, win_rate=(w / n if n else 0.0),
        open_positions=st.get("positions", {}), resolved=resolved, last_heartbeat=hb)


def divergence(status: LiveStatus, backtest_win_rate: float, backtest_expectancy_pct: float) -> dict:
    """Compare LIVE outcomes to the backtest's expectation (the overfit detector)."""
    if status.n_trades < 5:
        return {"verdict": "insufficient_data", "n": status.n_trades,
                "note": f"{status.n_trades} live trade — need ≥5 to judge divergence."}
    pnls = [t.get("pnl", t.get("ret", 0.0)) for t in status.resolved]
    live_exp = sum(pnls) / len(pnls) if pnls else 0.0
    wr_gap = status.win_rate - backtest_win_rate
    return {"verdict": "ok" if status.win_rate >= backtest_win_rate - 0.05 else "diverging",
            "live_win_rate": status.win_rate, "backtest_win_rate": backtest_win_rate,
            "win_rate_gap": wr_gap, "live_avg_pnl": live_exp, "n": status.n_trades}


# ── HEALTH POLICY — the meaningful risk decision (you implement this) ────────────
def health_check(status: LiveStatus, div: dict) -> tuple[str, str]:
    """Decide the live system's health verdict and what action to recommend.

    Returns (level, action) where level ∈ {"GREEN","YELLOW","RED"}.

    This is a genuine risk trade-off, NOT boilerplate — it defines WHEN you stop
    trusting the live test. Too lenient → you keep running a broken edge and bleed;
    too strict → you halt on normal variance and never learn. Consider:
      - drawdown vs the backtest MaxDD (e.g. live DD breaching backtest MaxDD = RED)
      - win-rate gap (div["win_rate_gap"]) — how far below backtest before YELLOW/RED
      - sample size (don't go RED on <N trades; early losing streaks are normal)
      - a hard equity floor (e.g. equity < 0.85 * starting → RED, stop the test)
    Best-judgment defaults below; tune the constants to your risk appetite.
    """
    start = status.peak if status.peak else 250.0
    # 1) hard equity floor — capital protection beats everything
    if status.equity < 0.85 * start:
        return "RED", f"Kasa %15+ düştü (${status.equity:.0f}) — canlı testi DURDUR."
    # 2) too few trades: variance is normal, never go RED early
    if status.n_trades < 10:
        return "GREEN", f"Erken aşama ({status.n_trades} işlem) — varyans normal, izlemeye devam."
    # 3) deep drawdown vs a sane live ceiling
    if status.drawdown <= -0.20:
        return "RED", f"Drawdown {status.drawdown*100:.0f}% — risk limiti aşıldı, DURDUR."
    # 4) live win-rate materially below backtest
    if div.get("win_rate_gap", 0.0) < -0.10:
        return "YELLOW", "Win-rate backtest'in 10pp+ altında — yakından izle, sermaye artırma."
    return "GREEN", "Canlı, backtest beklentisiyle uyumlu."
