"""LEVER #3 — XGBoost CROSS-SECTIONAL RANKING for the momentum sleeve (a NEW ML use).

Distinct from the meta-label that FAILED: that was a binary 'will this trade win' VETO
that culled the big winners the momentum book lives on (Sharpe 1.74→0.54). Here XGBoost
does NOT gate — it REPLACES the ranking key. The momentum sleeve picks Top-K by a strength
score; baseline uses 60-bar ROC. We train XGBoost to predict each coin's FORWARD 60-bar
return (cross-sectional), pooled across coins, and use that prediction as the ranking key.
Selection mechanism unchanged (still 'hold the Top-K strongest') — only the definition of
'strongest' changes from past-return to model-predicted-future-return.

No-lookahead: features at bar t use only data ≤ t (build_features is causality-tested);
the forward-return TARGET is used ONLY in training, and train is strictly < 2025. OOS
predictions use the frozen model on causal features. Same bar-timing as the ROC baseline,
so the comparison is fair.

Reports OOS Sharpe of ML-ranked vs ROC-ranked trend sleeve (standalone + combined with
funding), plus the OOS rank-IC of the predictions (the honest diagnostic: ~0 ⇒ no edge).

Usage: python scripts/run_mlrank.py
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
from quantlab.data import cache, funding as fundmod  # noqa: E402
from quantlab.backtest import combine, metrics  # noqa: E402
from quantlab.backtest.portfolio import run_portfolio  # noqa: E402
from quantlab.backtest.carry import run_carry  # noqa: E402
from quantlab import orchestrator  # noqa: E402
from quantlab.ml.features import build_features  # noqa: E402

CRYPTO = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LTC", "ATOM", "DOT",
          "LINK", "DOGE", "ETC", "FIL", "INJ", "NEAR", "UNI", "APT", "ARB", "OP"]
CUT = pd.Timestamp("2025-01-01")
MKTDATA = Path("../uyg/src/mktdata")
FUND = Path("../uyg/src/funddata")
HORIZON = 60  # 4h bars = 10 days (matches the ROC60 baseline horizon)


def _combo_oos(frames, targets, mom, fundings, cfg):
    trend = combine.equity_to_daily_returns(run_portfolio(frames, targets, mom, cfg, top_k=3).equity)
    carry = run_carry(frames, fundings, cfg, lookback_days=7, n_side=3, rebalance_days=1).daily_returns
    rt, rc = combine.align(trend, carry)
    wt, wc = combine.inverse_vol_weights(rt[rt.index < CUT], rc[rc.index < CUT])
    oos = combine.blend(rt[rt.index >= CUT], rc[rc.index >= CUT], wt, wc)
    m = metrics.compute_metrics(combine.equity_from_returns(oos, 10000.0), [], timeframe="1d")
    return m["sharpe"], m["cagr"], m["max_drawdown"]


def _sleeve_oos(frames, targets, mom, cfg):
    eq = run_portfolio(frames, targets, mom, cfg, top_k=3).equity
    r = combine.equity_to_daily_returns(eq)
    ro = r[r.index >= CUT]
    m = metrics.compute_metrics(combine.equity_from_returns(ro, 10000.0), [], timeframe="1d")
    return m["sharpe"], m["cagr"], m["max_drawdown"]


def main():
    cfg = load_config(str(Path(__file__).resolve().parents[1] / "config" / "default.yaml"))
    root = Path(__file__).resolve().parents[1]
    print("20 coin yükleniyor + feature/target paneli kuruluyor...")
    frames, targets, fundings, roc_mom = {}, {}, {}, {}
    feat_frames, y_frames = {}, {}
    for s in CRYPTO:
        csv = (root / MKTDATA / f"{s}_USDT_4h.csv").resolve()
        fp = (root / FUND / f"{s}_funding.csv").resolve()
        if not (csv.exists() and fp.exists()):
            continue
        df = cache.load_ohlcv(f"{s}/USDT", "4h", cache_dir=root / cfg.data.cache_dir,
                              start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
        hd = cache.load_ohlcv(f"{s}/USDT", "1d", cache_dir=root / cfg.data.cache_dir,
                              start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
        frames[s] = df
        targets[s] = orchestrator.build_target(df, cfg, hd)
        fundings[s] = fundmod.load_funding(fp)
        roc_mom[s] = df["close"].pct_change(HORIZON)
        feat_frames[s] = build_features(df, cfg, hd)
        y_frames[s] = df["close"].pct_change(HORIZON).shift(-HORIZON)  # forward return (train-only label)

    cols = sorted(set.intersection(*[set(f.columns) for f in feat_frames.values()]))
    # pooled training matrix
    Xtr_parts, ytr_parts = [], []
    for s in frames:
        X, y = feat_frames[s][cols], y_frames[s]
        idx = X.index[X.index < CUT]
        Xs, ys = X.loc[idx], y.loc[idx]
        ok = Xs.notna().all(axis=1) & ys.notna()
        Xtr_parts.append(Xs[ok])
        ytr_parts.append(ys[ok])
    Xtr = pd.concat(Xtr_parts)
    ytr = pd.concat(ytr_parts)
    print(f"Train paneli: {len(Xtr)} satır × {len(cols)} feature. XGBoost eğitiliyor...")

    import xgboost as xgb
    model = xgb.XGBRegressor(n_estimators=300, max_depth=4, learning_rate=0.03,
                             subsample=0.8, colsample_bytree=0.8, min_child_weight=20,
                             reg_lambda=2.0, n_jobs=-1)
    model.fit(Xtr.to_numpy(), ytr.to_numpy())

    # predict everywhere -> ML ranking signal
    ml_mom = {}
    ic_rows = []
    for s in frames:
        X = feat_frames[s][cols]
        pred = pd.Series(np.nan, index=X.index)
        ok = X.notna().all(axis=1)
        if ok.any():
            pred.loc[ok] = model.predict(X[ok].to_numpy())
        ml_mom[s] = pred
        # OOS rank-IC: predicted vs realized forward return
        oo = (X.index >= CUT)
        p = pred[oo]
        a = y_frames[s][oo]
        d = pd.concat([p, a], axis=1).dropna()
        if len(d) > 50:
            ic_rows.append(d.corr(method="spearman").iloc[0, 1])

    # baseline ROC vs ML ranking
    roc_s, roc_cg, roc_md = _sleeve_oos(frames, targets, roc_mom, cfg)
    ml_s, ml_cg, ml_md = _sleeve_oos(frames, targets, ml_mom, cfg)
    rocC = _combo_oos(frames, targets, roc_mom, fundings, cfg)
    mlC = _combo_oos(frames, targets, ml_mom, fundings, cfg)
    mean_ic = float(np.nanmean(ic_rows)) if ic_rows else float("nan")

    # feature importance (top 8)
    imp = sorted(zip(cols, model.feature_importances_), key=lambda x: -x[1])[:8]

    lines = ["# LEVER #3 — XGBoost cross-sectional RANKING vs ROC (momentum sleeve)", "",
             f"Train paneli {len(Xtr)} satır (<2025), {len(cols)} causal feature, horizon "
             f"{HORIZON}×4h=10g. OOS 2025-26, tüm maliyetler. Seçim mekanizması AYNI (Top-3 "
             "en güçlü); değişen tek şey 'güç' = ROC mu, XGBoost-tahmini-forward-return mı.", "",
             "## OOS sonuç (trend sleeve TEK BAŞINA)", "",
             "| sıralama | OOS Sharpe | CAGR | MaxDD |", "|---|---|---|---|",
             f"| ROC60 (baseline) | {roc_s:.2f} | {roc_cg*100:.0f}% | {roc_md*100:.0f}% |",
             f"| XGBoost-rank | {ml_s:.2f} | {ml_cg*100:.0f}% | {ml_md*100:.0f}% |", "",
             "## OOS sonuç (trend+funding COMBO — asıl kitap)", "",
             "| sıralama | combo OOS Sharpe | CAGR | MaxDD |", "|---|---|---|---|",
             f"| ROC60 (baseline) | {rocC[0]:.2f} | {rocC[1]*100:.0f}% | {rocC[2]*100:.0f}% |",
             f"| XGBoost-rank | {mlC[0]:.2f} | {mlC[1]*100:.0f}% | {mlC[2]*100:.0f}% |", "",
             f"## Teşhis: OOS rank-IC (tahmin vs gerçekleşen forward-return) = **{mean_ic:+.3f}**", "",
             "Top-8 feature önemi: " + ", ".join(f"{c}({v:.2f})" for c, v in imp), "",
             "## Yorum (dürüst)", ""]
    lift = mlC[0] - rocC[0]
    if lift > 0.1 and mean_ic > 0.03:
        lines.append(f"**XGBoost sıralama ROC'u GEÇTİ (combo {rocC[0]:.2f}→{mlC[0]:.2f}, "
                     f"IC {mean_ic:+.3f}).** Sıralama-olarak ML, gate-olarak ML'in aksine işe yaradı "
                     "— bu YENİ ve değerli bir kaldıraç. (Yine de survivorship + kısa OOS → haircut.)")
    else:
        lines.append(f"**XGBoost sıralama ROC'u GEÇMEDİ (combo {rocC[0]:.2f} vs {mlC[0]:.2f}, lift "
                     f"{lift:+.2f}, OOS IC {mean_ic:+.3f}).** IC ~0 ⇒ model forward-return'ü çapraz-"
                     "kesitte güvenilir sıralayamıyor; ROC kadar basit bir sinyal en az onun kadar iyi. "
                     "Bu, ML4T bulgusunu (IC ~0.02) sıralama görevinde de doğrular. **Baseline ROC kalır.**")
    report = "\n".join(lines)
    print("\n" + report)
    (root / "reports_out" / "mlrank.md").write_text(report)
    print(f"\nSaved -> {root / 'reports_out' / 'mlrank.md'}")


if __name__ == "__main__":
    main()
