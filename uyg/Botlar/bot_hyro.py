#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
BOT_HYRO — HyroTrader (crypto-native prop) için boyutlandırılmış COMBO botu  ★ PROP
═══════════════════════════════════════════════════════════════════════════════
HyroTrader 700+ Bybit USDT-perp + funding sunar → DSR/PBO-doğrulanmış crypto COMBO
edge'imiz (cross-sectional momentum Top-3 + funding-positioning carry) BURADA gerçekten
çalışır (FundingPips CFD'sinde imkansızdı). ABD kolu YOK (firma crypto-only).

HyroTrader kural-uyumu (firma şartları):
  • Her işleme ≤5 dk içinde STOP-LOSS, ≤%3 işlem-başı risk  → ATR-stop + vol-hedef sağlar
  • %40 tek-işlem kâr konsantrasyonu (eval)                 → Top-3+funding çeşitli → geçer
  • Trailing DD: 1-step %6 / 2-step %10 (EOD)               → DÜŞÜK vol-hedef şart
  • Günlük: 1-step %4 / 2-step %5                           → −%3 intraday self-stop önerilir
  • Yasak: HFT / sinyal-kopyalama / cross-account hedge     → hiçbiri yok

VOL-HEDEF (Monte-Carlo prop-sim'den):
  • GEÇİCİ (challenge): ~%10-12 yıllık vol  → P(funded) ~%35-48 (2-step), patlama düşük
  • FON İÇİ (funded):   ~%7-10 yıllık vol   → hesabı koru, ~$250/ay ($25K, %80 split)

⚠️ Bu STRATEJİ/PAPER mantığıdır — CANLI Bybit API/emir kodu DEĞİL. Önce HyroTrader
   TESTNET'te paper-doğrula; tutarlıysa challenge. Canlı emir öncesi kullanıcı onayı şart.

ÇALIŞTIRMA:  quantlab/.venv/bin/python uyg/Botlar/bot_hyro.py [vol_hedef]
═══════════════════════════════════════════════════════════════════════════════
"""
import sys
import warnings

import numpy as np
import pandas as pd

from _botlib import load_universe

warnings.filterwarnings("ignore")

CUT = pd.Timestamp("2025-01-01")
PPY = 365
MAX_LEV = 3.0
VOL_LOOKBACK = 20
PER_TRADE_RISK_CAP = 0.03   # HyroTrader: <=3% per-trade risk (stop-loss rule)


def vol_target(returns: pd.Series, target: float, lookback=VOL_LOOKBACK, maxlev=MAX_LEV) -> pd.Series:
    """Scale daily returns to a target annual vol using LAGGED realized vol (no-lookahead)."""
    realized = returns.rolling(lookback).std().shift(1) * np.sqrt(PPY)
    lev = (target / realized).clip(upper=maxlev).fillna(0.0)
    return (returns * lev).dropna()


def main(target_vol=0.10):
    print(__doc__)
    cfg, frames, higher, targets, momentum, fundings = load_universe()
    from quantlab.backtest.portfolio import run_portfolio
    from quantlab.backtest.carry import run_carry
    from quantlab.backtest import combine
    from quantlab.paper.engine import live_targets

    # crypto-only combo (no US sleeve — HyroTrader is crypto-native)
    trend = combine.equity_to_daily_returns(run_portfolio(frames, targets, momentum, cfg, top_k=3).equity)
    carry = run_carry(frames, fundings, cfg, lookback_days=7, n_side=3, rebalance_days=1).daily_returns
    rt, rc = combine.align(trend, carry)
    wt, wc = combine.inverse_vol_weights(rt[rt.index < CUT], rc[rc.index < CUT])
    combo = combine.blend(rt, rc, wt, wc)
    sized = vol_target(combo, target_vol)

    def stats(r):
        o = r[r.index >= CUT]
        eq = (1 + o).cumprod()
        sh = float(o.mean() / o.std() * np.sqrt(PPY)) if o.std() > 0 else float("nan")
        cg = eq.iloc[-1] ** (PPY / len(o)) - 1 if len(o) else float("nan")
        md = float((eq / eq.cummax() - 1).min()) if len(o) else float("nan")
        return sh, cg, md

    s0, c0, m0 = stats(combo)
    s1, c1, m1 = stats(sized)
    avg_lev = float((sized / combo.reindex(sized.index)).replace([np.inf, -np.inf], np.nan)
                    .loc[lambda x: x.index >= CUT].mean())

    print(f"\n=== HYRO COMBO (kripto trend+funding) — vol-hedef %{target_vol*100:.0f} ===")
    print(f"Ağırlık: trend {wt:.2f} | funding {wc:.2f}")
    print(f"Kaldıraçsız OOS : Sharpe {s0:.2f} | CAGR {c0*100:.0f}% | MaxDD {m0*100:.0f}%")
    print(f"%{target_vol*100:.0f} vol-hedef : Sharpe {s1:.2f} | CAGR {c1*100:.0f}% | MaxDD {m1*100:.0f}% | ort.kaldıraç {avg_lev:.2f}x")

    ct = live_targets(frames, cfg, top_k=3, mom_window=60)
    score = {s: fundings[s].tail(21).mean() for s in fundings}
    ranked = sorted(score, key=score.get)
    asof = max(f.index[-1] for f in frames.values())
    print(f"\nŞU ANKİ HEDEF (as-of {asof.date()}, %{target_vol*100:.0f} vol-hedefli, her pozisyona ATR-stop ≤%3 risk):")
    print(f"  KRİPTO-TREND   -> LONG {ct or '(nakit)'}")
    print(f"  KRİPTO-FUNDING -> LONG {ranked[:3]} | SHORT {ranked[-3:]}")
    print(f"\nHyroTrader kuralı: her işleme ≤5dk içinde SL (≤%{PER_TRADE_RISK_CAP*100:.0f} risk), "
          "−%3 intraday self-stop önerilir, Top-3+funding %40-konsantrasyonu doğal geçer.")
    print("\n⚠️ STRATEJİ/PAPER. Canlı Bybit API/emir YOK. Önce testnet paper, sonra kullanıcı onayı.")


if __name__ == "__main__":
    tv = float(sys.argv[1]) if len(sys.argv) > 1 else 0.10
    main(tv)
