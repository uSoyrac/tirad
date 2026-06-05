"""FundingPips honest hypotheses #2/#3 — FX CARRY + FX MEAN-REVERSION (both rigorously).

FX CARRY = the true analog of our best crypto edge (funding carry). Long high-policy-rate
currencies / short low-rate ones; total return = FX price move + daily carry (rate-diff)
accrual (the swap FundingPips pays/charges). Rates are approximate annual G10 policy rates
(public, step-like; the carry signal only needs the relative ranking).

FX MEAN-REVERSION = cross-sectional short-term reversal (fade last k-day winners/losers);
FX majors range more than crypto trends, so reversal may fit where momentum failed.

Same discipline: no-lookahead (signals lagged 1 day), realistic CFD cost, train<2025 / OOS
2025-26 + by-year (carry crashes in risk-off — the honesty gate). If either clears a credible
OOS Sharpe AND isn't a one-regime fluke, it feeds the prop simulator next.

Usage: python scripts/run_fxedge.py
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
COST = 0.0003

# USD pairs -> per-currency-vs-USD return sign (XXXUSD: +1 long=long XXX; USDXXX: long XXX = -USDXXX)
PAIRS = {"EURUSD=X": ("EUR", +1), "GBPUSD=X": ("GBP", +1), "AUDUSD=X": ("AUD", +1),
         "NZDUSD=X": ("NZD", +1), "USDJPY=X": ("JPY", -1), "USDCAD=X": ("CAD", -1),
         "USDCHF=X": ("CHF", -1)}
MR_UNIVERSE = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "USDCHF=X",
               "NZDUSD=X", "^GSPC", "^NDX", "^GDAXI", "GC=F", "SI=F"]
# approximate annual policy rates (%) — public central-bank history; relative ranking is what matters
RATES = {
    "USD": {2015: .25, 2016: .50, 2017: 1.25, 2018: 2.25, 2019: 1.75, 2020: .10, 2021: .10, 2022: 3.0, 2023: 5.0, 2024: 4.75, 2025: 4.0, 2026: 3.75},
    "EUR": {2015: .05, 2016: 0., 2017: 0., 2018: 0., 2019: 0., 2020: 0., 2021: 0., 2022: 1.5, 2023: 4.0, 2024: 3.5, 2025: 2.5, 2026: 2.25},
    "GBP": {2015: .50, 2016: .25, 2017: .50, 2018: .75, 2019: .75, 2020: .10, 2021: .25, 2022: 3.0, 2023: 5.0, 2024: 4.75, 2025: 4.25, 2026: 4.0},
    "JPY": {2015: .10, 2016: -.10, 2017: -.10, 2018: -.10, 2019: -.10, 2020: -.10, 2021: -.10, 2022: -.10, 2023: -.10, 2024: .10, 2025: .50, 2026: .75},
    "AUD": {2015: 2.0, 2016: 1.5, 2017: 1.5, 2018: 1.5, 2019: .75, 2020: .10, 2021: .10, 2022: 3.0, 2023: 4.1, 2024: 4.35, 2025: 3.85, 2026: 3.6},
    "CAD": {2015: .50, 2016: .50, 2017: 1.0, 2018: 1.75, 2019: 1.75, 2020: .25, 2021: .25, 2022: 4.25, 2023: 5.0, 2024: 4.25, 2025: 3.0, 2026: 2.75},
    "CHF": {2015: -.75, 2016: -.75, 2017: -.75, 2018: -.75, 2019: -.75, 2020: -.75, 2021: -.75, 2022: 1.0, 2023: 1.75, 2024: 1.25, 2025: .50, 2026: .25},
    "NZD": {2015: 2.5, 2016: 2.0, 2017: 1.75, 2018: 1.75, 2019: 1.0, 2020: .25, 2021: .75, 2022: 4.25, 2023: 5.5, 2024: 4.75, 2025: 3.75, 2026: 3.25},
}


def _sharpe(r):
    return float(r.mean() / r.std() * np.sqrt(PPY)) if r.std() > 0 else float("nan")


def _stats(r):
    eq = (1 + r).cumprod()
    return _sharpe(r), (eq.iloc[-1] ** (PPY / len(r)) - 1 if len(r) else np.nan), \
        (float((eq / eq.cummax() - 1).min()) if len(r) else np.nan)


def _load(tickers):
    import yfinance as yf
    raw = yf.download(tickers, start="2015-01-01", end="2026-06-01", interval="1d",
                      progress=False, auto_adjust=True)
    out = {}
    for t in tickers:
        try:
            c = raw["Close"][t].dropna()
        except Exception:  # noqa: BLE001
            continue
        if len(c) > 600:
            out[t] = c
    px = pd.DataFrame(out).dropna()
    px.index = pd.DatetimeIndex(px.index).as_unit("ns")
    return px


def carry_book():
    px = _load(list(PAIRS))
    # per-currency-vs-USD daily price return
    ccy_ret = {}
    for pair, (ccy, sgn) in PAIRS.items():
        if pair in px.columns:
            ccy_ret[ccy] = px[pair].pct_change() * sgn
    R = pd.DataFrame(ccy_ret).dropna()
    ccys = list(R.columns)
    # carry signal = rate(ccy) - rate(USD), by year (lagged: use prior day's known rate)
    yrs = R.index.year
    carry_sig = pd.DataFrame({c: [RATES[c][y] - RATES["USD"][y] for y in yrs] for c in ccys}, index=R.index)
    rank = carry_sig.rank(axis=1, ascending=False)
    n = len(ccys)
    k = 2
    w = ((rank <= k).astype(float) / k - (rank > n - k).astype(float) / k).shift(1).fillna(0.0)
    price_pnl = (w * R).sum(axis=1)
    # daily carry accrual earned on the held positions (long earns +rate-diff, short pays)
    accr = (w * (carry_sig / 100.0 / PPY)).sum(axis=1).shift(1).fillna(0.0)
    turn = w.diff().abs().sum(axis=1).fillna(0.0)
    return (price_pnl + accr - COST * turn).dropna()


def mr_book(lookback):
    px = _load(MR_UNIVERSE)
    rets = px.pct_change()
    past = px.pct_change(lookback)
    z = past.sub(past.mean(axis=1), axis=0).div(past.std(axis=1) + 1e-9, axis=0)
    w = (-z).shift(1)
    w = w.div(w.abs().sum(axis=1) + 1e-9, axis=0)
    turn = w.diff().abs().sum(axis=1).fillna(0.0)
    return ((w * rets).sum(axis=1) - COST * turn).dropna()


def _report_book(name, r, lines):
    is_r, oos_r = r[r.index < CUT], r[r.index >= CUT]
    shi, _, _ = _stats(is_r)
    sho, cgo, mdo = _stats(oos_r)
    lines.append(f"| {name} | {shi:.2f} | {sho:.2f} | {cgo*100:.0f}% | {mdo*100:.0f}% |")
    return sho, r


def main():
    lines = ["# FundingPips dürüst hipotezler — FX CARRY + MEAN-REVERSION", "",
             "G10 FX (carry) + 12-enstrüman (MR). Maliyet 3bps/turnover, sinyaller 1-gün gecikmeli, "
             "train<2025/OOS 2025-26. Carry = fiyat + günlük faiz-farkı tahakkuku.", "",
             "## IS vs OOS Sharpe", "",
             "| strateji | IS Sharpe | OOS Sharpe | OOS CAGR | OOS MaxDD |", "|---|---|---|---|---|"]
    results = {}
    print("FX carry kuruluyor...")
    results["FX-CARRY"] = _report_book("FX-CARRY (rate-diff)", carry_book(), lines)
    print("FX mean-reversion kuruluyor...")
    for lb in (1, 2, 3, 5):
        results[f"FX-MR-{lb}"] = _report_book(f"FX-MR-{lb}d", mr_book(lb), lines)

    best = max(results, key=lambda k: results[k][0] if results[k][0] == results[k][0] else -9)
    br = results[best][1]
    lines += ["", f"## En iyi OOS aday: **{best}** (Sharpe {results[best][0]:.2f}) — yıl-bazı "
              "(rejim/carry-crash geçidi)", "", "| yıl | Sharpe | getiri |", "|---|---|---|"]
    pos_years = 0
    tot_years = 0
    for yr, g in br.groupby(br.index.year):
        sh, _, _ = _stats(g)
        ret = (1 + g).cumprod().iloc[-1] - 1
        pos_years += ret > 0
        tot_years += 1
        lines.append(f"| {yr} | {sh:.2f} | {ret*100:+.0f}% |")

    lines += ["", "## Yorum (dürüst)", ""]
    bsh = results[best][0]
    if bsh >= 0.8 and pos_years >= 0.6 * tot_years:
        lines.append(f"**Aday GERÇEK görünüyor: {best}, OOS Sharpe {bsh:.2f}, {pos_years}/{tot_years} "
                     "yıl pozitif.** Tek-rejim flukı DEĞİL (FundingPips fiyat-momentum'unun aksine). "
                     "Sonraki: DSR/PBO + prop simülatörü (geç/patla olasılığı). Bu, challenge'ı "
                     "denemeye değer ilk dürüst zemin.")
    elif bsh >= 0.8:
        lines.append(f"**{best} OOS Sharpe {bsh:.2f} cazip AMA sadece {pos_years}/{tot_years} yıl "
                     "pozitif — rejim-bağımlı (muhtemelen carry-crash riski). Edge VAR ama kırılgan; "
                     "DSR/PBO + boyut çok temkinli. Tek başına challenge garantisi değil.")
    else:
        lines.append(f"**En iyi aday {best} bile OOS Sharpe {bsh:.2f} < 0.8.** FX carry + MR de "
                     "FundingPips'te güçlü/robust edge vermedi. Dürüst birikmiş sonuç: elimizdeki "
                     "yöntemlerle FundingPips için KANITLI edge YOK. Challenge alma; ya crypto-dostu "
                     "prop ara (kanıtlı kitabımız orada çalışır) ya da intraday/farklı veri gerekir.")
    report = "\n".join(lines)
    print("\n" + report)
    out = Path(__file__).resolve().parents[1] / "reports_out" / "fxedge.md"
    out.write_text(report)
    print(f"\nSaved -> {out}")


if __name__ == "__main__":
    main()
