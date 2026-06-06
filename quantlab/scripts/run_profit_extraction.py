"""PROFIT-EXTRACTION / compound policy for a FUNDED prop account.

Question: ONCE FUNDED, when do you WITHDRAW (bank profit, reset bankroll growth) vs
COMPOUND (let the funded balance grow, risk more $ per trade) to MAXIMISE cumulative $
extracted over 6-12 months WITHOUT blowing the account?

This is the FUNDED-phase problem only (passing the challenge is a separate, solved
question — see run_propfirm_sizing.py: ~45% pass ceiling). Here we assume we ARE funded
and ask the bankroll-management policy.

Honest construction (project rules):
- Edge = the DSR/PBO-validated 3-sleeve crypto combo (crypto_trend + crypto_funding,
  inverse-vol weights FIT ON TRAIN <2025). sim returns HAIRCUT ×0.6 (survivorship) so
  sim Sharpe ~1.0, the conservative deployable level (NOT the inflated OOS 2.2).
- Funded rules modelled on HyroTrader real perps ($5K, 80% split):
    * 2-step funded card: trailing EOD max DD -10% (from peak EQUITY incl. unrealized),
      daily -5% instant fail.
    * 1-step funded card: trailing EOD max DD -6%, daily -4%.
  We use the 2-step funded card by default (looser DD = the realistic compounding game).
- Block-bootstrap (block=5) the haircut'd daily combo returns, vol-targeted, over a
  6mo and 12mo horizon, 20k paths. Report P(survive), expected/median $ extracted,
  blowup%, and $ left on the table.

KEY MECHANIC of profit extraction with a TRAILING drawdown:
- The DD floor trails the PEAK EQUITY. If you compound, the peak rises and the floor
  rises with it — a normal pullback can then breach the floor and kill the account.
- WITHDRAWING resets equity toward the baseline: it BANKS profit (locks the $ out of
  blowup reach) AND lowers the live peak so the trailing floor stops chasing. So
  withdrawing is not just income — it is the primary DD-survival lever on a trailing card.

Policies swept:
  - withdraw threshold T: whenever profit-above-baseline >= T% of account, withdraw the
    bankable portion (down to baseline). T in {3,5,8,12,20,100(=never/pure-compound)}.
  - vol target (proxy for Kelly fraction): {6,8,10,12,15}% annual.

Usage: python scripts/run_profit_extraction.py [card] [horizon_months] [npaths]
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
VOL_LB = 20
ACCOUNT = 5000.0
SPLIT = 0.80          # trader keeps 80%
BLOCK = 5
SEED = 7

CARDS = {
    # funded-phase drawdown rules (trailing EOD from peak equity)
    "2step": {"daily": -0.05, "trail_dd": -0.10},
    "1step": {"daily": -0.04, "trail_dd": -0.06},
}


def combo_haircut(keep=HAIRCUT):
    R = pd.read_parquet(SLEEVE3)[["crypto_trend", "crypto_funding"]]
    iv = 1.0 / R[R.index < CUT].std().to_numpy()
    w = iv / iv.sum()
    c = pd.Series(R.to_numpy() @ w, index=R.index)
    mu = c.mean()
    return (c - mu) + mu * keep      # shrink mean only -> Sharpe ~0.6x


def vol_target(r, target, lb=VOL_LB, maxlev=3.0):
    realized = r.rolling(lb).std().shift(1) * np.sqrt(PPY)
    return (r * (target / realized).clip(upper=maxlev).fillna(0.0)).dropna()


def block_bootstrap(arr, n_days, rng, block=BLOCK):
    out = np.empty(n_days)
    i = 0
    n = len(arr)
    while i < n_days:
        s = rng.integers(0, n - block)
        take = min(block, n_days - i)
        out[i:i + take] = arr[s:s + take]
        i += take
    return out


def simulate_path(rets, daily, trail_dd, withdraw_thr, account=ACCOUNT, split=SPLIT):
    """One funded-account path.
    Equity in account-units (1.0 = baseline $account). Trailing DD from peak equity.
    withdraw_thr = profit fraction above baseline that triggers a withdraw down to baseline.
    withdraw_thr >= 1.0 means NEVER withdraw (pure compound).
    Returns (survived: bool, dollars_extracted: float).
    """
    eq = 1.0
    peak = 1.0
    floor_anchor = 1.0   # the peak that the trailing floor follows
    extracted = 0.0
    for ret in rets:
        # daily-loss instant fail (EOD proxy)
        if ret <= daily:
            return False, extracted
        eq *= (1 + ret)
        peak = max(peak, eq)
        floor_anchor = max(floor_anchor, eq)
        # trailing max-DD breach
        if eq <= floor_anchor * (1 + trail_dd):
            return False, extracted
        # withdraw rule: bank profit above baseline when threshold reached
        profit = eq - 1.0
        if profit >= withdraw_thr:
            # bank the trader's split of the profit, reset equity to baseline
            extracted += profit * account * split
            eq = 1.0
            # trailing anchor resets too: withdrawing lowers the high-water mark
            floor_anchor = 1.0
            peak = 1.0
    return True, extracted


def run_grid(arr, card, horizon_days, npaths, withdraw_thrs, vols):
    rng = np.random.default_rng(SEED)
    daily, trail = CARDS[card]["daily"], CARDS[card]["trail_dd"]
    rows = []
    # pre-build vol-targeted return arrays (different vol => different sized stream)
    base = combo_haircut()
    sized = {v: vol_target(base, v).to_numpy() for v in vols}
    for v in vols:
        a = sized[v]
        for T in withdraw_thrs:
            surv = 0
            ext = np.empty(npaths)
            for p in range(npaths):
                path = block_bootstrap(a, horizon_days, rng)
                ok, dollars = simulate_path(path, daily, trail, T)
                if ok:
                    surv += 1
                ext[p] = dollars
            p_surv = surv / npaths
            rows.append(dict(
                vol=v, thr=T,
                p_survive=p_surv,
                blowup=1 - p_surv,
                exp_total=ext.mean(),
                median_total=np.median(ext),
                exp_monthly=ext.mean() / (horizon_days / 30.0),
                p10=np.percentile(ext, 10),
                p90=np.percentile(ext, 90),
            ))
    return pd.DataFrame(rows)


def main():
    card = sys.argv[1] if len(sys.argv) > 1 else "2step"
    horizon_m = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    npaths = int(sys.argv[3]) if len(sys.argv) > 3 else 20000
    horizon_days = int(horizon_m * 30.4)

    withdraw_thrs = [0.03, 0.05, 0.08, 0.12, 0.20, 1.00]  # 1.00 = never (pure compound)
    vols = [0.06, 0.08, 0.10, 0.12, 0.15]

    arr = combo_haircut()
    df = run_grid(arr, card, horizon_days, npaths, withdraw_thrs, vols)

    # find the policy maximising expected $ subject to P(survive) >= 0.80
    safe = df[df.p_survive >= 0.80].copy()
    best = safe.sort_values("exp_total", ascending=False).iloc[0] if len(safe) else None
    best_ev = df.sort_values("exp_total", ascending=False).iloc[0]

    def thr_lbl(t):
        return "never" if t >= 1.0 else f"{t*100:.0f}%"

    lines = [f"# PROFIT-EXTRACTION policy — funded {card} (HyroTrader $5K, 80% split)", "",
             f"Edge: DSR/PBO combo (trend+funding), haircut x{HAIRCUT} (sim Sharpe ~1.0). "
             f"Block-bootstrap (block={BLOCK}), {npaths} paths, horizon {horizon_m}mo "
             f"({horizon_days}d). Funded card: daily {CARDS[card]['daily']*100:.0f}%, "
             f"trailing DD {CARDS[card]['trail_dd']*100:.0f}% from peak equity.", "",
             "Withdraw threshold T = bank profit (80% split) down to baseline when equity is "
             "T above baseline; 'never' = pure compound. Vol = annual target (Kelly proxy).", "",
             "## Grid (P(survive) / blowup% / exp total $ / exp monthly $)", "",
             "| vol | withdraw | P(surv) | blowup | exp total $ | median $ | exp/mo $ | p10 | p90 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for _, r in df.iterrows():
        lines.append(
            f"| {r.vol*100:.0f}% | {thr_lbl(r.thr)} | {r.p_survive*100:.1f}% | "
            f"{r.blowup*100:.1f}% | ${r.exp_total:,.0f} | ${r.median_total:,.0f} | "
            f"${r.exp_monthly:,.0f} | ${r.p10:,.0f} | ${r.p90:,.0f} |")

    lines += ["", "## Best policy at P(survive) >= 80%", ""]
    if best is not None:
        lines.append(f"- **vol {best.vol*100:.0f}%, withdraw at {thr_lbl(best.thr)}**: "
                     f"P(survive) {best.p_survive*100:.1f}%, blowup {best.blowup*100:.1f}%, "
                     f"exp total ${best.exp_total:,.0f} (${best.exp_monthly:,.0f}/mo), "
                     f"median ${best.median_total:,.0f}.")
    else:
        lines.append("- No policy clears 80% survival — edge too thin for this card.")
    lines += ["", "## Unconstrained max-EV (ignores survival)", "",
              f"- vol {best_ev.vol*100:.0f}%, withdraw {thr_lbl(best_ev.thr)}: "
              f"exp ${best_ev.exp_total:,.0f}, but P(survive) only {best_ev.p_survive*100:.1f}% "
              f"(blowup {best_ev.blowup*100:.1f}%) — the greedy compound trap.", ""]

    report = "\n".join(lines)
    print(report)
    out = Path(__file__).resolve().parents[1] / "reports_out" / f"profit_extraction_{card}_{horizon_m}mo.md"
    out.write_text(report)
    print(f"\nSaved -> {out}")
    return df


if __name__ == "__main__":
    main()
