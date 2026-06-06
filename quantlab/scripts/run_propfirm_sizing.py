"""PROP-PASS sizing maximization — find the vol LEVEL ceiling, then test if ANY adaptive
path-shaping beats the BEST constant-vol at its own optimum.

LEVER: maximize P(reach +target before a daily/total breach). The prior run_propfirm_opt.py
compared 4 hand-coded policies against a FIXED 12% baseline with arbitrary VOL_HI/LO/BUFFER and
concluded "de-risk hurts". This re-examines the question correctly:
  1. Sweep constant vol finely -> the true P(pass) ceiling and the vol that achieves it.
  2. For each ADAPTIVE family, grid its OWN parameters and report its BEST P(pass) -- so we
     compare best-adaptive vs best-constant, not adaptive vs a fixed baseline.
Adaptive families tested (alpha held constant, only position SIZE varies by path):
  - CONST            : constant vol target (baseline ceiling)
  - RAMP_UP          : start lower, raise vol after building a buffer (let winners compound)
  - DERISK           : start high to build buffer fast, then cut vol to protect it
  - LOCK_NEAR        : full vol until near target, then shrink to ~0 (don't give it back)
  - DAILY_GOV        : constant vol + intraday -g% self-halt (caps daily loss below the cliff)

Two real cards (HyroTrader):
  - ONE-STEP : +10% target, total -6% TRAILING (EOD peak), daily -4%, min 5 days.
  - TWO-STEP : P1 +10% / P2 +5%, total -10% TRAILING, daily -5%, min 10+5 days.

Honest: 0.6 survivorship haircut on the mean; block-bootstrap preserves vol-clustering AND the
positive skew that helps reach target; EOD-only -> add an intraday-proximity warning. Reports IS
vs OOS vs ALL residual pools (regime sensitivity). 100% is impossible; we find the honest ceiling.

Usage: cd quantlab && .venv/bin/python scripts/run_propfirm_sizing.py
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

CUT = pd.Timestamp("2025-01-01")
PPY = 365
SLEEVE3 = Path(__file__).resolve().parents[1] / "reports_out" / "_sleeves3.parquet"
HAIRCUT = 0.60
BLOCK = 5
NSIM = 25000
MAXD = 252           # 'no time limit' -> allow up to a year of trading days
SEED = 20260606

# Card definitions: (name, phases=[(target,min_days)], daily_limit, total_limit, trailing?)
CARDS = {
    "ONE-STEP": dict(phases=[(0.10, 5)], daily=-0.04, total=-0.06, trailing=True),
    "TWO-STEP": dict(phases=[(0.10, 10), (0.05, 5)], daily=-0.05, total=-0.10, trailing=True),
}


def book_residuals(cols):
    """Return (sharpe_d, z residuals dict per pool). 2-sleeve combo matches prior opt script."""
    R = pd.read_parquet(SLEEVE3)[cols]
    iv = 1.0 / R[R.index < CUT].std().to_numpy()
    w = iv / iv.sum()
    b = pd.Series(R.to_numpy() @ w, index=R.index)
    pools = {}
    for lbl, bb in [("IS", b[b.index < CUT]), ("OOS", b[b.index >= CUT]), ("ALL", b)]:
        pools[lbl] = ((bb - bb.mean()) / bb.std()).to_numpy()
    return b.mean() / b.std(), pools


def boot(z, n, days, rng):
    out = np.empty((n, days))
    nb = days // BLOCK + 1
    st = rng.integers(0, len(z) - BLOCK, size=(n, nb))
    for p in range(n):
        out[p] = np.concatenate([z[s:s + BLOCK] for s in st[p]])[:days]
    return out


def vol_vec(policy, eq, peak, params, target):
    """Vectorized today's annual-vol target across all paths (arrays eq, peak at phase scope)."""
    base = params["base"]
    n = eq.shape[0]
    if policy in ("CONST", "DAILY_GOV"):
        return np.full(n, base)
    buf = params.get("buf", 0.04)
    hi = params.get("hi", base)
    lo = params.get("lo", base)
    if policy == "RAMP_UP":
        return np.where(eq >= 1 + buf, hi, lo)
    if policy == "DERISK":
        return np.where(eq >= 1 + buf, lo, hi)
    if policy == "LOCK_NEAR":
        return np.where(eq >= (1 + target) * 0.985, 0.01, base)
    return np.full(n, base)


def sim_phase(zp, sharpe_d, policy, params, target, min_days, daily, total, trailing):
    """Vectorized across paths: one loop over days, numpy ops across all NSIM paths."""
    n, ndays = zp.shape
    eq = np.ones(n)
    peak = np.ones(n)
    alive = np.ones(n, bool)
    passed = np.zeros(n, bool)
    gov = params.get("gov", -0.03)
    sqrt_ppy = np.sqrt(PPY)
    for d in range(ndays):
        vt = vol_vec(policy, eq, peak, params, target)
        sd = vt / sqrt_ppy
        ret = HAIRCUT * sharpe_d * sd + sd * zp[:, d]
        if policy == "DAILY_GOV":
            ret = np.maximum(ret, gov)
        # daily breach (only among still-alive, not-yet-passed)
        active = alive & ~passed
        daily_breach = active & (ret <= daily)
        alive &= ~daily_breach
        # apply return to those still active and not daily-breached
        upd = active & ~daily_breach
        eq = np.where(upd, eq * (1 + ret), eq)
        peak = np.maximum(peak, eq)
        breach_level = peak * (1 + total) if trailing else (1 + total)
        total_breach = upd & (eq <= breach_level)
        alive &= ~total_breach
        # pass check (need min_days)
        if (d + 1) >= min_days:
            newpass = alive & ~passed & (eq >= 1 + target)
            passed |= newpass
        if not (alive & ~passed).any():
            break
    return passed.mean()


def p_pass_card(zpaths, sharpe_d, policy, params, card):
    """P(pass all phases) = product of per-phase pass rates (independent fresh paths per phase)."""
    p_all = 1.0
    for i, (tg, md) in enumerate(card["phases"]):
        zp = zpaths[i]
        p_all *= sim_phase(zp, sharpe_d, policy, params, tg, md,
                           card["daily"], card["total"], card["trailing"])
    return p_all


def main():
    sharpe_d, pools = book_residuals(["crypto_trend", "crypto_funding"])
    ann = sharpe_d * np.sqrt(PPY)
    sim_ann = ann * HAIRCUT

    lines = ["# PROP-PASS sizing maximization — best constant vol vs best adaptive path-shaping", "",
             f"Edge = 2-sleeve combo (crypto_trend+crypto_funding, inverse-vol). Raw ALL-pool ann "
             f"Sharpe {ann:.2f}; haircut x{HAIRCUT} -> sim Sharpe ~{sim_ann:.2f}. Block-bootstrap "
             f"(block={BLOCK}, {NSIM} paths, seed {SEED}), positive skew preserved. EOD-only "
             f"(intraday breach risk understated -> DAILY_GOV models a self-halt).", ""]

    # Pre-generate phase paths per pool so all policies see the SAME bootstrap draws (fair compare).
    VOLS = [round(v, 3) for v in np.arange(0.05, 0.301, 0.01)]

    summary_best = {}  # (card, pool) -> dict

    for card_name, card in CARDS.items():
        lines += [f"## Card: {card_name} "
                  f"(target(s) {'/'.join(f'{t*100:.0f}%' for t,_ in card['phases'])}, "
                  f"daily {card['daily']*100:.0f}%, total {card['total']*100:.0f}% "
                  f"{'TRAILING' if card['trailing'] else 'static'})", ""]
        for pool_name in ("OOS", "IS", "ALL"):
            print(f"... {card_name} / {pool_name}", flush=True)
            z = pools[pool_name]
            # fresh paths per phase, fixed across policies
            n_phases = len(card["phases"])
            base_rng = np.random.default_rng(SEED + hash(card_name + pool_name) % 100000)
            zpaths = [boot(z, NSIM, MAXD, base_rng) for _ in range(n_phases)]

            # 1) CONST vol sweep -> ceiling
            const_curve = []
            for v in VOLS:
                p = p_pass_card(zpaths, sharpe_d, "CONST", {"base": v}, card)
                const_curve.append((v, p))
            best_const_v, best_const_p = max(const_curve, key=lambda x: x[1])

            # 2) Adaptive families, each gridded over its own params around the const optimum
            adaptive_results = {}
            grid_hi = [0.12, 0.16, 0.20, 0.24, 0.28]
            grid_lo = [0.05, 0.08, 0.12, 0.16]
            grid_buf = [0.02, 0.04, 0.06]

            # RAMP_UP / DERISK: search hi,lo,buf
            for fam in ("RAMP_UP", "DERISK"):
                best = (None, -1.0)
                for hi in grid_hi:
                    for lo in grid_lo:
                        for buf in grid_buf:
                            params = {"base": best_const_v, "hi": hi, "lo": lo, "buf": buf}
                            p = p_pass_card(zpaths, sharpe_d, fam, params, card)
                            if p > best[1]:
                                best = ((hi, lo, buf), p)
                adaptive_results[fam] = best

            # LOCK_NEAR: search base vol
            best = (None, -1.0)
            for v in VOLS:
                p = p_pass_card(zpaths, sharpe_d, "LOCK_NEAR", {"base": v}, card)
                if p > best[1]:
                    best = (v, p)
            adaptive_results["LOCK_NEAR"] = best

            # DAILY_GOV: search base vol x governor level
            best = (None, -1.0)
            for v in VOLS:
                for g in (-0.025, -0.03, -0.035, -0.04):
                    p = p_pass_card(zpaths, sharpe_d, "DAILY_GOV", {"base": v, "gov": g}, card)
                    if p > best[1]:
                        best = ((v, g), p)
            adaptive_results["DAILY_GOV"] = best

            lines += [f"### Residual pool: {pool_name}", "",
                      f"- **Best CONSTANT vol = {best_const_v*100:.0f}% -> P(pass) = "
                      f"{best_const_p*100:.1f}%** (the ceiling).",
                      "- Best adaptive per family (own params optimized):"]
            for fam, (par, p) in adaptive_results.items():
                lines.append(f"  - {fam}: P={p*100:.1f}% (params {par})")
            # full const curve compact
            curve_str = "  ".join(f"{v*100:.0f}%:{p*100:.0f}" for v, p in const_curve
                                  if int(round(v*100)) % 2 == 1)
            lines += [f"- CONST vol curve (P% by vol): {curve_str}", ""]

            summary_best[(card_name, pool_name)] = {
                "const_v": best_const_v, "const_p": best_const_p,
                "adaptive": adaptive_results,
            }

    # ---- Verdict ----
    lines += ["## Verdict (honest)", ""]
    # Focus on OOS (forward-relevant) for each card
    for card_name in CARDS:
        s = summary_best[(card_name, "OOS")]
        best_adapt_fam = max(s["adaptive"].items(), key=lambda kv: kv[1][1])
        adapt_p = best_adapt_fam[1][1]
        const_p = s["const_p"]
        lift = adapt_p - const_p
        verdict = ("NO adaptive scheme beats best constant vol" if lift <= 0.005
                   else f"{best_adapt_fam[0]} beats constant by {lift*100:+.1f} pts")
        lines.append(
            f"- **{card_name} (OOS pool):** best constant vol {s['const_v']*100:.0f}% -> "
            f"P(pass)={const_p*100:.1f}%; best adaptive ({best_adapt_fam[0]}) "
            f"P={adapt_p*100:.1f}% -> {verdict}.")
    lines += ["",
              "- The ONLY reliable lever is the VOL LEVEL: P(pass) rises with vol up to a peak, "
              "then falls as daily/total breaches dominate. Path-shaping (ramp/derisk/lock/"
              "governor) is compared at its OWN best params, not vs a fixed baseline.",
              "- Why de-risk/lock typically can't beat constant: the target is HIGH vs the edge, "
              "so you must compound at full risk to reach it before time/path runs out; trailing "
              "total-DD floor rises with the peak so a built buffer doesn't lower breach risk.",
              "- A DAILY_GOV (intraday -g% self-halt) is the one tweak that can help on EOD-"
              "understated daily risk: it converts would-be -5% closes into capped losses, "
              "letting you run slightly higher vol. Check the OOS numbers above for whether the "
              "lift clears noise on THIS edge.",
              "- ALL/IS pools cross-check regime: OOS (2025-26) is the kind window; the IS/ALL "
              "ceiling is the more conservative deployable expectation.",
              "- ⚠️ EOD-only understates -5%/-4% intraday daily breaches; 0.6 haircut; survivorship-"
              "capped universe; favorable OOS regime. 100% pass is impossible — these are ceilings."]

    report = "\n".join(lines)
    print(report)
    out = Path(__file__).resolve().parents[1] / "reports_out" / "propfirm_sizing.md"
    out.write_text(report)
    print(f"\nSaved -> {out}")


if __name__ == "__main__":
    main()
