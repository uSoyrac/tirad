#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
BOT_COMBO — Diversified 2-factor book (Trend + Funding-positioning)  ★ ÖNERİLEN
═══════════════════════════════════════════════════════════════════════════════
Bake-off'un risk-ayarlı GALİBİ. İki ortogonal edge'i (korelasyon ~−0.06) inverse-vol
ağırlıkla birleştirir; ağırlıklar train'de fit edilip OOS'ta uygulanır (look-ahead yok).

DÜRÜST OOS (2025-26) SONUÇ:  Sharpe ~1.74  (WF-optimize varyant ~2.25),  MaxDD ~−14%.
  - Trend kolu: 20 coin arası en güçlü momentumlu Top-3 (cross-sectional).
  - Funding kolu: yüksek-funding short / düşük-funding long, dolar-nötr (market-neutral).

⚠️ DÜRÜSTLÜK: Evren bugünün hayatta kalan coinleri (survivorship-capped; literatür
   ~%15-22/yıl şişirme). Funding kolu rejim/borsa-bağımlı. → PAPER-TRADING adayı,
   canlı sermaye DEĞİL. Tüm maliyetler (komisyon/slippage/funding) dahildir.

ÇALIŞTIRMA:  python3 bot_combo.py
═══════════════════════════════════════════════════════════════════════════════
"""
from _botlib import load_universe
import pandas as pd


def main():
    print(__doc__)
    cfg, frames, higher, targets, momentum, fundings = load_universe()
    from quantlab.backtest import metrics, combine
    from quantlab.backtest.portfolio import run_portfolio
    from quantlab.backtest.carry import run_carry
    from quantlab.paper.engine import live_targets

    cut = pd.Timestamp(cfg.splits.train_end) + pd.Timedelta(days=1)
    trend = run_portfolio(frames, targets, momentum, cfg, top_k=3)
    carry = run_carry(frames, fundings, cfg, lookback_days=7, n_side=3, rebalance_days=1)

    rt = combine.equity_to_daily_returns(trend.equity)
    rc = carry.daily_returns
    rt, rc = combine.align(rt, rc)
    wt, wc = combine.inverse_vol_weights(rt[rt.index < cut], rc[rc.index < cut])
    oos = combine.blend(rt[rt.index >= cut], rc[rc.index >= cut], wt, wc)
    full = combine.blend(rt, rc, wt, wc)

    m_oos = metrics.compute_metrics(combine.equity_from_returns(oos, cfg.risk.bankroll), [], timeframe="1d")
    m_full = metrics.compute_metrics(combine.equity_from_returns(full, cfg.risk.bankroll), [], timeframe="1d")
    corr = combine.correlation(rt, rc)

    print("PERFORMANS (dürüst, maliyetler dahil)")
    print(f"  OOS (2025-26):  Sharpe {m_oos['sharpe']:.2f} | CAGR {m_oos['cagr']*100:.1f}% | "
          f"MaxDD {m_oos['max_drawdown']*100:.1f}%")
    print(f"  Full history :  Sharpe {m_full['sharpe']:.2f} | CAGR {m_full['cagr']*100:.1f}%")
    print(f"  Kol korelasyonu: {corr:+.2f}  | Ağırlık: trend {wt:.2f} / funding {wc:.2f}")

    # --- ŞU AN NE TUTULMALI (paper sinyali) ---
    longs = live_targets(frames, cfg, top_k=3, mom_window=60)
    score = {s: fundings[s].tail(21).mean() for s in fundings}  # ~7d funding mean proxy
    ranked = sorted(score, key=score.get)
    f_long = [s for s in ranked[:3]]
    f_short = [s for s in ranked[-3:]]
    asof = max(f.index[-1] for f in frames.values())
    print(f"\nŞU ANKİ HEDEF (as-of {asof}):")
    print(f"  TREND kolu  -> LONG (en güçlü momentum Top-3): {longs or '(yok)'}")
    print(f"  FUNDING kolu-> LONG (en düşük funding): {f_long}  |  SHORT (en yüksek): {f_short}")
    print("\n⚠️ Paper-trade için. Canlı emir YOK. Boyutlandırma: kola eşit-risk (inverse-vol).")


if __name__ == "__main__":
    main()
