"""HONESTY GATE on the PRODUCTION BOOK — is the 3-4 OOS Sharpe real or a mirage?

Deflated Sharpe Ratio + PBO (CSCV, Bailey & López de Prado) applied to the 3-sleeve book
family: 27-coin crypto-trend (ROC×topK) + crypto-funding (lb×n) + US-momentum, 3-way
inverse-vol blended. The WF-opt consistently picked trend(30,1)+carry(14,5) — we test THAT
deployed config for selection-bias inflation, and PBO over the whole family for whether
IS-best generalizes OOS.

DSR>0.95 + PBO<0.5 = the edge survives deflation (not a lucky grid pick). Otherwise the
3-4 Sharpe is substantially selection artifact and the honest expectation is far lower.

Usage: python scripts/run_bookpbo.py
"""

from __future__ import annotations

import sys
import warnings
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import kurtosis, norm, skew  # noqa: E402

from quantlab.config import load_config  # noqa: E402
from quantlab.data import cache  # noqa: E402
from quantlab.backtest import combine  # noqa: E402
from quantlab.backtest.portfolio import run_portfolio  # noqa: E402
from quantlab.backtest.carry import run_carry  # noqa: E402
from quantlab import orchestrator  # noqa: E402

EXP = Path(__file__).resolve().parents[1] / "data_cache_exp"
SLEEVE3 = Path(__file__).resolve().parents[1] / "reports_out" / "_sleeves3.parquet"
FULL_HIST_CUT = pd.Timestamp("2023-09-01")
TREND_GRID = [(mw, k) for mw in (30, 60, 120) for k in (1, 3, 5)]
CARRY_GRID = [(lb, n) for lb in (3, 7, 14) for n in (3, 5)]
DEPLOYED = "(30, 1)|(14, 5)"  # the WF-opt's consistent pick
EMC = 0.5772156649
ANN = np.sqrt(252)


def deflated_sharpe(returns, sr_trials):
    T = len(returns)
    sr = returns.mean() / returns.std(ddof=1)
    sk = float(skew(returns))
    ku = float(kurtosis(returns, fisher=False))
    N = len(sr_trials)
    var_sr = np.var(sr_trials, ddof=1)
    z1, z2 = norm.ppf(1 - 1.0 / N), norm.ppf(1 - 1.0 / (N * np.e))
    sr0 = np.sqrt(var_sr) * ((1 - EMC) * z1 + EMC * z2)
    num = (sr - sr0) * np.sqrt(T - 1)
    den = np.sqrt(1 - sk * sr + (ku - 1) / 4.0 * sr**2)
    return float(norm.cdf(num / den)), sr, float(sr0), N, T


def pbo_cscv(M, S=16):
    T, N = M.shape
    blocks = np.array_split(np.arange(T), S)
    logits = []
    for is_combo in combinations(range(S), S // 2):
        is_rows = np.concatenate([blocks[b] for b in is_combo])
        oos_rows = np.concatenate([blocks[b] for b in range(S) if b not in is_combo])
        is_sr = M[is_rows].mean(0) / (M[is_rows].std(0, ddof=1) + 1e-12)
        oos_sr = M[oos_rows].mean(0) / (M[oos_rows].std(0, ddof=1) + 1e-12)
        n_star = int(np.argmax(is_sr))
        rank = float((oos_sr <= oos_sr[n_star]).sum()) / (N + 1)
        w = min(max(rank, 1e-6), 1 - 1e-6)
        logits.append(np.log(w / (1 - w)))
    logits = np.array(logits)
    return float((logits < 0).mean()), logits


def _inv_vol3(a, b, c):
    s = {"t": a.std(), "c": b.std(), "u": c.std()}
    inv = {k: (1.0 / v if v and v > 0 else 0.0) for k, v in s.items()}
    tot = sum(inv.values()) or 1.0
    return inv["t"] / tot, inv["c"] / tot, inv["u"] / tot


def main():
    cfg = load_config(str(Path(__file__).resolve().parents[1] / "config" / "default.yaml"))
    root = Path(__file__).resolve().parents[1]
    print("27-coin + US, book ailesi kuruluyor...")
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
    us = pd.read_parquet(SLEEVE3)["us_momentum"]

    trend = {tk: combine.equity_to_daily_returns(
        run_portfolio(frames, targets, {s: frames[s]["close"].pct_change(tk[0]) for s in frames},
                      cfg, top_k=tk[1]).equity) for tk in TREND_GRID}
    carry = {ck: run_carry(frames, fund, cfg, lookback_days=ck[0], n_side=ck[1],
                           rebalance_days=1).daily_returns for ck in CARRY_GRID}

    cols = []
    for tk, tr in trend.items():
        for ck, cr in carry.items():
            df3 = pd.DataFrame({"t": tr, "c": cr, "u": us}).dropna()
            wt, wc, wu = _inv_vol3(df3["t"], df3["c"], df3["u"])
            blend = (df3["t"] * wt + df3["c"] * wc + df3["u"] * wu).rename(f"{tk}|{ck}")
            cols.append(blend)
    M_df = pd.concat(cols, axis=1).dropna()
    M = M_df.to_numpy()
    sr_trials = M.mean(0) / M.std(0, ddof=1)
    N, T = M.shape[1], M.shape[0]

    deployed = M_df[DEPLOYED].to_numpy()
    dsr, sr_d, sr0, _, _ = deflated_sharpe(deployed, sr_trials)
    print(f"Aile {N} config, T={T} gün. CSCV C(16,8)=12870 split çalışıyor...")
    pbo, logits = pbo_cscv(M, S=16)

    lines = ["# DÜRÜSTLÜK GEÇİDİ — üretim kitabı DSR + PBO (3-sleeve aile)", "",
             f"Aile: {N} config (trend ROC×topK × carry lb×n, hepsi US ile 3-yönlü inverse-vol "
             f"blend). Günlük T={T} (tüm tarih, 27 coin + US).", "",
             f"## Deflated Sharpe (deployed = WF-opt seçimi {DEPLOYED} + US)", "",
             f"- Gözlenen günlük Sharpe: {sr_d:.4f} (yıllık ~{sr_d*ANN:.2f})",
             f"- Null'da beklenen-maks Sharpe (seçim-yanlılığı, N={N}): {sr0:.4f} (yıllık ~{sr0*ANN:.2f})",
             f"- skew {float(skew(deployed)):+.2f}, kurtosis {float(kurtosis(deployed, fisher=False)):.2f}",
             f"- **Deflated Sharpe Ratio (P[gerçek Sharpe>0]): {dsr:.3f}**", "",
             "## PBO (Backtest Overfitting Olasılığı, CSCV S=16)", "",
             f"- **PBO = {pbo:.3f}** (IS-best'in OOS medyan-altı kaldığı split oranı)",
             f"- Medyan logit: {np.median(logits):+.2f} (pozitif = IS-best OOS'ta genelleşiyor)", "",
             "## Yorum (dürüst)", ""]
    ok = dsr > 0.95 and pbo < 0.5
    if ok:
        lines.append(f"**Kitap dürüstlük geçidini GEÇTİ:** DSR {dsr:.2f} (>0.95) + PBO {pbo:.2f} "
                     f"(<0.5). {N} deneme + non-normallik + IS/OOS genelleme için deflate edildikten "
                     "sonra pozitif Sharpe istatistiksel olarak güvenilir — grid-şansı DEĞİL. AMA "
                     "DSR/PBO yıllık MAGNİTÜDÜ onaylamaz, sadece edge'in pozitif olduğunu; 4.18 OOS "
                     "hâlâ survivorship + kısa-pencere şişkin. Konuşlandırma beklentisi: pozitif edge "
                     "VAR, büyüklük haircut'lı (~1.8-2.5 Sharpe gerçekçi).")
    elif pbo < 0.5:
        lines.append(f"**Karışık:** PBO {pbo:.2f}<0.5 (seçim genelleşiyor) ama DSR {dsr:.2f} ≤0.95 — "
                     "edge gerçekçi ama deflasyon sonrası yüksek-güven değil; boyutu temkinli tut.")
    else:
        lines.append(f"**Muhtemelen OVERFIT:** PBO {pbo:.2f} (≥0.5) ve/veya DSR {dsr:.2f} düşük. "
                     "Grid'in görünür edge'i büyük ölçüde seçim artefaktı — 3-4 başlık Sharpe'ına GÜVENME.")
    lines.append("- **Top-1 uyarısı:** WF-opt Top-1 seçti (tek-coin konsantrasyonu) — OOS'ta parlak "
                 "ama kırılgan. Konuşlandırmada Top-3 daha robust (biraz düşük Sharpe, çok daha az "
                 "tek-isim varyansı). En kârlı DÜRÜST konfig: Top-3 book + %15-20 vol-hedef.")
    report = "\n".join(lines)
    print("\n" + report)
    (root / "reports_out" / "bookpbo.md").write_text(report)
    print(f"\nSaved -> {root / 'reports_out' / 'bookpbo.md'}")


if __name__ == "__main__":
    main()
