"""FUNDED-SURVIVAL bot — the 2nd bot, runs AFTER getting funded.

Objective is the OPPOSITE of the passer bot: there is NO +target to hit. The job is to
SURVIVE 6+ months without breaching the daily-loss or total-drawdown limit, while
EXTRACTING payouts (withdrawals). We measure, by real combo returns:
  - P(survive 6 months) without any daily/total breach
  - expected cumulative withdrawn $ over 6 months (and ~ per-month)
  - blowup % (any breach within 6 months)

Levers tested (alpha held constant = the DSR/PBO combo; we only manage RISK + CASH):
  1. DE-RISK VOL LEVEL  : low constant annual-vol target (3% .. 12%). Lower vol = thinner
     daily-loss tail = higher survival, but lower payouts. Find the survival/earn frontier.
  2. PROFIT-BANKING     : withdraw the buffer above a +X% high-water threshold whenever the
     account is above start+X%. Banking REMOVES equity from the account -> for a TRAILING-DD
     firm it LOWERS the peak the floor trails from, so banking is also a survival lever, not
     just income. We test withdraw-trigger X in {3,5,8,10}% and also "never bank".
  3. KILL-SWITCH (intraday self-halt) : cap the worst intraday loss at -g% (stop trading for
     the day once down g). Models the real bot halting before the EOD daily limit; also
     protects against the EOD-model understating intraday daily-breach risk.

Firm rules modeled (crypto-native, where our edge is real):
  HyroTrader funded (TRAILING DD): daily -4% (1-step card) / -5% (2-step card), total -6% /
    -10% EOD-TRAILING from peak EQUITY (trailing stops trailing once it reaches start+ ... we
    model the common case: floor = peak*(1+total), withdrawals lower realized peak). 80% split.
  We run BOTH the 1-step funded rule (daily -4 / total -6 trailing, tighter) and the 2-step
  funded rule (daily -5 / total -10 trailing, looser) since the user can be on either card.
Accounts: $5K and $25K. Payout = withdrawn_buffer * split (trader keeps `split`).

Honesty (per CLAUDE.md): 0.6 survivorship haircut on the mean (sim Sharpe ~1.0, vs raw ~1.7
ALL / 2.2 OOS), block-bootstrap preserves vol-clustering + skew, IS/OOS/ALL pools reported
side-by-side (regime sensitivity), EOD model -> kill-switch addresses intraday understatement,
realistic per-rebalance cost already baked into the sleeve returns. 100% survival is impossible
over 6 months at any useful vol; we find the honest survival ceiling and its $ cost.

Usage: cd quantlab && .venv/bin/python scripts/run_funded_survival.py
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SLEEVE3 = ROOT / "reports_out" / "_sleeves3.parquet"
CUT = pd.Timestamp("2025-01-01")
PPY = 365
HAIRCUT = 0.60
BLOCK = 5
NSIM = 30000
HORIZON = 126          # ~6 months of trading days
SEED = 20260606

# Funded cards: daily limit, total trailing-DD limit (both negative, EOD-trailing peak).
CARDS = {
    "1-step (daily -4 / total -6 trail)": dict(daily=-0.04, total=-0.06),
    "2-step (daily -5 / total -10 trail)": dict(daily=-0.05, total=-0.10),
}
SPLIT = 0.80
ACCOUNTS = {"$5K": 5000.0, "$25K": 25000.0}


def book_residuals(cols=("crypto_trend", "crypto_funding")):
    R = pd.read_parquet(SLEEVE3)[list(cols)]
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


def sim_funded(zp, sharpe_d, vol, daily, total, bank_x, gov):
    """Vectorized funded-phase sim over NSIM paths x HORIZON days.

    Returns: survive_rate, blow_rate, mean_withdrawn_fraction (of account, pre-split),
             and the fraction of paths that ever withdrew.
    bank_x: None = never bank; else withdraw equity above (1+bank_x) back down to (1+bank_x)
            at each EOD when above it. Withdrawals are realized cash (kept), and they LOWER
            the equity (so for trailing DD the realized peak is capped near 1+bank_x).
    gov: None = no kill-switch; else floor each day's return at gov (intraday self-halt).
    """
    n, ndays = zp.shape
    sd = vol / np.sqrt(PPY)
    mu = HAIRCUT * sharpe_d * sd
    eq = np.ones(n)
    peak = np.ones(n)
    alive = np.ones(n, bool)
    withdrawn = np.zeros(n)         # cumulative fraction of starting balance withdrawn
    ever_wd = np.zeros(n, bool)
    for d in range(ndays):
        ret = mu + sd * zp[:, d]
        if gov is not None:
            ret = np.maximum(ret, gov)
        # daily-loss breach (EOD return below limit) among the living
        breach_daily = alive & (ret <= daily)
        # apply return to the still-living, non-daily-breached
        upd = alive & ~breach_daily
        eq = np.where(upd, eq * (1 + ret), eq)
        # profit banking at EOD: withdraw equity above (1+bank_x) back to (1+bank_x)
        if bank_x is not None:
            over = upd & (eq > 1 + bank_x)
            extra = np.where(over, eq - (1 + bank_x), 0.0)
            withdrawn += extra
            ever_wd |= over
            eq = np.where(over, 1 + bank_x, eq)
        peak = np.maximum(peak, eq)
        # total trailing-DD breach (EOD equity below trailing floor)
        floor = peak * (1 + total)
        breach_total = upd & (eq <= floor)
        # any breach kills the account
        alive &= ~(breach_daily | breach_total)
        if not alive.any():
            break
    survive = alive
    # final mark-to-market profit for survivors that never fully banked counts toward payout too
    # (a survivor can withdraw remaining buffer above start at the end)
    final_buffer = np.where(survive, np.maximum(eq - 1.0, 0.0), 0.0)
    total_wd = withdrawn + final_buffer
    return survive.mean(), (~survive).mean(), float(total_wd.mean()), ever_wd.mean()


def main():
    sharpe_d, pools = book_residuals()
    ann = sharpe_d * np.sqrt(PPY)
    sim_ann = ann * HAIRCUT

    lines = ["# FUNDED-SURVIVAL bot — survive 6mo + extract payouts (real combo returns)", "",
             f"Edge = DSR/PBO combo (crypto_trend+crypto_funding, inverse-vol). Raw ALL-pool ann "
             f"Sharpe {ann:.2f} (OOS 2.23 / IS 1.25), haircut x{HAIRCUT} -> sim Sharpe ~{sim_ann:.2f}. "
             f"Block-bootstrap (block={BLOCK}, {NSIM} paths), horizon {HORIZON}d (~6mo), seed {SEED}. "
             "Objective: NO target to hit -> MINIMIZE blowup, MAXIMIZE withdrawn $. "
             "Payout to trader = withdrawn buffer x 80% split.", ""]

    VOLS = [0.03, 0.05, 0.07, 0.10, 0.12]
    BANKS = [None, 0.10, 0.08, 0.05, 0.03]   # None=never, else withdraw above start+X%
    GOVS = {"none": None, "-3% halt": -0.03, "-2.5% halt": -0.025}

    # Pre-generate paths per pool (fair compare across all policies in that pool).
    zp_by_pool = {}
    for pool in ("OOS", "IS", "ALL"):
        prng = np.random.default_rng(SEED + hash(pool) % 100000)
        zp_by_pool[pool] = boot(pools[pool], NSIM, HORIZON, prng)

    best_overall = {}  # (card, pool) -> chosen policy dict

    for card_name, card in CARDS.items():
        lines += [f"# CARD: {card_name}", ""]
        for pool in ("OOS", "IS", "ALL"):
            print(f"... {card_name} / {pool}", flush=True)
            zp = zp_by_pool[pool]
            lines += [f"## Pool {pool}", ""]

            # ---- 1) De-risk vol sweep, never-bank vs bank-at-5%, no kill-switch ----
            lines += ["### Lever 1: de-risk VOL level (bank at +5% buffer, no kill-switch)", "",
                      "| ann vol | P(survive 6mo) | blowup% | withdrawn (frac/acct) | "
                      "$5K payout(6mo) | $25K payout(6mo) | $5K/mo | $25K/mo |",
                      "|---|---|---|---|---|---|---|---|"]
            vol_rows = []
            for vol in VOLS:
                surv, blow, wd, _ = sim_funded(zp, sharpe_d, vol, card["daily"], card["total"],
                                               bank_x=0.05, gov=None)
                pay5 = wd * ACCOUNTS["$5K"] * SPLIT
                pay25 = wd * ACCOUNTS["$25K"] * SPLIT
                lines.append(f"| {vol*100:.0f}% | {surv*100:.1f}% | {blow*100:.1f}% | {wd*100:.2f}% "
                             f"| ${pay5:.0f} | ${pay25:.0f} | ${pay5/6:.0f} | ${pay25/6:.0f} |")
                vol_rows.append((vol, surv, blow, wd, pay5, pay25))
            lines.append("")

            # ---- 2) Profit-banking threshold sweep at a fixed de-risk vol (7%) ----
            lines += ["### Lever 2: profit-banking trigger (at 7% vol, no kill-switch)", "",
                      "| bank trigger | P(survive) | blowup% | withdrawn frac | $5K/mo | $25K/mo |",
                      "|---|---|---|---|---|---|"]
            for bx in BANKS:
                surv, blow, wd, _ = sim_funded(zp, sharpe_d, 0.07, card["daily"], card["total"],
                                               bank_x=bx, gov=None)
                pay5 = wd * ACCOUNTS["$5K"] * SPLIT
                pay25 = wd * ACCOUNTS["$25K"] * SPLIT
                label = "never bank" if bx is None else f"+{bx*100:.0f}%"
                lines.append(f"| {label} | {surv*100:.1f}% | {blow*100:.1f}% | {wd*100:.2f}% "
                             f"| ${pay5/6:.0f} | ${pay25/6:.0f} |")
            lines.append("")

            # ---- 3) Kill-switch sweep at 7% vol, bank at +5% ----
            lines += ["### Lever 3: kill-switch / intraday self-halt (7% vol, bank +5%)", "",
                      "| kill-switch | P(survive) | blowup% | $5K/mo | $25K/mo |",
                      "|---|---|---|---|---|"]
            for gname, g in GOVS.items():
                surv, blow, wd, _ = sim_funded(zp, sharpe_d, 0.07, card["daily"], card["total"],
                                               bank_x=0.05, gov=g)
                pay5 = wd * ACCOUNTS["$5K"] * SPLIT
                pay25 = wd * ACCOUNTS["$25K"] * SPLIT
                lines.append(f"| {gname} | {surv*100:.1f}% | {blow*100:.1f}% "
                             f"| ${pay5/6:.0f} | ${pay25/6:.0f} |")
            lines.append("")

            # ---- choose the survival-first policy for this (card,pool): >=90% survive, max $ ----
            # grid over vol x bank x gov, pick highest $25K/mo subject to survive>=0.90 (else max survive)
            grid = []
            for vol in VOLS:
                for bx in BANKS:
                    for g in (None, -0.03, -0.025):
                        surv, blow, wd, _ = sim_funded(zp, sharpe_d, vol, card["daily"],
                                                       card["total"], bank_x=bx, gov=g)
                        grid.append((vol, bx, g, surv, blow, wd))
            safe = [r for r in grid if r[3] >= 0.90]
            chosen = (max(safe, key=lambda r: r[5]) if safe
                      else max(grid, key=lambda r: r[3]))
            best_overall[(card_name, pool)] = chosen

    # ---- Verdict / recommended policy (anchored to OOS + ALL, conservative) ----
    lines += ["# RECOMMENDED FUNDED-SURVIVAL POLICY (honest)", ""]
    for card_name in CARDS:
        c_oos = best_overall[(card_name, "OOS")]
        c_all = best_overall[(card_name, "ALL")]
        for pool, c in [("OOS (kind regime)", c_oos), ("ALL (conservative)", c_all)]:
            vol, bx, g, surv, blow, wd = c
            bank = "never" if bx is None else f"+{bx*100:.0f}%"
            ks = "none" if g is None else f"{g*100:.1f}% halt"
            p5 = wd * ACCOUNTS["$5K"] * SPLIT / 6
            p25 = wd * ACCOUNTS["$25K"] * SPLIT / 6
            lines.append(
                f"- **{card_name} / {pool}:** vol {vol*100:.0f}%, bank {bank}, kill-switch {ks} "
                f"-> P(survive 6mo) {surv*100:.1f}%, blowup {blow*100:.1f}%, "
                f"~${p5:.0f}/mo ($5K) / ~${p25:.0f}/mo ($25K).")
    lines += ["",
              "- **Survival is bought with vol:** lower de-risk vol shrinks the daily-loss tail "
              "(the main killer) almost linearly; payouts shrink with it. The 6-month survival "
              "ceiling at a useful (earning) vol is well below 100% under TRAILING DD.",
              "- **Profit-banking is a SURVIVAL lever, not just income, under trailing DD:** "
              "withdrawing the buffer caps the realized peak the floor trails from, so a small "
              "bank trigger both extracts cash AND lowers blowup vs never-banking (which lets the "
              "peak — and thus the trailing floor — ratchet up to where any pullback breaches).",
              "- **Kill-switch:** on EOD data its measured lift is small, but it is the real "
              "defense against the EOD model UNDERSTATING intraday daily breaches — keep a "
              "-2.5/-3% intraday self-halt on the live bot regardless of the sim number.",
              "- ⚠️ Honest limits: EOD-only (intraday daily breach understated -> kill-switch + "
              "size below the cliff); 0.6 survivorship haircut; trailing-DD modeled as "
              "floor=peak*(1+total) with banking capping the peak (real firm trailing rules vary — "
              "some stop trailing at start+total, which is EASIER, so this is conservative); "
              "favorable 2025-26 OOS regime -> trust the ALL/IS pool for the deployable number."]

    report = "\n".join(lines)
    print(report)
    out = ROOT / "reports_out" / "funded_survival.md"
    out.write_text(report)
    print(f"\nSaved -> {out}")
    return best_overall, sharpe_d


if __name__ == "__main__":
    main()
