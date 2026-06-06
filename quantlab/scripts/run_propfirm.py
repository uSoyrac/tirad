"""PROP-FIRM challenge simulator on our REAL (DSR/PBO-confirmed) edge — the 2-bot answer.

Card rules: Phase1 +8% target, Phase2 +5% target, max TOTAL loss 10%, max DAILY loss 5%
(instant fail), 80% biweekly payout. These are PATH-DEPENDENT kill constraints — a high
Sharpe is NOT enough; what matters is P(reach target before a -5% day or -10% total).

We take the 3-sleeve book's daily returns (bot_xasset, _sleeves3.parquet), scale to a grid
of annual vol targets, apply an HONEST survivorship haircut to the mean (the OOS Sharpe is
inflated), then Monte-Carlo each challenge via BLOCK BOOTSTRAP (preserves vol-clustering /
fat tails that drive breach probability). Reports, per vol target:
  * P(pass Phase1 +8%), P(pass Phase2 +5%), P(pass BOTH), median days-to-pass
  * how each failure happens (daily-5% vs total-10%)
  * funded: P(blowup in a month) + expected monthly payout on $5K (80% split)

Answer = ONE edge at TWO risk settings: an aggressive 'passer' vol + a conservative 'funded' vol.

HONEST LIMITS (stated): (1) only EOD daily data → intraday lows are WORSE than close, so the
true -5% daily breach risk is HIGHER than modeled; we report daily-vol + P(day<=-3%) as the
intraday-proximity warning and recommend a -3% intraday self-halt. (2) Our edge is crypto+US;
if the prop firm is forex/futures-only this profile doesn't transfer (we have no validated
forex edge). (3) survivorship haircut applied but magnitude still uncertain.

Usage: python scripts/run_propfirm.py
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
PPY = 252
SLEEVE3 = Path(__file__).resolve().parents[1] / "reports_out" / "_sleeves3.parquet"

# challenge rules (from the card)
P1_TARGET, P2_TARGET = 0.08, 0.05
MAX_TOTAL, MAX_DAILY = -0.10, -0.05
PAYOUT_SPLIT = 0.80
ACCOUNT = 5000.0

HAIRCUT = 0.60          # keep 60% of the (inflated) OOS Sharpe — honest survivorship discount
BLOCK = 5               # block-bootstrap length (preserves vol clustering)
NSIM = 30000
MAXD_PHASE = 252        # 'no time limit' card → allow up to a year of trading days to pass
FUNDED_DAYS = 21        # ~1 trading month for the funded payout estimate
RNG_SEED_BASE = 12345   # deterministic (Math.random unavailable; vary by index)


def _book_daily():
    R = pd.read_parquet(SLEEVE3)
    Rtr = R[R.index < CUT]
    iv = 1.0 / Rtr.std().to_numpy()
    w = iv / iv.sum()
    return pd.Series(R.to_numpy() @ w, index=R.index)


def _bootstrap_paths(z, n_paths, n_days, rng):
    """Block-bootstrap standardized residuals z into (n_paths, n_days)."""
    out = np.empty((n_paths, n_days))
    nb = n_days // BLOCK + 1
    starts = rng.integers(0, len(z) - BLOCK, size=(n_paths, nb))
    for p in range(n_paths):
        chunks = [z[s:s + BLOCK] for s in starts[p]]
        out[p] = np.concatenate(chunks)[:n_days]
    return out


def _sim_phase(paths_ret, target):
    """Vectorized-ish phase sim. Returns (pass_rate, fail_daily, fail_total, median_days)."""
    n = paths_ret.shape[0]
    passed = np.zeros(n, bool)
    fail_daily = np.zeros(n, bool)
    fail_total = np.zeros(n, bool)
    days = np.full(n, MAXD_PHASE)
    for p in range(n):
        eq = 1.0
        for d, ret in enumerate(paths_ret[p]):
            if ret <= MAX_DAILY:
                fail_daily[p] = True
                days[p] = d + 1
                break
            eq *= (1 + ret)
            if eq <= (1 + MAX_TOTAL):
                fail_total[p] = True
                days[p] = d + 1
                break
            if eq >= (1 + target):
                passed[p] = True
                days[p] = d + 1
                break
    md = int(np.median(days[passed])) if passed.any() else -1
    return passed.mean(), fail_daily.mean(), fail_total.mean(), md


def _sim_funded(paths_ret):
    """Over FUNDED_DAYS: P(blowup) and expected payout ($) on ACCOUNT with 80% split."""
    n = paths_ret.shape[0]
    blow = np.zeros(n, bool)
    profit = np.zeros(n)
    for p in range(n):
        eq = 1.0
        for ret in paths_ret[p]:
            if ret <= MAX_DAILY:
                blow[p] = True
                break
            eq *= (1 + ret)
            if eq <= (1 + MAX_TOTAL):
                blow[p] = True
                break
        profit[p] = (eq - 1.0) if not blow[p] else MAX_TOTAL
    payout = np.where(profit > 0, profit * ACCOUNT * PAYOUT_SPLIT, 0.0)
    return blow.mean(), float(np.mean(payout)), float(np.median(profit) * ACCOUNT)


def main():
    book = _book_daily()
    mu_d, sd_d = book.mean(), book.std()
    sharpe_d = mu_d / sd_d
    z = ((book - mu_d) / sd_d).to_numpy()  # standardized residuals (shape, fat tails)
    rng = np.random.default_rng(RNG_SEED_BASE)

    lines = ["# PROP-FIRM challenge — gerçek edge'imizle simülasyon (2-bot cevabı)", "",
             f"Kitap = 3-sleeve (bot_xasset) günlük getiri. Ham yıllık Sharpe ~{sharpe_d*np.sqrt(PPY):.2f}; "
             f"DÜRÜST haircut ×{HAIRCUT} (survivorship) → sim Sharpe ~{sharpe_d*np.sqrt(PPY)*HAIRCUT:.2f}. "
             f"Block-bootstrap (blok={BLOCK}, {NSIM} yol). Kurallar: P1 +8%, P2 +5%, günlük {MAX_DAILY*100:.0f}% "
             f"& toplam {MAX_TOTAL*100:.0f}% = elenme.", "",
             "## Vol-hedefine göre (haircut'lı, dürüst)", "",
             "| yıllık vol | günlük vol | P(P1 +8%) | P(P2 +5%) | **P(İKİSİ)** | medyan gün(P1) | "
             "P1 elenme: günlük/toplam | P(gün≤−3%)* |", "|---|---|---|---|---|---|---|---|"]

    rows = []
    for vol_ann in (0.03, 0.05, 0.07, 0.10, 0.12, 0.15):
        sigma_d = vol_ann / np.sqrt(PPY)
        mu_sim = HAIRCUT * sharpe_d * sigma_d            # haircut Sharpe at this vol
        # phase paths
        zz = _bootstrap_paths(z, NSIM, MAXD_PHASE, rng)
        ret = mu_sim + sigma_d * zz
        p1, fd1, ft1, md1 = _sim_phase(ret, P1_TARGET)
        zz2 = _bootstrap_paths(z, NSIM, MAXD_PHASE, rng)
        ret2 = mu_sim + sigma_d * zz2
        p2, _, _, _ = _sim_phase(ret2, P2_TARGET)
        p_both = p1 * p2
        p_day3 = float((ret <= -0.03).any(axis=1).mean())  # intraday-proximity warning
        rows.append((vol_ann, sigma_d, p1, p2, p_both, md1, fd1, ft1, p_day3))
        lines.append(f"| {vol_ann*100:.0f}% | {sigma_d*100:.2f}% | {p1*100:.0f}% | {p2*100:.0f}% | "
                     f"**{p_both*100:.0f}%** | {md1} | {fd1*100:.0f}%/{ft1*100:.0f}% | {p_day3*100:.0f}% |")

    # pick passer vol = max P(both)
    passer = max(rows, key=lambda r: r[4])

    lines += ["", "*P(gün≤−3%): bir challenge boyunca en az bir günün ≤−3% kapanma olasılığı — "
              "intraday daha kötü olabilir, −5% uçurumuna yakınlık uyarısı.", "",
              "## Fon İÇİ (geçtikten sonra — patlamadan maaş)", "",
              f"~1 ay ({FUNDED_DAYS} işlem günü), $5K hesap, %80 split:", "",
              "| yıllık vol | P(ayda patlama) | beklenen aylık ödeme | medyan aylık kâr |",
              "|---|---|---|---|"]
    funded_rows = []
    for vol_ann in (0.03, 0.05, 0.07, 0.10, 0.12, 0.15):
        sigma_d = vol_ann / np.sqrt(PPY)
        mu_sim = HAIRCUT * sharpe_d * sigma_d
        zz = _bootstrap_paths(z, NSIM, FUNDED_DAYS, rng)
        ret = mu_sim + sigma_d * zz
        blow, exp_pay, med_profit = _sim_funded(ret)
        funded_rows.append((vol_ann, blow, exp_pay))
        lines.append(f"| {vol_ann*100:.0f}% | {blow*100:.1f}% | ${exp_pay:.0f} | ${med_profit:.0f} |")
    # funded pick = best expected payout * (1-blow)
    funded = max(funded_rows, key=lambda r: r[2] * (1 - r[1]))

    lines += ["", "## 2-BOT TAVSİYESİ (dürüst)", "",
              f"- **BOT A — GEÇİCİ (challenge passer): ~%{passer[0]*100:.0f} yıllık vol-hedef.** "
              f"P(her iki faz) ≈ **%{passer[4]*100:.0f}**, P1 medyan ~{passer[5]} işlem günü. Tek bir "
              "edge, agresif risk ayarı; hedefi günlük/toplam limiti çiğnemeden yakalama olasılığını "
              "maksimize eder.",
              f"- **BOT B — FON İÇİ (funded earner): ~%{funded[0]*100:.0f} yıllık vol-hedef.** "
              f"P(ayda patlama) ≈ %{funded[1]*100:.1f}, beklenen aylık ödeme ~${funded[2]:.0f} "
              "($5K, %80 split). Düşük risk; hesabı koru, maaşı al.",
              "- **İkisi de AYNI kanıtlı edge (bot_xasset 3-sleeve) — sadece vol-hedef farklı.** "
              "Gemini'nin 06-10 prop botları doğru kuralları hedefliyor ama backtest'leri güvenilmez "
              "(look-ahead, liquidation yok, XGBoost AUC~0.52); bizimki DSR 1.00/PBO 0.01 ile gerçek.",
              "- ⚠️ **Kritik uyarılar:** (1) Sadece EOD veri → gerçek günlük-%5 ihlali modellenenden "
              "YÜKSEK; bota **−%3 intraday self-stop** koy. (2) Edge crypto+US; prop firma SADECE "
              "forex/futures ise bu profil transfer OLMAZ (doğrulanmış forex edge'imiz yok). (3) Önce "
              "PAPER, sonra küçük. Canlı emir kodu öncesi SOR."]
    report = "\n".join(lines)
    print("\n" + report)
    out = Path(__file__).resolve().parents[1] / "reports_out" / "propfirm.md"
    out.write_text(report)
    print(f"\nSaved -> {out}")


if __name__ == "__main__":
    main()
