"""SON-8-AY KONSOLİDE RAPOR — 3 bot (Binance compound + 2 prop) gerçek sonuçları.

Çıktı: prop'larda kaç challenge alındı / kaç funded / içerde kaç kez kâr-al (payout); Binance
compound'da $1000 → kaç para. Gerçek getiri akışları (combo + us_momentum), firma kuralları,
survivorship haircut. Arşive (README/AGENT.md) gömülecek rapor.

Usage: python scripts/run_8month_report.py
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
HAIRCUT = 0.60


def streams():
    R = pd.read_parquet(SLEEVE3)
    iv = 1.0 / R[R.index < CUT][["crypto_trend", "crypto_funding"]].std()
    combo = (R[["crypto_trend", "crypto_funding"]] * (iv / iv.sum())).sum(axis=1)
    return combo, R["us_momentum"].dropna()


def vol_target(r, target, lb=20):
    realized = r.rolling(lb).std().shift(1) * np.sqrt(PPY)
    return (r * (target / realized).clip(upper=3.0).fillna(0.0)).dropna()


def haircut(r, keep=HAIRCUT):
    return (r - r.mean()) + r.mean() * keep


def last8(r):
    end = r.index[-1]
    return r[(r.index >= end - pd.DateOffset(months=8)) & (r.index <= end)]


def farm(r, phases, daily, total, trailing, account, fee, refundable, withdraw, split):
    """Sıralı challenge-farming: challenge al → faz geç → funded → kâr-al (withdraw) → tekrar."""
    arr = r.to_numpy()
    state = "buy"; eq = peak = 1.0; pidx = dphase = 0; refunded = False
    n_buy = passes = fails = blow = n_wd = 0; fee_paid = wd = refund = 0.0
    i = 0
    while i < len(arr):
        if state == "buy":
            fee_paid += fee; n_buy += 1; eq = peak = 1.0; pidx = dphase = 0; refunded = False; state = "ch"
        ret = arr[i]; i += 1; dphase += 1
        if state == "ch":
            if ret <= daily: fails += 1; state = "buy"; continue
            eq *= (1 + ret); peak = max(peak, eq)
            floor = peak * (1 + total) if trailing else (1 + total)
            if eq <= floor: fails += 1; state = "buy"; continue
            tgt, mind = phases[pidx]
            if eq >= 1 + tgt and dphase >= mind:
                pidx += 1
                if pidx >= len(phases): passes += 1; state = "funded"; eq = peak = 1.0
                else: eq = peak = 1.0; dphase = 0
        elif state == "funded":
            if ret <= daily: blow += 1; state = "buy"; continue
            eq *= (1 + ret); peak = max(peak, eq)
            floor = peak * (1 + total) if trailing else (1 + total)
            if eq <= floor: blow += 1; state = "buy"; continue
            if (eq - 1) * account * split >= withdraw:
                wd += withdraw; n_wd += 1
                if refundable and not refunded: refund += fee; refunded = True
                eq = peak = 1.0
    return dict(challenge=n_buy, funded=passes, fail=fails, blowup=blow, payout=n_wd,
                withdrawn=wd, refund=refund, fee=fee_paid, net=wd + refund - fee_paid)


def compound(r, kelly_frac=0.25, start=1000.0):
    mu, var = r[r.index < CUT].mean(), r[r.index < CUT].var()
    lev = max(0.0, kelly_frac * (mu / var if var > 0 else 1.0))
    o = last8(r); eq = peak = start
    for ret in o:
        live = lev * (0.5 if eq <= peak * 0.8 else 1.0)
        eq *= (1 + ret * live); peak = max(peak, eq)
    return eq


def main():
    combo, usm = streams()
    combo_h = haircut(combo); usm_h = haircut(usm)
    # crypto combo @15% vol; us momentum native (zaten ~%25 vol)
    c15 = last8(vol_target(combo_h, 0.15))
    c20 = last8(vol_target(combo_h, 0.20))
    e08 = last8(vol_target(usm_h, 0.08))    # TTP %4 DD için düşük vol

    # PROP 1: HyroTrader crypto (2-step, $5K, $59 iade, trailing)
    hyro = farm(c20, [(0.10, 10), (0.05, 5)], -0.05, -0.10, True, 5000, 59, True, 200, 0.80)
    # PROP 2: Trade The Pool hisse (1-step Flex, $5K, $53 iade-yok, statik, %70 split)
    ttp = farm(e08, [(0.06, 3)], -0.02, -0.04, False, 5000, 53, False, 300, 0.70)
    # BİNANCE compound (kendi sermaye, combo %15, ¼-Kelly)
    bnc14 = compound(vol_target(combo_h, 0.15), 0.25, 1000.0)
    bnc_half = compound(vol_target(combo_h, 0.15), 0.5, 1000.0)

    win = c15
    lines = ["# SON-8-AY KONSOLİDE RAPOR — 3-bot operasyonu (gerçek getiriler, haircut'lı)", "",
             f"Pencere: {win.index[0].date()}→{win.index[-1].date()}. Combo (DSR/PBO-gerçek) + US-momentum. "
             f"Survivorship haircut ×{HAIRCUT}. ⚠️ 2025-26 cömert rejim — gerçekçi tavan.", "",
             "## 🏦 PROP 1 — HyroTrader (crypto, $5K, $59 İADE-edilebilir, 2-step)", "",
             f"- Alınan challenge: **{hyro['challenge']}** | Funded olunan: **{hyro['funded']}** | "
             f"Başarısız: {hyro['fail']} | Funded patlama: {hyro['blowup']}",
             f"- İÇERDE kâr-al (payout): **{hyro['payout']} kez × $200 = ${hyro['withdrawn']:.0f}** | "
             f"ücret iadesi ${hyro['refund']:.0f} | ödenen ${hyro['fee']:.0f}",
             f"- **NET (8 ay): ${hyro['net']:,.0f}**", "",
             "## 🏦 PROP 2 — Trade The Pool (hisse, $5K, $53, 1-step Flex, %70 split)", "",
             f"- Alınan challenge: **{ttp['challenge']}** | Funded: **{ttp['funded']}** | "
             f"Başarısız: {ttp['fail']} | patlama: {ttp['blowup']}",
             f"- İÇERDE kâr-al (payout): **{ttp['payout']} kez × $300 = ${ttp['withdrawn']:.0f}**",
             f"- **NET (8 ay): ${ttp['net']:,.0f}** (ücret iade YOK)", "",
             "## 🚀 BİNANCE — kendi sermaye compound ($1000 başlangıç, combo %15 vol)", "",
             f"- ¼-Kelly compound: **$1000 → ${bnc14:,.0f}** ({(bnc14/1000-1)*100:+.0f}%)",
             f"- ½-Kelly compound (agresif): $1000 → ${bnc_half:,.0f} ({(bnc_half/1000-1)*100:+.0f}%)", "",
             "## ÖZET", "",
             "| Kol | 8-ay net/büyüme |", "|---|---|",
             f"| Prop HyroTrader (crypto) | challenge {hyro['challenge']}, funded {hyro['funded']}, "
             f"payout {hyro['payout']}× → net ${hyro['net']:.0f} |",
             f"| Prop Trade The Pool (hisse) | challenge {ttp['challenge']}, funded {ttp['funded']}, "
             f"payout {ttp['payout']}× → net ${ttp['net']:.0f} |",
             f"| Binance compound (¼-Kelly) | $1000 → ${bnc14:,.0f} |", "",
             "⚠️ Tek-yol simülasyon, haircut'lı, cömert rejim. Gerçek = forward kanıt. ≤¼-Kelly tavanı."]
    report = "\n".join(lines)
    print(report)
    out = Path(__file__).resolve().parents[1] / "reports_out" / "report_8month.md"
    out.write_text(report)
    print(f"\nSaved -> {out}")


if __name__ == "__main__":
    main()
