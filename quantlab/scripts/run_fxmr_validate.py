"""Validate FX-MR-1d (the first FundingPips-native candidate) — cost-stress + prop-sim.

FX-MR-1d showed OOS Sharpe 1.67 / IS +0.60 / 8-of-12 years positive. Before trusting it for a
real challenge we must: (1) COST-STRESS it (1-day reversal is high-turnover — does the edge
survive realistic FX/CFD spreads?), and (2) run the PROP MONTE-CARLO at vol targets that
respect the −10% total / −5% daily limits (its raw OOS DD was −10%, at the cliff).

If it survives higher costs AND a vol-targeted version passes with decent probability while
keeping blowup low, FX-MR-1d is a genuine FundingPips bot candidate. Reports honestly either way.

Usage: python scripts/run_fxmr_validate.py
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
MR_UNIVERSE = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "USDCHF=X",
               "NZDUSD=X", "^GSPC", "^NDX", "^GDAXI", "GC=F", "SI=F"]
# prop rules
P1_TARGET, P2_TARGET, MAX_TOTAL, MAX_DAILY = 0.08, 0.05, -0.10, -0.05
PAYOUT_SPLIT, ACCOUNT = 0.80, 5000.0
HAIRCUT, BLOCK, NSIM, MAXD, FUNDED_DAYS = 0.65, 5, 30000, 252, 21


def _sharpe(r):
    return float(r.mean() / r.std() * np.sqrt(PPY)) if r.std() > 0 else float("nan")


def _load():
    import yfinance as yf
    raw = yf.download(MR_UNIVERSE, start="2015-01-01", end="2026-06-01", interval="1d",
                      progress=False, auto_adjust=True)
    out = {}
    for t in MR_UNIVERSE:
        try:
            c = raw["Close"][t].dropna()
        except Exception:  # noqa: BLE001
            continue
        if len(c) > 600:
            out[t] = c
    px = pd.DataFrame(out).dropna()
    px.index = pd.DatetimeIndex(px.index).as_unit("ns")
    return px


def mr_book(px, lookback=1, cost=0.0003):
    rets = px.pct_change()
    past = px.pct_change(lookback)
    z = past.sub(past.mean(axis=1), axis=0).div(past.std(axis=1) + 1e-9, axis=0)
    w = (-z).shift(1)
    w = w.div(w.abs().sum(axis=1) + 1e-9, axis=0)
    turn = w.diff().abs().sum(axis=1).fillna(0.0)
    return ((w * rets).sum(axis=1) - cost * turn).dropna()


def _bootstrap(z, n_paths, n_days, rng):
    out = np.empty((n_paths, n_days))
    nb = n_days // BLOCK + 1
    starts = rng.integers(0, len(z) - BLOCK, size=(n_paths, nb))
    for p in range(n_paths):
        out[p] = np.concatenate([z[s:s + BLOCK] for s in starts[p]])[:n_days]
    return out


def _phase(paths, target):
    n = paths.shape[0]
    passed = np.zeros(n, bool)
    for p in range(n):
        eq = 1.0
        for ret in paths[p]:
            if ret <= MAX_DAILY:
                break
            eq *= (1 + ret)
            if eq <= 1 + MAX_TOTAL:
                break
            if eq >= 1 + target:
                passed[p] = True
                break
    return passed.mean()


def _funded(paths):
    n = paths.shape[0]
    blow = np.zeros(n, bool)
    profit = np.zeros(n)
    for p in range(n):
        eq = 1.0
        for ret in paths[p]:
            if ret <= MAX_DAILY:
                blow[p] = True
                break
            eq *= (1 + ret)
            if eq <= 1 + MAX_TOTAL:
                blow[p] = True
                break
        profit[p] = (eq - 1.0) if not blow[p] else MAX_TOTAL
    pay = np.where(profit > 0, profit * ACCOUNT * PAYOUT_SPLIT, 0.0)
    return blow.mean(), float(np.mean(pay))


def main():
    print("FX verisi yükleniyor + FX-MR-1d maliyet-stresi...")
    px = _load()
    lines = ["# FX-MR-1d doğrulama — maliyet-stresi + prop simülatörü", "",
             "## 1) Maliyet-stresi (1-günlük reversal yüksek turnover — edge dayanıyor mu?)", "",
             "| maliyet (bps/turnover) | OOS Sharpe | OOS CAGR |", "|---|---|---|"]
    base = None
    for c in (0.0003, 0.0006, 0.0010, 0.0015, 0.0020):
        r = mr_book(px, 1, c)
        oos = r[r.index >= CUT]
        eq = (1 + oos).cumprod().iloc[-1] ** (PPY / len(oos)) - 1
        lines.append(f"| {c*1e4:.0f} | {_sharpe(oos):.2f} | {eq*100:.0f}% |")
        if c == 0.0006:
            base = r  # use a realistic 6bps version for the prop sim
    book = base
    mu_d, sd_d = book.mean(), book.std()
    sharpe_d = mu_d / sd_d
    z = ((book - mu_d) / sd_d).to_numpy()
    rng = np.random.default_rng(7)

    lines += ["", f"## 2) Prop simülatörü (6bps versiyon, haircut ×{HAIRCUT}, $5K, kurallar "
              f"+8%/+5%, günlük −5%/toplam −10%)", "",
              f"Ham yıllık Sharpe ~{sharpe_d*np.sqrt(PPY):.2f} → sim ~{sharpe_d*np.sqrt(PPY)*HAIRCUT:.2f}. "
              "Düşük vol-hedef ŞART (ham OOS DD −10% = limitte).", "",
              "| yıllık vol | P(P1+8%) | P(P2+5%) | **P(İKİSİ)** | fon: P(ay patlama) | beklenen aylık $ |",
              "|---|---|---|---|---|---|"]
    rows = []
    for vol in (0.03, 0.05, 0.07, 0.10):
        sd = vol / np.sqrt(PPY)
        mu = HAIRCUT * sharpe_d * sd
        p1 = _phase(mu + sd * _bootstrap(z, NSIM, MAXD, rng), P1_TARGET)
        p2 = _phase(mu + sd * _bootstrap(z, NSIM, MAXD, rng), P2_TARGET)
        blow, pay = _funded(mu + sd * _bootstrap(z, NSIM, FUNDED_DAYS, rng))
        rows.append((vol, p1 * p2, blow, pay))
        lines.append(f"| {vol*100:.0f}% | {p1*100:.0f}% | {p2*100:.0f}% | **{p1*p2*100:.0f}%** | "
                     f"{blow*100:.1f}% | ${pay:.0f} |")
    passer = max(rows, key=lambda r: r[1])
    funded = max(rows, key=lambda r: r[3] * (1 - r[2]))

    oos6 = book[book.index >= CUT]
    lines += ["", "## Yorum (dürüst)", ""]
    surv = _sharpe(oos6) >= 0.8
    if surv and passer[1] >= 0.5:
        lines.append(f"**FX-MR-1d gerçek bir FundingPips adayı.** 6bps maliyette bile OOS Sharpe "
                     f"{_sharpe(oos6):.2f}; prop-sim'de ~%{passer[0]*100:.0f} vol-hedefte P(iki faz) "
                     f"≈ %{passer[1]*100:.0f}, fon-içi patlama düşük. **2-bot: passer ~%{passer[0]*100:.0f} "
                     f"vol, funded ~%{funded[0]*100:.0f} vol (~${funded[3]:.0f}/ay).** Sonraki: DSR/PBO, "
                     "sonra MT5/cTrader'da PAPER. ⚠️ 1-gün reversal = günlük rebalance, intraday "
                     "execution + −3% self-stop şart; gerçek CFD spread'i 6bps'i aşarsa edge zayıflar.")
    elif surv:
        lines.append(f"**Edge maliyete dayanıyor (OOS {_sharpe(oos6):.2f}) ama prop pass-prob düşük "
                     f"(en iyi %{passer[1]*100:.0f}).** Hedefe ulaşmadan limit riski; daha uzun "
                     "horizon/daha düşük vol gerek. Umut var ama henüz net 'geçer' değil.")
    else:
        lines.append(f"**Maliyet edge'i öldürüyor (6bps'te OOS Sharpe {_sharpe(oos6):.2f}).** 1-günlük "
                     "reversal'ın görünür edge'i turnover maliyetine dayanmıyor — gerçekçi CFD "
                     "spread'inde kaybolur. Dürüst sonuç: bu da güvenilir değil. Challenge alma.")
    report = "\n".join(lines)
    print("\n" + report)
    out = Path(__file__).resolve().parents[1] / "reports_out" / "fxmr_validate.md"
    out.write_text(report)
    print(f"\nSaved -> {out}")


if __name__ == "__main__":
    main()
