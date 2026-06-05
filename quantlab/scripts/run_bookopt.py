"""OPTIMIZE THE PRODUCTION BOOK for most profit — HONESTLY (walk-forward, overfit-protected).

Not leverage (Sharpe-invariant) and not more ML (failed 4×). The honest profit maximiser is
walk-forward parameter selection: in each rolling window pick the best trend (ROC×top_k) and
carry (lookback×n_side) params + 3-way inverse-vol weights (trend/carry/US) on TRAIN, apply to
the untouched TEST window. Concatenated test windows = fully OOS, overfit-protected. Run on the
broad 27-coin full-history universe + the US-momentum sleeve. Then size with vol-targeting.

CRITICAL honesty: if WF-opt OOS Sharpe comes out ABOVE the already-suspicious fixed 3.06, that
is MORE likely regime-luck/overfit than real — flagged loudly. The point of WF is robustness
(does adapting params per regime beat a fixed default OOS?), not chasing a bigger number.

Usage: python scripts/run_bookopt.py
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
FULL_HIST_CUT = pd.Timestamp("2023-09-01")
TREND_GRID = [(mw, k) for mw in (30, 60, 120) for k in (1, 3, 5)]
CARRY_GRID = [(lb, n) for lb in (3, 7, 14) for n in (3, 5)]


def _sharpe(r):
    return float(r.mean() / r.std() * np.sqrt(PPY)) if r.std() > 0 else -9.0


def _ann(r):
    eq = (1 + r).cumprod()
    sh = _sharpe(r)
    cg = eq.iloc[-1] ** (PPY / len(r)) - 1 if len(r) else float("nan")
    md = float((eq / eq.cummax() - 1).min()) if len(r) else float("nan")
    return sh, cg, md, (eq.iloc[-1] if len(r) else float("nan"))


def _blend3(streams, weights, idx):
    """weights dict name->w; streams dict name->Series; align on idx."""
    parts = []
    for name, w in weights.items():
        parts.append(streams[name].reindex(idx).fillna(0.0) * w)
    return sum(parts)


def _inv_vol3(streams, names, idx):
    stds = {}
    for n in names:
        s = streams[n].reindex(idx).dropna()
        stds[n] = s.std() if s.std() > 0 else np.nan
    inv = {n: (1.0 / stds[n] if stds[n] == stds[n] and stds[n] > 0 else 0.0) for n in names}
    tot = sum(inv.values()) or 1.0
    return {n: inv[n] / tot for n in names}


def main():
    cfg = load_config(str(Path(__file__).resolve().parents[1] / "config" / "default.yaml"))
    root = Path(__file__).resolve().parents[1]
    print("27-coin tam-tarihli evren yükleniyor...")
    frames, targets, fund = {}, {}, {}
    for pq in sorted(EXP.glob("*_4h.parquet")):
        base = pq.name.replace("_4h.parquet", "")
        fp = EXP / f"{base}_funding.parquet"
        if not fp.exists():
            continue
        df = cache._validate(pd.read_parquet(pq))
        if df.index[0] > FULL_HIST_CUT:
            continue
        frames[base] = df
        targets[base] = orchestrator.build_target(df, cfg, cache.resample(df, "1d"))
        fund[base] = pd.read_parquet(fp)["funding"]
    print(f"{len(frames)} coin. {len(TREND_GRID)} trend + {len(CARRY_GRID)} carry akışı önceden hesaplanıyor...")

    trend_streams = {}
    for mw, k in TREND_GRID:
        mom = {s: frames[s]["close"].pct_change(mw) for s in frames}
        trend_streams[(mw, k)] = combine.equity_to_daily_returns(
            run_portfolio(frames, targets, mom, cfg, top_k=k).equity)
    carry_streams = {}
    for lb, n in CARRY_GRID:
        carry_streams[(lb, n)] = run_carry(frames, fund, cfg, lookback_days=lb, n_side=n,
                                           rebalance_days=1).daily_returns
    us = pd.read_parquet(SLEEVE3)["us_momentum"]

    # common daily index across everything
    idx = us.index
    for r in list(trend_streams.values()) + list(carry_streams.values()):
        idx = idx.intersection(r.index)
    idx = idx.sort_values()

    # walk-forward 12m train / 6m test / step 6m
    wf = pd.Series(dtype=float)
    picks = []
    start = idx[0]
    while True:
        tr_end = start + pd.DateOffset(months=12)
        te_end = tr_end + pd.DateOffset(months=6)
        tr = idx[(idx >= start) & (idx < tr_end)]
        te = idx[(idx >= tr_end) & (idx < te_end)]
        if len(te) < 20:
            break
        best, best_s = None, -1e9
        for tk, trr in trend_streams.items():
            for ck, crr in carry_streams.items():
                streams = {"trend": trr, "carry": crr, "us": us}
                w = _inv_vol3(streams, ["trend", "carry", "us"], tr)
                s = _sharpe(_blend3(streams, w, tr).dropna())
                if s > best_s:
                    best_s, best = s, (tk, ck, w)
        if best is None:
            start = start + pd.DateOffset(months=6)
            continue
        tk, ck, w = best
        streams = {"trend": trend_streams[tk], "carry": carry_streams[ck], "us": us}
        wf = pd.concat([wf, _blend3(streams, w, te).dropna()])
        picks.append((str(te[0].date()), tk, ck, {k2: round(v, 2) for k2, v in w.items()}))
        start = start + pd.DateOffset(months=6)
    wf = wf[~wf.index.duplicated()].sort_index()
    wf_oos = wf[wf.index >= CUT]

    # fixed-default book baseline (ROC60/top3 + carry7/3 + US, inverse-vol fit on train)
    streams = {"trend": trend_streams[(60, 3)], "carry": carry_streams[(7, 3)], "us": us}
    wfit = _inv_vol3(streams, ["trend", "carry", "us"], idx[idx < CUT])
    base = _blend3(streams, wfit, idx)
    base_oos = base[base.index >= CUT]

    sh_b, cg_b, md_b, _ = _ann(base_oos)
    sh_w, cg_w, md_w, _ = _ann(wf_oos)

    lines = ["# ÜRETİM KİTABI — walk-forward optimizasyon (en kârlı, dürüst)", "",
             f"{len(frames)} coin + US sleeve. 12a train / 6a test / 6a adım; her pencerede trend "
             f"(ROC×topK ∈ {len(TREND_GRID)}) + carry (lb×n ∈ {len(CARRY_GRID)}) + 3-yönlü inverse-vol "
             "ağırlık TRAIN'de seçilip TEST'e uygulanır. Tamamen OOS.", "",
             "## OOS (2025-26) — WF-optimize vs sabit-default kitap", "",
             "| Metrik | Sabit default | WF-optimize |", "|---|---|---|",
             f"| Sharpe | {sh_b:.2f} | {sh_w:.2f} |",
             f"| CAGR | {cg_b*100:.0f}% | {cg_w*100:.0f}% |",
             f"| MaxDD | {md_b*100:.0f}% | {md_w*100:.0f}% |", "",
             "## WF-optimize kitabın vol-hedefli boyutlandırması (OOS — 'en çok para' kadranı)", "",
             "| hedef vol | Sharpe | CAGR | MaxDD | terminal | ort.kaldıraç |", "|---|---|---|---|---|---|"]
    for tgt in (0.10, 0.15, 0.20, 0.25):
        realized = wf.rolling(20).std().shift(1) * np.sqrt(PPY)
        lev = (tgt / realized).clip(upper=MAX_LEV).fillna(0.0)
        rt = (wf * lev)[wf.index >= CUT]
        s, c, m, t = _ann(rt)
        lines.append(f"| {tgt*100:.0f}% | {s:.2f} | {c*100:.0f}% | {m*100:.0f}% | {t:.2f} | "
                     f"{lev[lev.index >= CUT].mean():.2f}x |")

    lines += ["", "## Pencere-bazında seçilen parametreler (train-seçimi)", "",
              "| Test başı | trend(ROC,topK) | carry(lb,n) | ağırlıklar |", "|---|---|---|---|"]
    for d, tk, ck, w in picks:
        lines.append(f"| {d} | {tk} | {ck} | {w} |")

    lift = sh_w - sh_b
    lines += ["", "## Yorum (dürüst)", ""]
    if lift > 0.1:
        lines.append(f"**WF-opt OOS Sharpe'ı YÜKSELTTİ ({sh_b:.2f}→{sh_w:.2f}, {lift:+.2f}).** Rejime "
                     "göre parametre uyarlaması sabit-default'u geçti ve dürüst (train-seçimi, "
                     "OOS-uygulama). ⚠️ AMA sabit kitap zaten 3.06 (>2.5 kaçak-çizgisi) idi; daha "
                     "yüksek bir OOS Sharpe büyük olasılıkla 2025-26 rejim-şansı/overfit — gerçek "
                     "değil. Beklentiyi WF-opt'un FULL-span'ine + ağır survivorship haircut'a göre kur, "
                     "OOS pik sayısına değil. Paramların pencere-pencere TUTARLILIĞI (tablo) gerçek "
                     "robustluğun işareti; zıplıyorsa param-chasing.")
    elif lift > -0.1:
        lines.append(f"**WF-opt ~nötr ({sh_b:.2f}→{sh_w:.2f}, {lift:+.2f}).** Sabit-default zaten "
                     "near-optimal — param-chasing robust OOS değer katmıyor (İYİ: default kiraz-"
                     "toplama değil). En kârlı dürüst konfig = sabit kitap + vol-hedef.")
    else:
        lines.append(f"**WF-opt HURTS ({sh_b:.2f}→{sh_w:.2f}, {lift:+.2f}).** Train-best paramlar "
                     "OOS'ta tutmuyor (rejim istikrarsızlığı). Sabit robust default'ta kal.")
    lines.append("- **'En çok para' = en yüksek dürüst risk-ayarlı kitabı seç, sonra vol-hedef "
                 "(%15-20) ile boyutla.** Kaldıraç Sharpe'ı artırmaz; sadece DD'ye göre getiriyi "
                 "ölçekler. ≤¼-Kelly tavanı. Sonraki: bu kitaba DSR/PBO + paper-trade. Canlı öncesi SOR.")
    report = "\n".join(lines)
    print("\n" + report)
    (root / "reports_out" / "bookopt.md").write_text(report)
    print(f"\nSaved -> {root / 'reports_out' / 'bookopt.md'}")


if __name__ == "__main__":
    main()
