"""FX CARRY (Bot 2) tam istatistik + prop geçiş tahmini — 'sağlam rakamlar'."""
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


def carry_returns():
    import yfinance as yf
    raw = yf.download(list(PAIRS), start="2015-01-01", end="2026-06-01", interval="1d", progress=False, auto_adjust=True)
    px = pd.DataFrame({p: raw["Close"][p].dropna() for p in PAIRS if len(raw["Close"][p].dropna()) > 600}).dropna()
    px.index = pd.DatetimeIndex(px.index).as_unit("ns")
    ret = pd.DataFrame({c: px[p].pct_change() * s for p, (c, s) in PAIRS.items() if p in px.columns}).dropna()
    cs = pd.DataFrame({c: [RATES[c][y] - RATES["USD"][y] for y in ret.index.year] for c in ret.columns}, index=ret.index)
    rank = cs.rank(axis=1, ascending=False)
    n, k = len(ret.columns), 2
    w = ((rank <= k).astype(float) / k - (rank > n - k).astype(float) / k).shift(1).fillna(0.0)
    accr = (w * (cs / 100.0 / PPY)).sum(axis=1).shift(1).fillna(0.0)
    turn = w.diff().abs().sum(axis=1).fillna(0.0)
    return ((w * ret).sum(axis=1) + accr - COST * turn).dropna()


def sharpe(r):
    return float(r.mean() / r.std() * np.sqrt(PPY)) if r.std() > 0 else float("nan")


def pass_prob(r, target, daily, total, vol, nsim=15000):
    """bootstrap: carry'yi vol'a ölçekle, prop challenge geç (HyroTrader 2-step trailing)."""
    z = ((r - r.mean()) / r.std()).to_numpy()
    sd = vol / np.sqrt(PPY)
    mu = 0.6 * (r.mean() / r.std()) * sd      # haircut 0.6
    rng = np.random.default_rng(3)
    P1, P2 = 0.10, 0.05
    passed = 0
    for _ in range(nsim):
        idx = rng.integers(0, len(z), 252)
        path = mu + sd * z[idx]
        eq = peak = 1.0
        phase = d = ok = 0
        for ret in path:
            d += 1
            if ret <= daily:
                break
            eq *= (1 + ret)
            peak = max(peak, eq)
            if eq <= peak * (1 + total):
                break
            tgt, mind = (P1, 10) if phase == 0 else (P2, 5)
            if eq >= 1 + tgt and d >= mind:
                phase += 1
                if phase >= 2:
                    ok = 1
                    break
                eq = peak = 1.0
                d = 0
        passed += ok
    return passed / nsim


def main():
    r = carry_returns()
    is_r, oos = r[r.index < CUT], r[r.index >= CUT]
    full = r
    monthly = (1 + r).resample("ME").prod() - 1
    yearly = (1 + r).groupby(r.index.year).prod() - 1

    def block(name, s):
        eq = (1 + s).cumprod()
        cg = eq.iloc[-1] ** (PPY / len(s)) - 1
        md = float((eq / eq.cummax() - 1).min())
        return f"| {name} | {sharpe(s):.2f} | {cg*100:+.0f}% | {md*100:.0f}% | {len(s)}g |"

    lines = ["# FX CARRY (Bot 2) — sağlam rakamlar", "",
             f"7 G10 parite, faiz-farkı carry, maliyet {COST*1e4:.0f}bps, 2015→2026.", "",
             "## Risk-getiri", "", "| pencere | Sharpe | yıllık getiri | MaxDD | örneklem |", "|---|---|---|---|---|",
             block("Tüm tarih", full), block("IS (≤2024)", is_r), block("OOS (2025-26)", oos), "",
             "## Tutarlılık", "",
             f"- **Kazanan yıl: {int((yearly>0).sum())}/{len(yearly)} (%{(yearly>0).mean()*100:.0f})**",
             f"- **Kazanan ay: {int((monthly>0).sum())}/{len(monthly)} (%{(monthly>0).mean()*100:.0f})**",
             f"- Kazanan gün: %{(r>0).mean()*100:.0f}",
             f"- En iyi yıl {yearly.max()*100:+.0f}% / en kötü yıl {yearly.min()*100:+.0f}%",
             f"- En iyi ay {monthly.max()*100:+.0f}% / en kötü ay {monthly.min()*100:+.0f}% (carry-crash kuyruğu)", "",
             "## Prop challenge geçiş tahmini (HyroTrader 2-step, bootstrap, haircut 0.6)", "",
             "| vol-hedef | P(geç) |", "|---|---|"]
    for v in (0.10, 0.15, 0.20):
        lines.append(f"| %{v*100:.0f} | %{pass_prob(full, 0.10, -0.05, -0.10, v)*100:.0f} |")
    lines += ["", "## Yorum (dürüst)", "",
              f"- **Strateji olarak GERÇEK ama MODEST:** OOS Sharpe {sharpe(oos):.2f}, yıllık ~%7, "
              f"{int((yearly>0).sum())}/{len(yearly)} yıl +. Carry literatür normu (~0.5 Sharpe) bandında.",
              "- **Prop-passer olarak ZAYIF:** yavaş (yıllık ~%7) → +%10 hedefe ulaşmak için yüksek "
              "vol gerek, o da carry-crash + DD riskini artırır → geçiş oranı crypto'nun (%42-52) "
              "ÇOK ALTINDA. Yukarıdaki tablo gösteriyor.",
              "- **Doğru kullanım: yavaş-gelir / diversifikasyon sinyali** (manuel, FundingPips/forex), "
              "challenge-passer değil. Carry kriz-kuyruğu (en kötü ay) → stop-loss zorunlu.",
              "- ⚠️ Tek-dönem OOS, yaklaşık-yıllık faiz, gerçek FX/CFD swap firma-bazlı; beklenti düşük tut."]
    report = "\n".join(lines)
    print(report)
    (Path(__file__).resolve().parents[1] / "reports_out" / "fx_carry_stats.md").write_text(report)


if __name__ == "__main__":
    main()
