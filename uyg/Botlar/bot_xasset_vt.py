#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
BOT_XASSET_VT — 3-kollu ÇAPRAZ-VARLIK kitabı + %15 VOL-HEDEF  ★★★ OPTIMAL (EN SON)
═══════════════════════════════════════════════════════════════════════════════
bot_xasset'in (DSR 1.00 / PBO 0.01 ile doğrulanmış 3-kollu kitap) üzerine, tüm
araştırmanın gösterdiği TEK yeni-alfa-gerektirmeyen "daha çok para" kaldıracını ekler:
DİNAMİK VOL-HEDEFLEME. Sharpe kaldıraçtan bağımsızdır; vol-hedef sağlam edge'i
stomach-edilebilir bir drawdown'a göre kontrollü bileşik büyümeye çevirir.

  Kitap = inverse-vol(kripto-trend Top-3 + kripto-funding + ABD-momentum), train'de fit.
  Boyut = her gün, 20-gün LAGGED gerçekleşen vol ile hedef %15 yıllık vol'a ölçekle (≤3x).

DÜRÜST OOS (2025-26):  kaldıraçsız Sharpe ~2.40; %15 vol-hedefte CAGR ~%49-55,
  MaxDD ~−10/−12%, Sharpe ~sabit. f* (Kelly) şişkin → ≤¼-Kelly tavanı; %15 güvenli bant.

⚠️ DÜRÜSTLÜK: survivorship-capped (lit. ~%15-22/yıl şişirme) → işaret sağlam, mutlak
   büyüklük iyimser. OOS>IS şanslı 2025-26 rejimini yansıtır → beklentiyi haircut'la.
   ABD kolu yfinance ister. PAPER-TRADE adayı, CANLI SERMAYE DEĞİL. Emir kodu yok.

ÇALIŞTIRMA:  quantlab/.venv/bin/python uyg/Botlar/bot_xasset_vt.py
═══════════════════════════════════════════════════════════════════════════════
"""
import warnings

import numpy as np
import pandas as pd

from _botlib import load_universe
from bot_xasset import _us_sleeve  # reuse the exact US-momentum sleeve

warnings.filterwarnings("ignore")

CUT = pd.Timestamp("2025-01-01")
PPY = 365            # crypto trades every day (matches paper_runner convention)
TARGET_VOL = 0.15    # annual vol target — the honest "more money" dial
MAX_LEV = 3.0
VOL_LOOKBACK = 20


def vol_target(returns: pd.Series, target=TARGET_VOL, lookback=VOL_LOOKBACK, maxlev=MAX_LEV) -> pd.Series:
    """Scale daily returns to a target annual vol using LAGGED realized vol (no-lookahead)."""
    realized = returns.rolling(lookback).std().shift(1) * np.sqrt(PPY)
    lev = (target / realized).clip(upper=maxlev).fillna(0.0)
    return (returns * lev).dropna()


def main():
    print(__doc__)
    cfg, frames, higher, targets, momentum, fundings = load_universe()
    from quantlab.backtest.portfolio import run_portfolio
    from quantlab.backtest.carry import run_carry
    from quantlab.backtest import combine
    from quantlab.paper.engine import live_targets

    trend = combine.equity_to_daily_returns(run_portfolio(frames, targets, momentum, cfg, top_k=3).equity)
    carry = run_carry(frames, fundings, cfg, lookback_days=7, n_side=3, rebalance_days=1).daily_returns
    print("ABD hisse kolu çekiliyor (yfinance)...")
    usret, us_long = _us_sleeve(cfg)

    sleeves = {"crypto_trend": trend, "crypto_funding": carry}
    if usret is not None:
        sleeves["us_momentum"] = usret
    R = pd.DataFrame(sleeves).dropna()
    Rtr = R[R.index < CUT]
    iv = 1.0 / Rtr.std()
    w = iv / iv.sum()
    book = (R * w).sum(axis=1)
    book_vt = vol_target(book)

    def stats(r):
        o = r[r.index >= CUT]
        eq = (1 + o).cumprod()
        sh = float(o.mean() / o.std() * np.sqrt(PPY)) if o.std() > 0 else float("nan")
        cg = eq.iloc[-1] ** (PPY / len(o)) - 1 if len(o) else float("nan")
        md = float((eq / eq.cummax() - 1).min()) if len(o) else float("nan")
        return sh, cg, md

    s0, c0, m0 = stats(book)
    s1, c1, m1 = stats(book_vt)
    avg_lev = float((book_vt / book.reindex(book_vt.index)).replace([np.inf, -np.inf], np.nan)
                    .loc[lambda x: x.index >= CUT].mean())

    print(f"\n=== ÇAPRAZ-VARLIK KİTABI + %15 VOL-HEDEF ({len(R.columns)} kol) ===")
    print(f"Kaldıraçsız OOS : Sharpe {s0:.2f} | CAGR {c0*100:.0f}% | MaxDD {m0*100:.0f}%")
    print(f"%15 vol-hedef   : Sharpe {s1:.2f} | CAGR {c1*100:.0f}% | MaxDD {m1*100:.0f}% | ort.kaldıraç {avg_lev:.2f}x")
    print("Ağırlıklar (inverse-vol, train-fit): " + " | ".join(f"{k} {v:.2f}" for k, v in w.items()))

    ct = live_targets(frames, cfg, top_k=3, mom_window=60)
    score = {s: fundings[s].tail(21).mean() for s in fundings}
    ranked = sorted(score, key=score.get)
    asof = max(f.index[-1] for f in frames.values())
    print(f"\nŞU ANKİ HEDEF (as-of {asof.date()}, %15 vol-hedefli boyutlandırma ile):")
    print(f"  1) KRİPTO-TREND   -> LONG {ct or '(nakit)'}")
    print(f"  2) KRİPTO-FUNDING -> LONG {ranked[:3]} | SHORT {ranked[-3:]}")
    print(f"  3) ABD-MOMENTUM   -> LONG {us_long or '(yok/offline)'}")
    print("\n⚠️ Paper-trade adayı. Canlı emir YOK. Survivorship-capped — ileriye-dönük doğrula.")


if __name__ == "__main__":
    main()
