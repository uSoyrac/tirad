"""FOREX OPTIMAL SİNYAL — FX CARRY'yi optimize et (tek gerçek FX faktörü).

FX'te tek pozitif-IS-VE-OOS, düşük-turnover (maliyet-dayanıklı) faktör = CARRY. Onu güçlendir:
  A. raw carry        : faiz-farkı sıralaması (baseline)
  B. carry-to-vol     : risk-ayarlı carry (faiz-farkı / parite vol) — daha iyi sıralama
  C. carry + trend    : sadece fiyat-trendi carry yönüyle uyuşunca tut (carry-CRASH koruması)
  D. C + vol-hedef    : %10 yıllık vol
Carry'nin bilinen kusuru risk-off'ta çöküş; trend-filtresi tam bunu hedefler. IS/OOS + yıl-bazı.
Çıktı = FundingPips/forex için MANUEL sinyal (modest ama gerçek faktör).

Usage: python scripts/run_fx_carry_opt.py
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
COST = 0.0006
PAIRS = {"EURUSD=X": ("EUR", +1), "GBPUSD=X": ("GBP", +1), "AUDUSD=X": ("AUD", +1),
         "NZDUSD=X": ("NZD", +1), "USDJPY=X": ("JPY", -1), "USDCAD=X": ("CAD", -1), "USDCHF=X": ("CHF", -1)}
RATES = {
    "USD": {2015: .25, 2016: .5, 2017: 1.25, 2018: 2.25, 2019: 1.75, 2020: .1, 2021: .1, 2022: 3, 2023: 5, 2024: 4.75, 2025: 4, 2026: 3.75},
    "EUR": {2015: .05, 2016: 0, 2017: 0, 2018: 0, 2019: 0, 2020: 0, 2021: 0, 2022: 1.5, 2023: 4, 2024: 3.5, 2025: 2.5, 2026: 2.25},
    "GBP": {2015: .5, 2016: .25, 2017: .5, 2018: .75, 2019: .75, 2020: .1, 2021: .25, 2022: 3, 2023: 5, 2024: 4.75, 2025: 4.25, 2026: 4},
    "JPY": {2015: .1, 2016: -.1, 2017: -.1, 2018: -.1, 2019: -.1, 2020: -.1, 2021: -.1, 2022: -.1, 2023: -.1, 2024: .1, 2025: .5, 2026: .75},
    "AUD": {2015: 2, 2016: 1.5, 2017: 1.5, 2018: 1.5, 2019: .75, 2020: .1, 2021: .1, 2022: 3, 2023: 4.1, 2024: 4.35, 2025: 3.85, 2026: 3.6},
    "CAD": {2015: .5, 2016: .5, 2017: 1, 2018: 1.75, 2019: 1.75, 2020: .25, 2021: .25, 2022: 4.25, 2023: 5, 2024: 4.25, 2025: 3, 2026: 2.75},
    "CHF": {2015: -.75, 2016: -.75, 2017: -.75, 2018: -.75, 2019: -.75, 2020: -.75, 2021: -.75, 2022: 1, 2023: 1.75, 2024: 1.25, 2025: .5, 2026: .25},
    "NZD": {2015: 2.5, 2016: 2, 2017: 1.75, 2018: 1.75, 2019: 1, 2020: .25, 2021: .75, 2022: 4.25, 2023: 5.5, 2024: 4.75, 2025: 3.75, 2026: 3.25},
}


def _stats(r):
    eq = (1 + r).cumprod()
    sh = float(r.mean() / r.std() * np.sqrt(PPY)) if r.std() > 0 else float("nan")
    cg = eq.iloc[-1] ** (PPY / len(r)) - 1 if len(r) else np.nan
    md = float((eq / eq.cummax() - 1).min()) if len(r) else np.nan
    return sh, cg, md


def _load():
    import yfinance as yf
    raw = yf.download(list(PAIRS), start="2015-01-01", end="2026-06-01", interval="1d", progress=False, auto_adjust=True)
    out = {}
    for p in PAIRS:
        try:
            c = raw["Close"][p].dropna()
        except Exception:  # noqa: BLE001
            continue
        if len(c) > 600:
            out[p] = c
    px = pd.DataFrame(out).dropna()
    px.index = pd.DatetimeIndex(px.index).as_unit("ns")
    return px


def build(variant):
    px = _load()
    ret = pd.DataFrame({c: px[p].pct_change() * s for p, (c, s) in PAIRS.items() if p in px.columns}).dropna()
    ccys = list(ret.columns)
    carry = pd.DataFrame({c: [RATES[c][y] - RATES["USD"][y] for y in ret.index.year] for c in ccys}, index=ret.index)
    vol = ret.rolling(60).std() * np.sqrt(PPY)
    if variant in ("B", "C", "D"):
        signal = carry / (vol + 1e-9)        # carry-to-vol
    else:
        signal = carry
    rank = signal.rank(axis=1, ascending=False)
    n, k = len(ccys), 2
    w = ((rank <= k).astype(float) / k - (rank > n - k).astype(float) / k)
    if variant in ("C", "D"):
        trend = np.sign(px_ccy_trend(px)).reindex(index=w.index, columns=ccys).fillna(0.0)
        w = w.where(np.sign(w) == trend, 0.0)   # trend uyuşmazsa pozisyon kapat
    w = w.shift(1).fillna(0.0)
    accr = (w * (carry / 100.0 / PPY)).sum(axis=1).shift(1).fillna(0.0)
    turn = w.diff().abs().sum(axis=1).fillna(0.0)
    r = (w * ret).sum(axis=1) + accr - COST * turn
    if variant == "D":
        rv = r.rolling(20).std().shift(1) * np.sqrt(PPY)
        r = r * (0.10 / rv).clip(upper=3.0).fillna(0.0)
    return r.dropna()


def px_ccy_trend(px, lb=60):
    """her para birimi-vs-USD için trend yönü (90g momentum işareti)."""
    tr = {}
    for p, (c, s) in PAIRS.items():
        if p in px.columns:
            tr[c] = np.sign(px[p].pct_change(lb)) * s
    return pd.DataFrame(tr)


def main():
    names = {"A": "raw carry", "B": "carry-to-vol", "C": "carry+trend-filtre", "D": "C+vol-hedef %10"}
    lines = ["# FOREX OPTIMAL SİNYAL — FX carry optimizasyonu (tek gerçek FX faktörü)", "",
             f"7 G10 parite, maliyet {COST*1e4:.0f}bps, train<2025/OOS 2025-26. Carry-crash için trend-filtresi.", "",
             "| Varyant | IS Sharpe | OOS Sharpe | OOS CAGR | OOS MaxDD | +yıl |", "|---|---|---|---|---|---|"]
    best = (None, -9)
    for v in ("A", "B", "C", "D"):
        r = build(v)
        is_r, oos = r[r.index < CUT], r[r.index >= CUT]
        si, _, _ = _stats(is_r)
        so, co, mo = _stats(oos)
        py = sum((1 + g).cumprod().iloc[-1] > 1 for _, g in r.groupby(r.index.year))
        ty = r.index.year.nunique()
        lines.append(f"| {v}: {names[v]} | {si:.2f} | {so:.2f} | {co*100:.0f}% | {mo*100:.0f}% | {py}/{ty} |")
        score = min(si, so)   # hem IS hem OOS iyi olmalı
        if score > best[1]:
            best = (v, score, si, so, py, ty)
    v, _, si, so, py, ty = best
    lines += ["", "## Yorum (dürüst)", ""]
    if si > 0.3 and so > 0.5 and py >= 0.6 * ty:
        lines.append(f"**En iyi: {names[v]} — IS {si:.2f} / OOS {so:.2f}, {py}/{ty} yıl +.** Hem IS hem OOS "
                     "pozitif + çoğu yıl + düşük-turnover (maliyet-dayanıklı) = FX için GERÇEK ama MODEST "
                     "sinyal. Trend-filtresi carry-crash'i azaltıyorsa C/D kazanır. **FundingPips/forex 2. "
                     "bot = bu carry sinyali (MANUEL).** ⚠️ Prop +%10 hedefi için zayıf (yavaş/modest) — "
                     "challenge-passer değil, yavaş-gelir/diversifikasyon sinyali.")
    else:
        lines.append(f"**En iyi varyant bile zayıf (IS {si:.2f}/OOS {so:.2f}, {py}/{ty} yıl).** FX carry "
                     "literatür-tipik (~0.5 Sharpe, kriz-kuyruğu) ama prop için yetersiz ve kırılgan. "
                     "Trend-filtresi yardım ettiyse C/D en az kötü. Dürüst: forex'te modest carry dışında "
                     "satılabilir edge yok; sinyal olarak verilebilir ama beklenti düşük tutulmalı.")
    lines.append("- ⚠️ Carry kriz-kuyruğu taşır (risk-off'ta sert düşüş); trend-filtresi azaltır ama silmez. "
                 "Tek-dönem OOS; faiz verisi yaklaşık-yıllık; gerçek FX/CFD swap firma-bazlı farklı.")
    report = "\n".join(lines)
    print(report)
    (Path(__file__).resolve().parents[1] / "reports_out" / "fx_carry_opt.md").write_text(report)
    print("\nSaved -> reports_out/fx_carry_opt.md")


if __name__ == "__main__":
    main()
