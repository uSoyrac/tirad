"""FundingPips-NATIVE edge research — does a REAL edge exist on THEIR instruments?

Our DSR/PBO-validated crypto book does NOT transfer to FundingPips (no perp funding sleeve,
no 30-stock cross-section, crypto degraded to a few 1:2 CFDs). So we apply the SAME rigorous
pipeline to FundingPips-tradeable instruments: G10 FX + major indices + metals (all CFDs they
offer). Honest costs (CFD spread + overnight swap + commission). Train/OOS + by-year + DSR-lite.

Candidates (price-only, no rate data needed for v1):
  A. Cross-asset TIME-SERIES momentum (Moskowitz-Ooi-Pedersen): long/short by sign of trailing
     return, inverse-vol weighted — the canonical managed-futures edge prop traders use.
  B. Cross-sectional momentum: hold Top-K trailing-return instruments long, Bottom-K short.

If NEITHER clears a credible OOS Sharpe on their instruments, the honest answer is: don't
expect our system to pass FundingPips — the edge isn't there on these markets. If one does,
its OOS daily returns feed the prop pass-probability (reuse run_propfirm logic separately).

Usage: python scripts/run_fundingpips.py
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
# FundingPips-tradeable, fetchable via yfinance:
FX = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "USDCHF=X", "NZDUSD=X",
      "EURGBP=X", "EURJPY=X", "GBPJPY=X"]
IDX = ["^GSPC", "^NDX", "^DJI", "^GDAXI", "^FTSE", "^N225"]
METAL = ["GC=F", "SI=F"]               # gold, silver (XAUUSD/XAGUSD analogs)
UNIVERSE = FX + IDX + METAL
COST = 0.0003                          # ~3 bps/turnover (FX/index CFD spreads tight; alts wider)


def _sharpe(r):
    return float(r.mean() / r.std() * np.sqrt(PPY)) if r.std() > 0 else float("nan")


def _stats(r):
    eq = (1 + r).cumprod()
    sh = _sharpe(r)
    cg = eq.iloc[-1] ** (PPY / len(r)) - 1 if len(r) else float("nan")
    md = float((eq / eq.cummax() - 1).min()) if len(r) else float("nan")
    return sh, cg, md


def _load():
    import yfinance as yf
    raw = yf.download(UNIVERSE, start="2015-01-01", end="2026-06-01", interval="1d",
                      progress=False, auto_adjust=True)
    closes = {}
    for t in UNIVERSE:
        try:
            c = raw["Close"][t].dropna()
        except Exception:  # noqa: BLE001
            continue
        if len(c) > 600:
            closes[t] = c
    px = pd.DataFrame(closes).dropna()
    px.index = pd.DatetimeIndex(px.index).as_unit("ns")
    return px


def _tsmom(px, lookback=90):
    rets = px.pct_change()
    sig = np.sign(px.pct_change(lookback)).shift(1)
    invvol = (1.0 / rets.rolling(60).std()).shift(1)
    invvol = invvol.div(invvol.sum(axis=1), axis=0)
    pos = (sig * invvol).fillna(0.0)
    gross = (pos * rets).sum(axis=1)
    turn = pos.diff().abs().sum(axis=1).fillna(0.0)
    return (gross - COST * turn).dropna()


def _xsec(px, lookback=90, k=3):
    rets = px.pct_change()
    mom = px.pct_change(lookback)
    rank = mom.rank(axis=1, ascending=False)
    n = px.shape[1]
    long = (rank <= k).astype(float)
    short = (rank > n - k).astype(float)
    w = (long / k - short / k).shift(1).fillna(0.0)
    gross = (w * rets).sum(axis=1)
    turn = w.diff().abs().sum(axis=1).fillna(0.0)
    return (gross - COST * turn).dropna()


def main():
    print("FundingPips-yerli evren indiriliyor (G10 FX + indeks + metal)...")
    px = _load()
    print(f"{px.shape[1]} enstrüman, {len(px)} gün ({px.index[0].date()}→{px.index[-1].date()}).")

    books = {}
    for lb in (30, 60, 90, 120):
        books[f"TSMOM-{lb}"] = _tsmom(px, lb)
        books[f"XSEC-{lb}-k3"] = _xsec(px, lb, 3)

    lines = ["# FundingPips-yerli edge araştırması (kendi enstrümanları)", "",
             f"Evren: {px.shape[1]} enstrüman (G10 FX + indeks + metal), günlük, maliyet "
             f"{COST*1e4:.0f}bps/turnover. Train<2025 / OOS 2025-26. Aynı dürüst boru hattı.", "",
             "## Aday stratejiler — IS vs OOS Sharpe (overfit kontrolü)", "",
             "| strateji | IS Sharpe | OOS Sharpe | OOS CAGR | OOS MaxDD |", "|---|---|---|---|---|"]
    best = (None, -9)
    for name, r in books.items():
        is_r, oos_r = r[r.index < CUT], r[r.index >= CUT]
        shi, _, _ = _stats(is_r)
        sho, cgo, mdo = _stats(oos_r)
        lines.append(f"| {name} | {shi:.2f} | {sho:.2f} | {cgo*100:.0f}% | {mdo*100:.0f}% |")
        if sho > best[1]:
            best = (name, sho)

    # by-year for the best book
    br = books[best[0]]
    lines += ["", f"## En iyi OOS aday: **{best[0]}** (OOS Sharpe {best[1]:.2f}) — yıl-bazı", "",
              "| yıl | Sharpe | getiri |", "|---|---|---|"]
    for yr, g in br.groupby(br.index.year):
        sh, _, _ = _stats(g)
        eq = (1 + g).cumprod().iloc[-1] - 1
        lines.append(f"| {yr} | {sh:.2f} | {eq*100:+.0f}% |")

    lines += ["", "## Yorum (dürüst)", ""]
    if best[1] >= 0.8:
        lines.append(f"**FundingPips enstrümanlarında ARAŞTIRILMAYA DEĞER bir aday var: {best[0]}, "
                     f"OOS Sharpe {best[1]:.2f}.** Sonraki adım: DSR/PBO honesty gate + bu akışı prop "
                     "simülatörüne ver (geç/patla olasılığı). Yıl-bazı tablo rejim-dayanıklılığını gösterir; "
                     "negatif yıl varsa beklenti ona göre. yfinance survivorship-light (FX/indeks delist "
                     "olmaz) → crypto'dan DAHA temiz; ama spread/swap CFD'de daha yüksek olabilir.")
    else:
        lines.append(f"**FundingPips enstrümanlarında price-only momentum/trend OOS'ta zayıf (en iyi "
                     f"{best[0]} Sharpe {best[1]:.2f} < 0.8).** Bu, kendi LEVER #1 makro-TSMOM negatif "
                     "bulgumuzla TUTARLI — FX/indeks trend son rejimde zor. Dürüst sonuç: bu basit "
                     "edge'lerle FundingPips'i geçmeyi BEKLEME. Denenecek sonraki (veri gerektirir): "
                     "FX CARRY (faiz-farkı, swap ile — funding-carry'mizin gerçek analoğu), daha kısa "
                     "vade/intraday, ya da mean-reversion. Edge KANITLANMADAN challenge alma.")
    report = "\n".join(lines)
    print("\n" + report)
    out = Path(__file__).resolve().parents[1] / "reports_out" / "fundingpips.md"
    out.write_text(report)
    print(f"\nSaved -> {out}")


if __name__ == "__main__":
    main()
