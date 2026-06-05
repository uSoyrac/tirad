"""FUTURES edge testi (Q2) — TopStep/Apex tarzı futures prop için.

Çok-varlık futures evreni (endeks ES/NQ/YM, emtia GC/SI/HG/CL/NG, tahvil ZB/ZN, FX 6E/6J/6B,
dolar DX). Managed-futures klasikleri: TSMOM (zaman-serisi momentum) + cross-sectional momentum.
IS/OOS + yıl-bazı + futures-prop geçiş tahmini. Dürüst: TSMOM son rejimde zayıftı (makro-ETF
testinde OOS -0.72) — futures-native'de farklı mı?

Usage: python scripts/run_futures.py
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
FUT = ["ES=F", "NQ=F", "YM=F", "GC=F", "SI=F", "HG=F", "CL=F", "NG=F",
       "ZB=F", "ZN=F", "6E=F", "6J=F", "6B=F", "DX=F"]


def _sharpe(r):
    return float(r.mean() / r.std() * np.sqrt(PPY)) if r.std() > 0 else float("nan")


def _stats(r):
    eq = (1 + r).cumprod()
    return _sharpe(r), (eq.iloc[-1] ** (PPY / len(r)) - 1 if len(r) else np.nan), \
        (float((eq / eq.cummax() - 1).min()) if len(r) else np.nan)


def _load():
    import yfinance as yf
    raw = yf.download(FUT, start="2015-01-01", end="2026-06-01", interval="1d", progress=False, auto_adjust=True)
    out = {}
    for t in FUT:
        try:
            c = raw["Close"][t].dropna()
        except Exception:  # noqa: BLE001
            continue
        if len(c) > 600:
            out[t] = c
    px = pd.DataFrame(out).dropna()
    px.index = pd.DatetimeIndex(px.index).as_unit("ns")
    return px


def tsmom(px, lb):
    rets = px.pct_change()
    sig = np.sign(px.pct_change(lb)).shift(1)
    iv = (1.0 / rets.rolling(60).std()).shift(1)
    iv = iv.div(iv.sum(axis=1), axis=0)
    pos = (sig * iv).fillna(0.0)
    turn = pos.diff().abs().sum(axis=1).fillna(0.0)
    return ((pos * rets).sum(axis=1) - COST * turn).dropna()


def xsec(px, lb, k=3):
    rets = px.pct_change()
    mom = px.pct_change(lb)
    rank = mom.rank(axis=1, ascending=False)
    n = px.shape[1]
    w = ((rank <= k).astype(float) / k - (rank > n - k).astype(float) / k).shift(1).fillna(0.0)
    turn = w.diff().abs().sum(axis=1).fillna(0.0)
    return ((w * rets).sum(axis=1) - COST * turn).dropna()


def pass_prob(r, vol, target=0.06, daily=-0.03, total=-0.04, trail=True, nsim=12000):
    """TopStep/Apex proxy: +6% hedef, trailing -4% DD, günlük -3%."""
    z = ((r - r.mean()) / r.std()).to_numpy()
    sd = vol / np.sqrt(PPY)
    mu = 0.6 * (r.mean() / r.std()) * sd
    rng = np.random.default_rng(9)
    p = 0
    for _ in range(nsim):
        path = mu + sd * z[rng.integers(0, len(z), 252)]
        eq = peak = 1.0
        for ret in path:
            if ret <= daily:
                break
            eq *= (1 + ret)
            peak = max(peak, eq)
            floor = peak * (1 + total) if trail else (1 + total)
            if eq <= floor:
                break
            if eq >= 1 + target:
                p += 1
                break
    return p / nsim


def main():
    print("Futures verisi indiriliyor…")
    px = _load()
    print(f"{px.shape[1]} futures, {len(px)} gün ({px.index[0].date()}→{px.index[-1].date()})")
    books = {}
    for lb in (30, 60, 90, 120):
        books[f"TSMOM-{lb}"] = tsmom(px, lb)
        books[f"XSEC-{lb}"] = xsec(px, lb)

    lines = [f"# FUTURES edge testi — {px.shape[1]} kontrat (endeks+emtia+tahvil+FX)", "",
             f"Managed-futures: TSMOM + cross-sectional momentum. Maliyet {COST*1e4:.0f}bps. train<2025/OOS.", "",
             "| strateji | IS Sharpe | OOS Sharpe | OOS CAGR | OOS MaxDD | +yıl |", "|---|---|---|---|---|---|"]
    best = (None, -9, None)
    for nm, r in books.items():
        is_r, oos = r[r.index < CUT], r[r.index >= CUT]
        si = _sharpe(is_r)
        so, co, mo = _stats(oos)
        py = sum((1 + g).cumprod().iloc[-1] > 1 for _, g in r.groupby(r.index.year))
        ty = r.index.year.nunique()
        lines.append(f"| {nm} | {si:.2f} | {so:.2f} | {co*100:.0f}% | {mo*100:.0f}% | {py}/{ty} |")
        if min(si, so) > best[1]:
            best = (nm, min(si, so), r)

    nm, _, br = best
    si = _sharpe(br[br.index < CUT])
    so = _sharpe(br[br.index >= CUT])
    lines += ["", f"## En iyi: {nm} (IS {si:.2f} / OOS {so:.2f}) — geçiş tahmini (TopStep proxy +6%/trail-4%/günlük-3%)", "",
              "| vol-hedef | P(geç) |", "|---|---|"]
    for v in (0.05, 0.08, 0.10):
        lines.append(f"| %{v*100:.0f} | %{pass_prob(br, v)*100:.0f} |")
    lines += ["", "## Yorum (dürüst)", ""]
    if si > 0.3 and so > 0.5:
        lines.append(f"**Futures'ta {nm} araştırılabilir (IS {si:.2f}/OOS {so:.2f}).** Managed-futures "
                     "trend gerçek; geçiş yukarıda. Firma: TopStep/Apex (ucuz, yarı-oto → manuel /sinyal "
                     "uyar). DSR/PBO + maliyet-stresi sonraki adım. ⚠️ trailing DD %4 SIKI → düşük vol.")
    else:
        lines.append(f"**Futures zayıf: en iyi {nm} IS {si:.2f}/OOS {so:.2f}.** Managed-futures TSMOM "
                     "son rejimde (makro-ETF testiyle tutarlı) zayıf — futures-native'de de robust edge "
                     "çıkmadı. Dürüst: futures için kanıtlı edge YOK; crypto+hisse'ye odaklan. (Futures "
                     "props ucuz/Türkiye-OK ama edge olmadan = kumar.)")
    lines.append("- ⚠️ Trailing -4% DD futures-prop'ta SIKI; tek-dönem OOS; yfinance sürekli-futures "
                 "yaklaşık. Yarı-oto (TradingView webhook) izinli, tam-bot çoğu firmada yasak.")
    report = "\n".join(lines)
    print("\n" + report)
    (Path(__file__).resolve().parents[1] / "reports_out" / "futures.md").write_text(report)
    print("\nSaved -> reports_out/futures.md")


if __name__ == "__main__":
    main()
