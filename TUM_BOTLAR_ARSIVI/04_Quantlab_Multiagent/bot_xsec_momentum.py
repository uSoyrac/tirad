#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
BOT_XSEC_MOMENTUM — Cross-sectional Top-3 Momentum (en yüksek DOĞRU-KARAR oranı)
═══════════════════════════════════════════════════════════════════════════════
Her bar 20 coin arasından en güçlü momentumlu (60-bar ROC) ve trend-sinyali veren
EN İYİ 3 coini tutar. Bake-off'ta en yüksek win-rate'li +EV strateji.

DÜRÜST OOS (2025-26):  Win-rate %41.8 | Beklenti +$70/işlem | Sharpe ~1.12 | RoR %12.
  Düşüş/chop'ta bile bazı coinler güçlü trend yapar; en güçlü birkaçını seçmek dispersiyonu
  yakalar, kanayan gerisini atlar. Maliyetler (komisyon/slippage) dahil.

⚠️ Survivorship-capped (bugünün hayatta kalanları); tek başına random alt-evrende
   kırılgan (kombo daha sağlam). PAPER-TRADING adayı, canlı DEĞİL.

ÇALIŞTIRMA:  python3 bot_xsec_momentum.py
═══════════════════════════════════════════════════════════════════════════════
"""
from _botlib import load_universe
import pandas as pd


def main():
    print(__doc__)
    cfg, frames, higher, targets, momentum, fundings = load_universe()
    from quantlab.backtest import metrics
    from quantlab.backtest.portfolio import run_portfolio
    from quantlab.paper.engine import live_targets

    cut = pd.Timestamp(cfg.splits.train_end) + pd.Timedelta(days=1)
    res = run_portfolio(frames, targets, momentum, cfg, top_k=3)
    oos_eq = res.equity[res.equity.index >= cut]
    oos_tr = [t for t in res.trades if pd.Timestamp(t.entry_ts) >= cut]
    m = metrics.compute_metrics(oos_eq, oos_tr, timeframe="4h",
                                ruin_drawdown=cfg.risk.total_dd_killswitch, seed=cfg.seed)
    print("PERFORMANS (OOS 2025-26, dürüst):")
    print(f"  Win-rate {m['win_rate']*100:.1f}% | Beklenti {m['expectancy']:+.2f}$/işlem | "
          f"Sharpe {m['sharpe']:.2f} | CAGR {m['cagr']*100:.1f}% | MaxDD {m['max_drawdown']*100:.1f}% | "
          f"İşlem {m['n_trades']} | RoR {m['risk_of_ruin']*100:.1f}%")

    longs = live_targets(frames, cfg, top_k=3, mom_window=60)
    asof = max(f.index[-1] for f in frames.values())
    print(f"\nŞU ANKİ HEDEF (as-of {asof}): LONG {longs or '(sinyal yok / nakit)'}")
    print("  Sermaye 3 slota eşit bölünür; ATR-stop ile yönetilir. Paper-trade — canlı emir YOK.")


if __name__ == "__main__":
    main()
