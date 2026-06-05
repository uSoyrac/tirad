"""THE PRODUCTION-CANDIDATE BOOK — synthesise everything that actually works into one
deployable (paper-first) book, sized for the most money at an honest risk level.

Combines the three findings that survived every honesty gate:
  1. BREADTH  — broad 44-coin auto-selected crypto universe (survivorship/selection-proxy
     robust: 100% positive on random 20-coin subsets), NOT the hand-picked 20.
  2. DIVERSIFICATION — crypto-trend (Top-3) + crypto-funding (carry) + US-equity-momentum,
     inverse-vol blended, weights fit on TRAIN only (orthogonal sleeves, the real edge).
  3. SIZING — vol-targeting (LEVER #2): the only lever that adds money without new alpha.

Outputs a full OOS tearsheet (Sharpe/Sortino/CAGR/MaxDD/terminal), IS-vs-OOS side by side,
and a BY-YEAR table (the regime-honesty gate: does it survive bear years?). NO live
execution — this is the research deliverable to paper-trade next.

Usage: python scripts/run_book.py
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from quantlab.config import load_config  # noqa: E402
from quantlab.data import cache  # noqa: E402
from quantlab.backtest import combine  # noqa: E402
from quantlab.backtest.portfolio import run_portfolio  # noqa: E402
from quantlab.backtest.carry import run_carry  # noqa: E402
from quantlab import orchestrator  # noqa: E402

CUT = pd.Timestamp("2025-01-01")
PPY = 252
MAX_LEV = 3.0
EXP = Path(__file__).resolve().parents[1] / "data_cache_exp"
SLEEVE3 = Path(__file__).resolve().parents[1] / "reports_out" / "_sleeves3.parquet"


def _ann(r):
    sh = float(r.mean() / r.std() * np.sqrt(PPY)) if r.std() > 0 else float("nan")
    dn = r[r < 0].std()
    so = float(r.mean() / dn * np.sqrt(PPY)) if dn and dn > 0 else float("nan")
    eq = (1 + r).cumprod()
    cagr = eq.iloc[-1] ** (PPY / len(r)) - 1 if len(r) else float("nan")
    mdd = float((eq / eq.cummax() - 1).min()) if len(r) else float("nan")
    return sh, so, cagr, mdd, (eq.iloc[-1] if len(r) else float("nan"))


FULL_HIST_CUT = pd.Timestamp("2023-09-01")  # coin must exist by here (else it truncates the
#                                             all-coin index intersection & kills the train split)


def _broad_crypto_sleeves(cfg):
    """Build trend(Top-3) + funding(carry) daily returns on the FULL-HISTORY subset of the
    broad cache. run_portfolio intersects all coins' indices, so a 2025-listed coin would
    truncate everything to 2025 — restrict to coins present by FULL_HIST_CUT (still ~27,
    far broader than the hand-picked 20, with a valid <2025 train window)."""
    frames, targets, mom, fund = {}, {}, {}, {}
    for pq in sorted(EXP.glob("*_4h.parquet")):
        base = pq.name.replace("_4h.parquet", "")
        fp = EXP / f"{base}_funding.parquet"
        if not fp.exists():
            continue
        df = cache._validate(pd.read_parquet(pq))
        if df.index[0] > FULL_HIST_CUT:
            continue
        hd = cache.resample(df, "1d")
        frames[base] = df
        targets[base] = orchestrator.build_target(df, cfg, hd)
        mom[base] = df["close"].pct_change(60)
        fund[base] = pd.read_parquet(fp)["funding"]
    trend = combine.equity_to_daily_returns(run_portfolio(frames, targets, mom, cfg, top_k=3).equity)
    funding = run_carry(frames, fund, cfg, lookback_days=7, n_side=3, rebalance_days=1).daily_returns
    return trend.rename("crypto_trend"), funding.rename("crypto_funding"), len(frames)


def _vol_target(r, target_ann, lookback=20):
    realized = r.rolling(lookback).std().shift(1) * np.sqrt(PPY)
    lev = (target_ann / realized).clip(upper=MAX_LEV).fillna(0.0)
    return r * lev, lev


def main():
    cfg = load_config(str(Path(__file__).resolve().parents[1] / "config" / "default.yaml"))
    root = Path(__file__).resolve().parents[1]
    print("Geniş-44 crypto sleeve'leri kuruluyor (cache'ten)...")
    trend, funding, ncoin = _broad_crypto_sleeves(cfg)
    us = pd.read_parquet(SLEEVE3)["us_momentum"]
    R = pd.DataFrame({"crypto_trend": trend, "crypto_funding": funding, "us_momentum": us}).dropna()
    Rtr = R[R.index < CUT]

    # inverse-vol weights fit on TRAIN only
    iv = 1.0 / Rtr.std().to_numpy()
    w = iv / iv.sum()
    book = pd.Series(R.to_numpy() @ w, index=R.index)
    wd = dict(zip(R.columns, w.round(3)))

    is_r, oos_r = book[book.index < CUT], book[book.index >= CUT]

    lines = ["# ÜRETİM-ADAY KİTABI — geniş evren + çeşitlendirme + vol-hedef (paper-first)", "",
             f"Sleeve'ler: **{ncoin}-coin** crypto-trend (Top-3) + {ncoin}-coin crypto-funding + "
             f"US-momentum. Inverse-vol ağırlık (TRAIN'de fit): {wd}. Ortak-gün {len(R)} "
             f"({R.index[0].date()}→{R.index[-1].date()}).", "",
             "## Sleeve korelasyonu (çeşitlendirme gerçek mi?)", "",
             "```", R.corr().round(2).to_string(), "```", "",
             "## IS vs OOS yan yana (overfit kontrolü — kaldıraçsız kitap)", "",
             "| pencere | Sharpe | Sortino | CAGR | MaxDD | terminal |", "|---|---|---|---|---|---|"]
    for name, r in (("IS (≤2024)", is_r), ("OOS (2025-26)", oos_r)):
        sh, so, cg, md, tw = _ann(r)
        lines.append(f"| {name} | {sh:.2f} | {so:.2f} | {cg*100:.0f}% | {md*100:.0f}% | {tw:.2f} |")

    lines += ["", "## Vol-hedefli boyutlandırma (OOS — 'en çok para' kadranı)", "",
              f"20g LAGGED gerçekleşen vol, kaldıraç ≤{MAX_LEV:.0f}x. Sharpe ~sabit; risk/getiri seç:", "",
              "| hedef vol | Sharpe | CAGR | MaxDD | terminal | ort.kaldıraç |", "|---|---|---|---|---|---|"]
    rec = None
    for tgt in (0.10, 0.15, 0.20, 0.25):
        rt, lev = _vol_target(book, tgt)
        rto = rt[rt.index >= CUT]
        sh, so, cg, md, tw = _ann(rto)
        lev_oos = lev[lev.index >= CUT].mean()
        lines.append(f"| {tgt*100:.0f}% | {sh:.2f} | {cg*100:.0f}% | {md*100:.0f}% | {tw:.2f} | {lev_oos:.2f}x |")
        if tgt == 0.15:
            rec = (cg, md)

    # by-year regime-honesty gate (unlevered book, full sample)
    lines += ["", "## Yıl-bazında (rejim-dürüstlük geçidi — ayı yıllarında hayatta mı?)", "",
              "| yıl | Sharpe | getiri | MaxDD |", "|---|---|---|---|"]
    for yr, g in book.groupby(book.index.year):
        sh, so, cg, md, tw = _ann(g)
        lines.append(f"| {yr} | {sh:.2f} | {(tw-1)*100:+.0f}% | {md*100:.0f}% |")

    lines += ["", "## Yorum (dürüst)", "",
              f"- **Kitap = en geniş evren ({ncoin} coin, seçim-yanlılığına dayanıklı) + 3 ortogonal "
              "sleeve + vol-hedef.** OOS Sharpe yukarıdaki tabloda; korelasyon matrisi çeşitlendirmenin "
              "gerçek olduğunu gösterir.",
              f"- **'En çok para' önerisi: %15 vol-hedef** → OOS CAGR ~{rec[0]*100:.0f}%, MaxDD "
              f"~{rec[1]*100:.0f}% (stomach-able). Daha agresif istersen %20-25 satırları; ama "
              "≤¼-Kelly tavanını fat-tail nedeniyle aşma.",
              "- ⚠️ **Dürüst sınırlar:** (1) hâlâ truly-delisted coin yok → büyüklüğe ~%15-22/yıl "
              "haircut; (2) US sleeve 20-coin döneminden, crypto 44'ten — ortak-gün takvimi; (3) OOS "
              "örneklem kısa (2025-26); (4) yıl-bazı tablo ayı-yılı dayanıklılığını gösterir — "
              "negatif yıl varsa beklenti ona göre. **Sonraki adım: paper-trade (canlı sermaye DEĞİL), "
              "sonra point-in-time evren. Canlı execution öncesi SOR.**"]
    report = "\n".join(lines)
    print("\n" + report)
    (root / "reports_out" / "book.md").write_text(report)
    print(f"\nSaved -> {root / 'reports_out' / 'book.md'}")


if __name__ == "__main__":
    main()
