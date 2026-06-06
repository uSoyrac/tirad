"""CRYPTO PROP-FIRM hedef seçimi — gerçek edge'imizi her firmanın TAM kurallarına karşı simüle et.

Our DSR/PBO-validated crypto combo (cross-sectional momentum Top-3 + funding-positioning carry)
DOES trade on crypto-native firms with real USDT perps (funding sleeve works there, unlike
FundingPips CFDs). This sizes that exact edge to each firm's rules — static vs EOD-TRAILING
drawdown, daily limit, min trading days, 1-step vs 2-step — and ranks which firm to attack.

Firms (from public 2026 rules):
  HyroTrader  : 700+ Bybit USDT perps. 1-step 10%/DD6%trail/daily4%/min10d;
                2-step 10%+5%/DD10%trail/daily5%/min10+5d. 80% split. EOD-trailing DD.
  Breakout    : 50+ crypto pairs. 1-step 10%/DD6% STATIC/daily4%. 80% split.
  FundedNext  : 8%+5%/DD10% static/daily5% (CFD crypto — funding sleeve weaker; caveat).

Monte-Carlo (block-bootstrap, honest survivorship haircut) the combo's daily returns at a
grid of vol targets; report P(pass all phases), funded blowup + expected payout. Pick the
firm × vol that maximizes get-funded × earn EV. Reports honestly.

Usage: python scripts/run_propfirm_multi.py
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
HAIRCUT, BLOCK, NSIM, MAXD, FUNDED_DAYS = 0.60, 5, 20000, 252, 21

# firm rule sets. phase = (target, daily_loss, total_dd, trailing, min_days)
FIRMS = {
    "HyroTrader 1-step": {"split": 0.80, "price": 279, "size": 25000, "trailing": True,
                          "phases": [(0.10, -0.04, -0.06, True, 10)]},
    "HyroTrader 2-step": {"split": 0.80, "price": 249, "size": 25000, "trailing": True,
                          "phases": [(0.10, -0.05, -0.10, True, 10), (0.05, -0.05, -0.10, True, 5)]},
    "Breakout 1-step": {"split": 0.80, "price": 200, "size": 25000, "trailing": False,
                        "phases": [(0.10, -0.04, -0.06, False, 0)]},
    "FundedNext 2-step": {"split": 0.80, "price": 200, "size": 25000, "trailing": False,
                          "phases": [(0.08, -0.05, -0.10, False, 0), (0.05, -0.05, -0.10, False, 0)]},
}


def _crypto_combo():
    R = pd.read_parquet(SLEEVE3)[["crypto_trend", "crypto_funding"]]
    Rtr = R[R.index < CUT]
    iv = 1.0 / Rtr.std().to_numpy()
    w = iv / iv.sum()
    return pd.Series(R.to_numpy() @ w, index=R.index)


def _bootstrap(z, n_paths, n_days, rng):
    out = np.empty((n_paths, n_days))
    nb = n_days // BLOCK + 1
    starts = rng.integers(0, len(z) - BLOCK, size=(n_paths, nb))
    for p in range(n_paths):
        out[p] = np.concatenate([z[s:s + BLOCK] for s in starts[p]])[:n_days]
    return out


def _sim_phase(paths, target, daily, total, trailing, min_days):
    """EOD model. Daily-loss breach, static/EOD-trailing total breach, min-days gate."""
    n = paths.shape[0]
    passed = np.zeros(n, bool)
    for p in range(n):
        eq, peak = 1.0, 1.0
        for d in range(paths.shape[1]):
            ret = paths[p, d]
            if ret <= daily:
                break
            eq *= (1 + ret)
            peak = max(peak, eq)
            floor = peak * (1 + total) if trailing else (1 + total)
            if eq <= floor:
                break
            if eq >= 1 + target and (d + 1) >= min_days:
                passed[p] = True
                break
    return passed.mean()


def _sim_funded(paths, daily, total, trailing, split, size):
    n = paths.shape[0]
    blow = np.zeros(n, bool)
    profit = np.zeros(n)
    for p in range(n):
        eq, peak = 1.0, 1.0
        for d in range(paths.shape[1]):
            ret = paths[p, d]
            if ret <= daily:
                blow[p] = True
                break
            eq *= (1 + ret)
            peak = max(peak, eq)
            floor = peak * (1 + total) if trailing else (1 + total)
            if eq <= floor:
                blow[p] = True
                break
        profit[p] = (eq - 1.0) if not blow[p] else total
    pay = np.where(profit > 0, profit * size * split, 0.0)
    return blow.mean(), float(np.mean(pay))


def main():
    book = _crypto_combo()
    mu_d, sd_d = book.mean(), book.std()
    sharpe_d = mu_d / sd_d
    z = ((book - mu_d) / sd_d).to_numpy()
    rng = np.random.default_rng(11)

    lines = ["# CRYPTO PROP-FIRM hedef seçimi — gerçek combo edge'imizle (trend+funding)", "",
             f"Edge = DSR/PBO-doğrulanmış crypto combo. Ham yıllık Sharpe ~{sharpe_d*np.sqrt(PPY):.2f}, "
             f"haircut ×{HAIRCUT} → sim ~{sharpe_d*np.sqrt(PPY)*HAIRCUT:.2f}. Block-bootstrap {NSIM} yol. "
             "Crypto-native firmalar (gerçek perp + funding) — edge BURADA çalışır (FundingPips'in aksine).", ""]

    summary = []
    for firm, cfg in FIRMS.items():
        lines += [f"## {firm}  (split {cfg['split']*100:.0f}%, ~${cfg['price']}, "
                  f"{'TRAILING' if cfg['trailing'] else 'STATİK'} DD)", "",
                  "| yıllık vol | P(tüm fazlar) | fon: P(ay patlama) | beklenen aylık $ |",
                  "|---|---|---|---|"]
        best = (0, 0.0, 1.0, 0.0)  # vol, p_all, blow, pay
        for vol in (0.03, 0.05, 0.07, 0.10, 0.15):
            sd = vol / np.sqrt(PPY)
            mu = HAIRCUT * sharpe_d * sd
            p_all = 1.0
            for (tg, dl, tot, tr, md) in cfg["phases"]:
                pth = mu + sd * _bootstrap(z, NSIM, MAXD, rng)
                p_all *= _sim_phase(pth, tg, dl, tot, tr, md)
            pf = mu + sd * _bootstrap(z, NSIM, FUNDED_DAYS, rng)
            ph = cfg["phases"][-1]
            blow, pay = _sim_funded(pf, ph[1], ph[2], ph[3], cfg["split"], cfg["size"])
            lines.append(f"| {vol*100:.0f}% | {p_all*100:.0f}% | {blow*100:.1f}% | ${pay:.0f} |")
            if p_all * pay > best[1] * best[3]:   # maximize get-funded prob x monthly payout
                best = (vol, p_all, blow, pay)
        # EV: expected cost to fund = price/p_all; monthly net once funded
        ev_cost = cfg["price"] / best[1] if best[1] > 0 else float("inf")
        summary.append((firm, best[0], best[1], best[2], best[3], ev_cost, cfg["price"]))
        lines.append("")

    lines += ["## SIRALAMA — hangi firmaya saldıralım (EV)", "",
              "| firma | en iyi vol | P(funded) | fon patlama/ay | aylık $ | funded olma maliyeti | challenge $ |",
              "|---|---|---|---|---|---|---|"]
    summary.sort(key=lambda r: (r[2] * r[4]) - r[5] / 6.0, reverse=True)  # ~6-month EV proxy
    for firm, vol, p_all, blow, pay, ev_cost, price in summary:
        lines.append(f"| {firm} | {vol*100:.0f}% | {p_all*100:.0f}% | {blow*100:.1f}% | ${pay:.0f} | "
                     f"${ev_cost:.0f} | ${price} |")

    top = summary[0]
    lines += ["", "## Yorum (dürüst)", "",
              f"- **En yüksek-EV hedef: {top[0]}** — ~%{top[1]*100:.0f} funded olma olasılığı "
              f"(~%{top[1]*100:.0f}'de ${top[6]} challenge geçilir → beklenen maliyet ~${top[5]:.0f}), "
              f"funded sonrası ~${top[4]:.0f}/ay (aylık patlama %{top[3]*100:.1f}). Önerilen vol ~%{top[1]*100:.0f}.",
              "- **TRAILING DD (HyroTrader) statikten daha zor:** zirveden geri-çekilme bile eler → "
              "trailing firmalarda DAHA düşük vol gerekir. Statik DD (Breakout) hedefe daha rahat yürür.",
              "- **Crypto-native = edge'imiz GERÇEK** (gerçek perp + funding; FundingPips'te imkansızdı). "
              "700+ coin (HyroTrader) bizim 20-44'ten fazla breadth → momentum kolu daha da güçlü olabilir.",
              "- ⚠️ Dürüst sınırlar: EOD modeli (intraday DD daha kötü → bota −%3 intraday self-stop); "
              "survivorship haircut; min-10-gün hedefi erken tutsan da riske maruz bırakır; gerçek perp "
              "funding/komisyon firmada biraz farklı. Önce küçük hesapla/paper, sonra ölçekle.",
              "- **Sonraki: seçilen firma için bot_xasset'in crypto-only + o firmanın vol-hedefli "
              "versiyonunu paketle.** Canlı emir/API kodu öncesi SOR."]
    report = "\n".join(lines)
    print(report)
    (Path(__file__).resolve().parents[1] / "reports_out" / "propfirm_multi.md").write_text(report)
    print("\nSaved -> reports_out/propfirm_multi.md")


if __name__ == "__main__":
    main()
