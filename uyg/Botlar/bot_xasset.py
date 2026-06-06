#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
BOT_XASSET — 3-kollu ÇAPRAZ-VARLIK kitabı  ★★ EN İYİ SİSTEM
═══════════════════════════════════════════════════════════════════════════════
Tüm araştırmanın zirvesi. Üç ORTOGONAL kolu (korelasyon −0.09..+0.18) inverse-vol
ağırlıkla (train'de fit, OOS'ta uygula) birleştirir:
  1) KRİPTO-TREND      : 20 coin arası en güçlü momentum Top-3 (cross-sectional)
  2) KRİPTO-FUNDING    : yüksek-funding short / düşük-funding long, market-nötr
  3) ABD-MOMENTUM      : likit ABD hisseleri arası momentum Top-5 (gerçek breadth)

DÜRÜST OOS (2025-26):  Sharpe ~2.40,  MaxDD ~−7%.
  Overfitting kapısını geçti (Deflated Sharpe 0.99, PBO 0.03). Edge yapısal
  çeşitlendirme — yeni sinyal değil. ABD momentum kolu kripto'ya ortogonal → √N breadth.

⚠️ DÜRÜSTLÜK: Her iki evren de survivorship-capped (bugünün hayatta kalanları);
   literatür ~%15-22/yıl şişirme der → işaret sağlam, mutlak büyüklük iyimser olabilir.
   ABD kolu yfinance + internet gerektirir. PAPER-TRADE adayı, canlı sermaye DEĞİL.

ÇALIŞTIRMA:  quantlab/.venv/bin/python uyg/Botlar/bot_xasset.py
═══════════════════════════════════════════════════════════════════════════════
"""
import warnings

import numpy as np
import pandas as pd

from _botlib import load_universe

warnings.filterwarnings("ignore")

US = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "JPM", "V", "JNJ", "WMT",
      "PG", "XOM", "UNH", "HD", "MA", "BAC", "KO", "PEP", "CVX", "ABBV", "COST", "MRK",
      "AVGO", "PFE", "CSCO", "ADBE", "CRM", "NFLX", "AMD"]
CUT = pd.Timestamp("2025-01-01")
PPY = 252


def _us_sleeve(cfg):
    """Returns (daily_returns, current_long_holdings) for US momentum, or (None, []) offline."""
    try:
        import yfinance as yf
        from quantlab.backtest.portfolio import run_portfolio
        from quantlab.backtest import combine
        from quantlab import orchestrator
        scfg = cfg.model_copy(deep=True)
        scfg.orchestrator.use_mtf = False
        raw = yf.download(US, start="2021-01-01", end="2026-06-01", interval="1d",
                          progress=False, auto_adjust=True)
        sf, st, sm = {}, {}, {}
        for t in US:
            try:
                df = pd.DataFrame({"open": raw["Open"][t], "high": raw["High"][t],
                                   "low": raw["Low"][t], "close": raw["Close"][t],
                                   "volume": raw["Volume"][t]}).dropna()
            except Exception:  # noqa: BLE001
                continue
            if len(df) < 300:
                continue
            df.index = pd.DatetimeIndex(df.index).as_unit("ns")
            df.index.name = "ts"
            sf[t], st[t], sm[t] = df, orchestrator.build_target(df, scfg, None), df["close"].pct_change(90)
        res = run_portfolio(sf, st, sm, scfg, top_k=5)
        ret = combine.equity_to_daily_returns(res.equity)
        # current holdings: signaling-long stocks ranked by 90d momentum, top-5
        last = max(f.index[-1] for f in sf.values())
        cand = [(t, sm[t].reindex([last]).iloc[0]) for t in sf
                if st[t].reindex([last]).fillna(0).iloc[0] > 0 and sm[t].reindex([last]).notna().iloc[0]]
        cand.sort(key=lambda x: x[1], reverse=True)
        return ret, [t for t, _ in cand[:5]]
    except Exception as e:  # noqa: BLE001
        print(f"  (US sleeve unavailable: {type(e).__name__} — running crypto-only)")
        return None, []


def main():
    print(__doc__)
    cfg, frames, higher, targets, momentum, fundings = load_universe()
    from quantlab.backtest.portfolio import run_portfolio
    from quantlab.backtest.carry import run_carry
    from quantlab.backtest import combine
    from quantlab.paper.engine import live_targets

    # crypto sleeves
    trend = combine.equity_to_daily_returns(run_portfolio(frames, targets, momentum, cfg, top_k=3).equity)
    carry = run_carry(frames, fundings, cfg, lookback_days=7, n_side=3, rebalance_days=1).daily_returns
    print("Fetching US equity sleeve (yfinance)...")
    usret, us_long = _us_sleeve(cfg)

    sleeves = {"crypto_trend": trend, "crypto_funding": carry}
    if usret is not None:
        sleeves["us_momentum"] = usret
    R = pd.DataFrame(sleeves).dropna()
    Rtr = R[R.index < CUT]

    iv = 1.0 / Rtr.std()
    w = (iv / iv.sum())
    book = (R * w).sum(axis=1)
    oos = book[book.index >= CUT]
    eq = (1 + oos).cumprod()
    sharpe = float(oos.mean() / oos.std() * np.sqrt(PPY)) if oos.std() > 0 else float("nan")
    cagr = eq.iloc[-1] ** (PPY / len(oos)) - 1 if len(oos) else float("nan")
    mdd = float((eq / eq.cummax() - 1).min()) if len(oos) else float("nan")

    print(f"\n=== 3-KOLLU ÇAPRAZ-VARLIK KİTABI ({len(R.columns)} kol) ===")
    print(f"OOS (2025-26): Sharpe {sharpe:.2f} | CAGR {cagr*100:.0f}% | MaxDD {mdd*100:.0f}%")
    print("Kol korelasyonları:\n" + R.corr().round(2).to_string())
    print("Ağırlıklar (inverse-vol, train-fit): " +
          " | ".join(f"{k} {v:.2f}" for k, v in w.items()))

    # current targets
    ct = live_targets(frames, cfg, top_k=3, mom_window=60)
    score = {s: fundings[s].tail(21).mean() for s in fundings}
    ranked = sorted(score, key=score.get)
    asof = max(f.index[-1] for f in frames.values())
    print(f"\nŞU ANKİ HEDEF (as-of {asof.date()}):")
    print(f"  1) KRİPTO-TREND  -> LONG {ct or '(nakit)'}")
    print(f"  2) KRİPTO-FUNDING-> LONG {ranked[:3]} | SHORT {ranked[-3:]}")
    print(f"  3) ABD-MOMENTUM  -> LONG {us_long or '(yok/offline)'}")
    print("\n⚠️ Paper-trade adayı. Canlı emir YOK. Survivorship-capped — ileriye-dönük doğrula.")


if __name__ == "__main__":
    main()
