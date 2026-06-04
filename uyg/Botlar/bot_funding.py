#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
BOT_FUNDING — Cross-sectional Funding-positioning (ORTOGONAL edge)
═══════════════════════════════════════════════════════════════════════════════
Market-nötr: yüksek-funding (aşırı-kalabalık long) coinleri SHORT, düşük/negatif-funding
coinleri LONG, dolar-nötr. Günlük rebalance. Fiyat momentum'una ORTOGONAL — trend'in
kanadığı 2025-26 chop'unda kazandı; bu yüzden kombo'da trend'le birleşince Sharpe'ı yükseltir.

DÜRÜST OOS (2025-26):  Sharpe ~1.31 | CAGR ~33% | MaxDD ~−15%.  Funding maliyeti dahil.
⚠️ Getiriyi fiyat-pozisyonlama domine eder (saf carry değil); rejim/borsa-bağımlı;
   survivorship-capped. PAPER-TRADING adayı.

ÇALIŞTIRMA:  python3 bot_funding.py
═══════════════════════════════════════════════════════════════════════════════
"""
from _botlib import load_universe
import pandas as pd


def main():
    print(__doc__)
    cfg, frames, higher, targets, momentum, fundings = load_universe()
    from quantlab.backtest import metrics, combine
    from quantlab.backtest.carry import run_carry

    cut = pd.Timestamp(cfg.splits.train_end) + pd.Timedelta(days=1)
    res = run_carry(frames, fundings, cfg, lookback_days=7, n_side=3, rebalance_days=1)
    r = res.daily_returns[res.daily_returns.index >= cut]
    m = metrics.compute_metrics(combine.equity_from_returns(r, cfg.risk.bankroll), [], timeframe="1d")
    print("PERFORMANS (OOS 2025-26, dürüst):")
    print(f"  Sharpe {m['sharpe']:.2f} | CAGR {m['cagr']*100:.1f}% | MaxDD {m['max_drawdown']*100:.1f}%")
    fr = res.funding_pnl.iloc[-1] * 100
    pr = res.price_pnl.iloc[-1] * 100
    print(f"  Dekompozisyon (full): funding-harvest {fr:+.0f}% | fiyat-P&L {pr:+.0f}% "
          "(fiyat domine = pozisyonlama faktörü, saf carry değil)")

    score = {s: fundings[s].tail(21).mean() for s in fundings}
    ranked = sorted(score, key=score.get)
    asof = max(f.index[-1] for f in frames.values())
    print(f"\nŞU ANKİ HEDEF (as-of {asof}):")
    print(f"  LONG (en düşük funding): {ranked[:3]}")
    print(f"  SHORT (en yüksek funding): {ranked[-3:]}")
    print("  Dolar-nötr, eşit-ağırlık. Paper-trade — canlı emir YOK.")


if __name__ == "__main__":
    main()
