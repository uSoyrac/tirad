"""Test each Fibonacci retracement level as range mean-reversion S/R — honestly, controlled.

User's (testable) thesis: in a RANGE (after a swing high + low), price reverts at fib
levels. The discretionary trap is anchoring + the '0.618 is magic' claim. We control for
it: in a CHOP regime, define range = rolling N-bar [low, high] (causal), and ask whether
price reverts toward centre MORE at each fib level than at a position-matched random
level. If fib levels just track the smooth 'extremes revert more' curve, there is no fib
magic — only generic range mean-reversion.

Pooled across 20 coins, 4h. Forward horizon 6 bars (~1 day). Usage: python scripts/run_fib.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from quantlab.config import load_config  # noqa: E402
from quantlab.data import cache  # noqa: E402
from quantlab.indicators import efficiency_ratio  # noqa: E402

MKTDATA = Path("../uyg/src/mktdata")
UNIVERSE = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LTC", "ATOM", "DOT",
            "LINK", "DOGE", "ETC", "FIL", "INJ", "NEAR", "UNI", "APT", "ARB", "OP"]
# ALL distinct levels across the 7 screenshots. 0<f<1 = range-retracement S/R (the user's
# range thesis); f<0 or f>1 = extension/breakout targets (tested as exhaustion-reversion).
FIBS = [-0.377, 0.236, 0.377, 0.382, 0.5, 0.618, 0.65, 0.705, 0.786, 0.886,
        1.337, 1.377, 1.618, 1.66, 2.618, 3.618]
N_RANGE = 50        # bars defining the swing range
FWD = 6             # forward bars (~1 day on 4h)
TOL = 0.025         # how close (in range-fraction) counts as 'at the level'
CUT = pd.Timestamp("2025-01-01")


def main():
    cfg = load_config(str(Path(__file__).resolve().parents[1] / "config" / "default.yaml"))
    root = Path(__file__).resolve().parents[1]
    pos_all, rev_all, chop_all = [], [], []
    for sym in UNIVERSE:
        csv = (root / MKTDATA / f"{sym}_USDT_4h.csv").resolve()
        if not csv.exists():
            continue
        df = cache.load_ohlcv(f"{sym}/USDT", "4h", cache_dir=root / cfg.data.cache_dir,
                              start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
        hi = df["high"].rolling(N_RANGE).max().shift(1)
        lo = df["low"].rolling(N_RANGE).min().shift(1)
        rng = (hi - lo)
        pos = (df["close"] - lo) / rng.replace(0.0, np.nan)     # position in range [0,1]
        er = efficiency_ratio(df, 10)                            # <0.3 = chop/ranging
        fwd = df["close"].pct_change(FWD).shift(-FWD)            # forward FWD-bar return
        # reversion return = forward move TOWARD range centre (0.5)
        rev = np.sign(0.5 - pos) * fwd
        oos = df.index >= CUT
        m = oos & pos.notna() & rev.notna() & (rng > 0)
        pos_all.append(pos[m].to_numpy())
        rev_all.append(rev[m].to_numpy())
        chop_all.append((er[m] < 0.30).to_numpy())
    P = np.concatenate(pos_all)
    R = np.concatenate(rev_all)
    C = np.concatenate(chop_all)
    Pc, Rc = P[C], R[C]   # chop-only

    lines = ["# Fibonacci levels as range mean-reversion S/R (OOS 2025-26, controlled)", "",
             f"Pooled chop bars (efficiency-ratio<0.3): {len(Pc)} of {len(P)} total. "
             f"Range=rolling-{N_RANGE}, forward {FWD} bars, reversion = move toward range centre. "
             "NO trading costs applied (so real edge is if anything worse).", "",
             "## Reversion edge vs position-in-range (the control curve)", "",
             "| position bin | mean reversion ret | hit-rate | n |", "|---|---|---|---|"]
    bins = np.linspace(0, 1, 11)
    for i in range(10):
        mlt = (Pc >= bins[i]) & (Pc < bins[i + 1])
        if mlt.sum() < 30:
            continue
        seg = Rc[mlt]
        lines.append(f"| {bins[i]:.1f}-{bins[i+1]:.1f} | {seg.mean()*100:+.3f}% | "
                     f"{(seg>0).mean()*100:.0f}% | {mlt.sum()} |")

    lines += ["", "## Each fib level vs a position-matched NON-fib control "
              "(retr=0..1 range-S/R, ext=beyond-range exhaustion)", "",
              "| fib level | zone | reversion ret | hit-rate | n | control | fib − control |",
              "|---|---|---|---|---|---|---|"]
    base = Rc.mean()
    for f in FIBS:
        zone = "retr" if 0.0 < f < 1.0 else "ext"
        at = np.abs(Pc - f) < TOL
        ctrl_lvl = f + 0.06 if f < 0.6 else f - 0.06   # position-matched non-fib level
        ctrl = np.abs(Pc - ctrl_lvl) < TOL
        if at.sum() < 30:
            lines.append(f"| {f} | {zone} | (n<30) | — | {at.sum()} | — | — |")
            continue
        fr = Rc[at].mean()
        hit = (Rc[at] > 0).mean() * 100
        cr = Rc[ctrl].mean() if ctrl.sum() >= 30 else float("nan")
        cr_s = f"{cr*100:+.3f}%" if cr == cr else "n/a"
        d_s = f"{(fr-cr)*100:+.3f}%" if cr == cr else "n/a"
        lines.append(f"| {f} | {zone} | {fr*100:+.3f}% | {hit:.0f}% | {at.sum()} | {cr_s} | {d_s} |")

    # verdict
    fib_edges = []
    for f in FIBS:
        at = np.abs(Pc - f) < TOL
        if at.sum() >= 30:
            fib_edges.append(Rc[at].mean())
    best = max(fib_edges) if fib_edges else float("nan")
    lines += ["", "## Verdict", "",
              f"- Unconditional chop reversion (any level): {base*100:+.3f}% per {FWD} bars.",
              f"- Best fib-level reversion: {best*100:+.3f}%.",
              "- **Read:** reversion strengthens toward the range EXTREMES (see the curve) — "
              "that is generic mean-reversion, true at ANY level near 0/1, not a fib property. "
              "A fib level only 'works' if it beats its position-matched non-fib control "
              "(the last column). If the fib−control deltas are ~0 / noisy and not consistently "
              "positive, the specific Fibonacci ratios add NO edge beyond 'price reverts from "
              "range edges in chop' — and that generic MR already failed as a tradable sleeve "
              "(mean_reversion.py) once costs are applied."]
    report = "\n".join(lines)
    print("\n" + report)
    (root / "reports_out" / "fib.md").write_text(report)
    print(f"\nSaved -> {root / 'reports_out' / 'fib.md'}")


if __name__ == "__main__":
    main()
