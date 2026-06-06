"""İKİNCİ BOT denemesi — FundingPips-native DIVERSIFIED book (forex/indeks/metal).

Tek tek FX stratejileri zayıf/kırılgandı (momentum IS<0, MR maliyet-kırılgan, carry zayıf).
DENENMEYEN: crypto'daki ders — ÇEŞİTLENDİRME — burada. FX-carry + FX-MR + makro-TSMOM'u
inverse-vol blend (train-fit) ile birleştir; ortogonal zayıflar güçlü olur mu? Sıkı test:
IS vs OOS + yıl-bazı + maliyet-stresi. Geçerse 2. bot; geçmezse dürüstçe entegre etme.

Usage: python scripts/run_fpips_book.py [cost_bps]
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
COST = (float(sys.argv[1]) if len(sys.argv) > 1 else 6) / 1e4
PAIRS = {"EURUSD=X": ("EUR", +1), "GBPUSD=X": ("GBP", +1), "AUDUSD=X": ("AUD", +1),
         "NZDUSD=X": ("NZD", +1), "USDJPY=X": ("JPY", -1), "USDCAD=X": ("CAD", -1), "USDCHF=X": ("CHF", -1)}
MRU = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "USDCHF=X", "NZDUSD=X", "^GSPC", "^NDX", "GC=F", "SI=F"]
MACRO = ["GLD", "SLV", "TLT", "IEF", "DBC", "USO", "UUP", "DBA"]
RATES = {  # yaklaşık yıllık politika faizi (%)
    "USD": {2015: .25, 2016: .5, 2017: 1.25, 2018: 2.25, 2019: 1.75, 2020: .1, 2021: .1, 2022: 3, 2023: 5, 2024: 4.75, 2025: 4, 2026: 3.75},
    "EUR": {2015: .05, 2016: 0, 2017: 0, 2018: 0, 2019: 0, 2020: 0, 2021: 0, 2022: 1.5, 2023: 4, 2024: 3.5, 2025: 2.5, 2026: 2.25},
    "GBP": {2015: .5, 2016: .25, 2017: .5, 2018: .75, 2019: .75, 2020: .1, 2021: .25, 2022: 3, 2023: 5, 2024: 4.75, 2025: 4.25, 2026: 4},
    "JPY": {2015: .1, 2016: -.1, 2017: -.1, 2018: -.1, 2019: -.1, 2020: -.1, 2021: -.1, 2022: -.1, 2023: -.1, 2024: .1, 2025: .5, 2026: .75},
    "AUD": {2015: 2, 2016: 1.5, 2017: 1.5, 2018: 1.5, 2019: .75, 2020: .1, 2021: .1, 2022: 3, 2023: 4.1, 2024: 4.35, 2025: 3.85, 2026: 3.6},
    "CAD": {2015: .5, 2016: .5, 2017: 1, 2018: 1.75, 2019: 1.75, 2020: .25, 2021: .25, 2022: 4.25, 2023: 5, 2024: 4.25, 2025: 3, 2026: 2.75},
    "CHF": {2015: -.75, 2016: -.75, 2017: -.75, 2018: -.75, 2019: -.75, 2020: -.75, 2021: -.75, 2022: 1, 2023: 1.75, 2024: 1.25, 2025: .5, 2026: .25},
    "NZD": {2015: 2.5, 2016: 2, 2017: 1.75, 2018: 1.75, 2019: 1, 2020: .25, 2021: .75, 2022: 4.25, 2023: 5.5, 2024: 4.75, 2025: 3.75, 2026: 3.25},
}


def _sharpe(r):
    return float(r.mean() / r.std() * np.sqrt(PPY)) if r.std() > 0 else float("nan")


def _stats(r):
    eq = (1 + r).cumprod()
    return _sharpe(r), (eq.iloc[-1] ** (PPY / len(r)) - 1 if len(r) else np.nan), \
        (float((eq / eq.cummax() - 1).min()) if len(r) else np.nan)


def _load(tk):
    import yfinance as yf
    raw = yf.download(tk, start="2015-01-01", end="2026-06-01", interval="1d", progress=False, auto_adjust=True)
    out = {}
    for t in tk:
        try:
            c = raw["Close"][t].dropna()
        except Exception:  # noqa: BLE001
            continue
        if len(c) > 600:
            out[t] = c
    px = pd.DataFrame(out).dropna()
    px.index = pd.DatetimeIndex(px.index).as_unit("ns")
    return px


def carry_sleeve():
    px = _load(list(PAIRS))
    ccy = {c: px[p].pct_change() * s for p, (c, s) in PAIRS.items() if p in px.columns}
    R = pd.DataFrame(ccy).dropna()
    cs = pd.DataFrame({c: [RATES[c][y] - RATES["USD"][y] for y in R.index.year] for c in R.columns}, index=R.index)
    rank = cs.rank(axis=1, ascending=False)
    n, k = len(R.columns), 2
    w = ((rank <= k).astype(float) / k - (rank > n - k).astype(float) / k).shift(1).fillna(0.0)
    accr = (w * (cs / 100.0 / PPY)).sum(axis=1).shift(1).fillna(0.0)
    turn = w.diff().abs().sum(axis=1).fillna(0.0)
    return ((w * R).sum(axis=1) + accr - COST * turn).dropna().rename("carry")


def mr_sleeve(lb=1):
    px = _load(MRU)
    rets = px.pct_change()
    past = px.pct_change(lb)
    z = past.sub(past.mean(axis=1), axis=0).div(past.std(axis=1) + 1e-9, axis=0)
    w = (-z).shift(1)
    w = w.div(w.abs().sum(axis=1) + 1e-9, axis=0)
    turn = w.diff().abs().sum(axis=1).fillna(0.0)
    return ((w * rets).sum(axis=1) - COST * turn).dropna().rename("mr")


def tsmom_sleeve(lb=90):
    px = _load(MACRO)
    rets = px.pct_change()
    sig = np.sign(px.pct_change(lb)).shift(1)
    iv = (1.0 / rets.rolling(60).std()).shift(1)
    iv = iv.div(iv.sum(axis=1), axis=0)
    pos = (sig * iv).fillna(0.0)
    turn = pos.diff().abs().sum(axis=1).fillna(0.0)
    return ((pos * rets).sum(axis=1) - COST * turn).dropna().rename("tsmom")


def main():
    print(f"FundingPips-native sleeve'ler kuruluyor (maliyet {COST*1e4:.0f}bps)…")
    carry, mr, ts = carry_sleeve(), mr_sleeve(), tsmom_sleeve()
    R = pd.DataFrame({"carry": carry, "mr": mr, "tsmom": ts}).dropna()
    Rtr = R[R.index < CUT]
    iv = 1.0 / Rtr.std()
    w = iv / iv.sum()
    book = (R * w).sum(axis=1)

    lines = [f"# İKİNCİ BOT — FundingPips-native DIVERSIFIED book (maliyet {COST*1e4:.0f}bps)", "",
             f"Sleeve'ler: FX-carry + FX-MR(1g) + makro-TSMOM. Inverse-vol blend (train-fit "
             f"{dict((k, round(float(v), 2)) for k, v in w.items())}). Ortak {len(R)} gün.", "",
             "## Sleeve korelasyonu", "", "```", R.corr().round(2).to_string(), "```", "",
             "## IS vs OOS (kitap)", "", "| pencere | Sharpe | CAGR | MaxDD |", "|---|---|---|---|"]
    for nm, seg in (("IS (≤2024)", book[book.index < CUT]), ("OOS (2025-26)", book[book.index >= CUT])):
        sh, cg, md = _stats(seg)
        lines.append(f"| {nm} | {sh:.2f} | {cg*100:.0f}% | {md*100:.0f}% |")
    lines += ["", "## Tek tek sleeve OOS Sharpe", ""]
    for c in R.columns:
        sh, _, _ = _stats(R[c][R.index >= CUT])
        lines.append(f"- {c}: {sh:.2f}")
    lines += ["", "## Yıl-bazı (kitap)", "", "| yıl | Sharpe | getiri |", "|---|---|---|"]
    pos_y = tot_y = 0
    for yr, g in book.groupby(book.index.year):
        sh, _, _ = _stats(g)
        ret = (1 + g).cumprod().iloc[-1] - 1
        pos_y += ret > 0
        tot_y += 1
        lines.append(f"| {yr} | {sh:.2f} | {ret*100:+.0f}% |")

    is_sh = _stats(book[book.index < CUT])[0]
    oos_sh = _stats(book[book.index >= CUT])[0]
    lines += ["", "## Yorum (dürüst)", ""]
    if is_sh > 0.5 and oos_sh > 0.8 and pos_y >= 0.6 * tot_y:
        lines.append(f"**Çeşitlendirme İŞE YARADI: IS {is_sh:.2f} / OOS {oos_sh:.2f}, {pos_y}/{tot_y} yıl +.** "
                     "Ortogonal zayıf sleeve'ler birleşince robust kitap → 2. bot adayı. Maliyet-stresi "
                     "(farklı bps) + DSR/PBO + prop-sim sonraki adım.")
    else:
        lines.append(f"**Çeşitlendirme YETMEDİ: IS {is_sh:.2f} / OOS {oos_sh:.2f}, {pos_y}/{tot_y} yıl +.** "
                     "Zayıf/negatif bileşenler (momentum IS<0, MR maliyet-kırılgan) birleşince de robust "
                     "edge çıkmıyor — crypto'nun aksine FX/indeks'te ortogonal-güçlü-sleeve yok. **Dürüst "
                     "sonuç: FundingPips-native 2. botu ENTEGRE ETME — kanıtlı edge yok.** Forex'te edge "
                     "intraday/farklı-veri ister; günlük-üstü yapımızla çıkmıyor.")
    lines.append(f"- ⚠️ Maliyet {COST*1e4:.0f}bps; MR yüksek-turnover → gerçek FX/CFD spread'inde daha kötü. "
                 "Tek-dönem 2025-26 OOS cömert. yfinance survivorship-light (FX delist olmaz, crypto'dan temiz).")
    report = "\n".join(lines)
    print("\n" + report)
    (Path(__file__).resolve().parents[1] / "reports_out" / "fpips_book.md").write_text(report)
    print("\nSaved -> reports_out/fpips_book.md")


if __name__ == "__main__":
    main()
