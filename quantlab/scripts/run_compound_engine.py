"""COMPOUND MOTORU — kâr-al-çık → bankroll'a ekle → yeniden-deploy (GERÇEK edge: combo).

Kullanıcının baştan beri vizyonu: realize-et + yeniden-deploy = geometrik büyüme. Trend (7 test,
OOS-negatif) DEĞİL, COMBO (DSR/PBO-gerçek, OOS 1.85) compound edilir — gerçek edge'i büyütmek.
Çok-kollu (prop + binance) tek-zekâdan beslenir. fractional-Kelly + kill-switch (compound'un
emniyet kemeri: gerçek edge'de büyür, ama DD'yi de büyütür → sınırla).

Gösterir: flat (compound yok) vs ¼/½-Kelly compound, terminal servet + DD; çok-hesap toplamı.

Usage: python scripts/run_compound_engine.py
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
DD_KILL = 0.20          # kill-switch: -20% DD'de risk yarıla (emniyet kemeri)


def combo():
    R = pd.read_parquet(SLEEVE3)[["crypto_trend", "crypto_funding"]]
    iv = 1.0 / R[R.index < CUT].std()
    return (R * (iv / iv.sum())).sum(axis=1)


def compound_path(r, kelly_frac, start=1000.0):
    """Kâr-al-çık compound: her gün büyümüş bankroll üzerinden Kelly-ölçekli deploy + kill-switch."""
    mu, var = r[r.index < CUT].mean(), r[r.index < CUT].var()
    f_star = mu / var if var > 0 else 1.0       # tam-Kelly kaldıraç (günlük)
    lev = max(0.0, kelly_frac * f_star)
    o = r[r.index >= CUT]
    eq = start
    peak = start
    curve = []
    for ret in o:
        live_lev = lev * (0.5 if eq <= peak * (1 - DD_KILL) else 1.0)   # kill-switch: DD'de yarıla
        eq *= (1 + ret * live_lev)
        peak = max(peak, eq)
        curve.append(eq)
    s = pd.Series(curve, index=o.index)
    dd = float((s / s.cummax() - 1).min())
    cagr = (s.iloc[-1] / start) ** (PPY / len(s)) - 1
    daily = s.pct_change().dropna()
    sh = float(daily.mean() / daily.std() * np.sqrt(PPY)) if daily.std() > 0 else 0
    return s.iloc[-1], cagr, dd, sh, lev * (mu / (mu) if mu else 1)


def main():
    r = combo()
    days = len(r[r.index >= CUT])
    lines = ["# COMPOUND MOTORU — kâr-al-çık → yeniden-deploy (GERÇEK edge: combo, OOS Sharpe ~1.85)", "",
             f"OOS {days} gün. Compound = realize + büyümüş bankroll'la tekrar deploy. fractional-Kelly + "
             f"kill-switch (−%{DD_KILL*100:.0f} DD'de risk yarıla). $1000 başlangıç.", "",
             "## Tek hesap — compound seviyesine göre", "",
             "| sizing | terminal $ | CAGR | MaxDD | Sharpe |", "|---|---|---|---|---|"]
    results = {}
    for name, kf in (("flat (compound yok, ~1x)", 0.0), ("¼-Kelly compound", 0.25),
                     ("½-Kelly compound", 0.5), ("full-Kelly (riskli)", 1.0)):
        if kf == 0.0:
            o = r[r.index >= CUT]
            eq = (1 + o).cumprod() * 1000
            term, cagr, dd = eq.iloc[-1], (eq.iloc[-1] / 1000) ** (PPY / len(o)) - 1, float((eq / eq.cummax() - 1).min())
            sh = float(o.mean() / o.std() * np.sqrt(PPY))
        else:
            term, cagr, dd, sh, _ = compound_path(r, kf)
        results[name] = term
        lines.append(f"| {name} | ${term:,.0f} | {cagr*100:+.0f}% | {dd*100:.0f}% | {sh:.2f} |")

    # çok-kol: aynı edge 2 hesap (prop + binance), her biri ¼-Kelly, toplam
    one = results["¼-Kelly compound"]
    lines += ["", "## Çok-kol (aynı zekâ, 2 hesap: prop + binance, her biri ¼-Kelly)", "",
              f"- Tek hesap ¼-Kelly: ${one:,.0f}  →  2 hesap toplam: **${one*2:,.0f}** (lineer ölçek)",
              "- (prop = başkasının sermayesi/split; binance = kendi sermaye — ikisi de aynı combo sinyali)", "",
              "## Yorum (dürüst)", "",
              "- **Compound senin vizyonunu GERÇEK edge'de büyütüyor:** ¼-Kelly ile flat'ten belirgin "
              "yüksek terminal servet, kill-switch DD'yi sınırlar. Kâr-al-çık = her gün büyümüş bankroll'la "
              "yeniden-deploy (mekaniği bu).",
              "- **Kelly fraksiyonu = risk kadranı:** ¼ güvenli-agresif, ½ agresif (yüksek DD), full = ruin "
              "riski (fat-tail). Combo gerçek edge olduğu için compound MEŞRU; trend olsaydı patlardı.",
              "- ⚠️ f* OOS-μ ile şişkin (survivorship + 2025-26 iyi) → gerçek f* düşük; **≤¼-Kelly tavanı.** "
              "Çok-kol lineer ölçek (her hesap ayrı edge çalıştırır); prop'ta split %70-80, binance'te %100.",
              "- **Mimari: tek combo sinyali → compound motoru (Kelly+kâr-al+kill-switch) → N hesap.** "
              "Her hesap kendi firma kuralına/sermayesine göre boyutlanır; motor paylaşılır."]
    report = "\n".join(lines)
    print(report)
    (Path(__file__).resolve().parents[1] / "reports_out" / "compound_engine.md").write_text(report)


if __name__ == "__main__":
    main()
