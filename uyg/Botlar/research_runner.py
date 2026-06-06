#!/usr/bin/env python3
"""ZAMANLANMIŞ RE-RESEARCH — RAPOR-ONLY, İNSAN-KAPILI (haftalık cron).

Claude kapalıyken bile sunucu kendini DEĞERLENDİRİR (deploy ETMEZ):
  1) Walk-forward param-drift: son 12 ayda en iyi (ROC×topK)+(carry lb×n) hâlâ deploy
     edilen default (60,3)+(7,3) mı? Kaydıysa "gözden geçir" işareti.
  2) DSR + PBO (overfit honesty gate): edge hâlâ istatistiksel olarak gerçek mi?
  3) Paper-vs-backtest sapma: canlı forward Sharpe, referans OOS'tan çok mu düştü? (edge çöküşü)
Sonucu paper/research.json'a yazar; /arastirma sekmesi gösterir. DEPLOY KARARI İNSANIN.

Çalıştırma (cron): cd /root/tirad/uyg/Botlar && TIRAD_LIVE=1 \
    /root/tirad/.venv/bin/python /root/tirad/research_runner.py
"""
import json
import sys
import time
import warnings
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, "/root/tirad/uyg/Botlar")

from _botlib import load_universe  # noqa: E402
from quantlab.backtest import combine  # noqa: E402
from quantlab.backtest.portfolio import run_portfolio  # noqa: E402
from quantlab.backtest.carry import run_carry  # noqa: E402

OUT = Path("/root/tirad/paper")
TREND_GRID = [(mw, k) for mw in (30, 60, 120) for k in (1, 3, 5)]
CARRY_GRID = [(lb, n) for lb in (3, 7, 14) for n in (3, 5)]
DEPLOYED = ((60, 3), (7, 3))
EMC = 0.5772156649
ANN = np.sqrt(365)


def deflated_sharpe(returns, sr_trials):
    from scipy.stats import kurtosis, norm, skew
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
    return float(norm.cdf(num / den)), float(sr), float(sr0)


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
    return float((np.array(logits) < 0).mean())


def _sharpe(r):
    return float(r.mean() / r.std() * ANN) if r.std() > 0 else -9.0


def main():
    print(f"[{time.strftime('%Y-%m-%d %H:%M')}] Re-research başlıyor (RAPOR-ONLY)…", flush=True)
    cfg, frames, higher, targets, momentum, fundings = load_universe()

    trend = {tk: combine.equity_to_daily_returns(
        run_portfolio(frames, targets, {s: frames[s]["close"].pct_change(tk[0]) for s in frames},
                      cfg, top_k=tk[1]).equity) for tk in TREND_GRID}
    carry = {ck: run_carry(frames, fundings, cfg, lookback_days=ck[0], n_side=ck[1],
                           rebalance_days=1).daily_returns for ck in CARRY_GRID}

    # combo family for DSR/PBO
    cols = []
    for tk, tr in trend.items():
        for ck, cr in carry.items():
            a, b = combine.align(tr, cr)
            wt, wc = combine.inverse_vol_weights(a, b)
            cols.append(combine.blend(a, b, wt, wc).rename(f"{tk}|{ck}"))
    M_df = pd.concat(cols, axis=1).dropna()
    M = M_df.to_numpy()
    sr_trials = M.mean(0) / M.std(0, ddof=1)
    deployed_ret = M_df[f"{DEPLOYED[0]}|{DEPLOYED[1]}"].to_numpy()
    dsr, sr_d, sr0 = deflated_sharpe(deployed_ret, sr_trials)
    pbo = pbo_cscv(M, S=16)

    # walk-forward param-drift: best on last 12 months
    idx = M_df.index
    trw = idx[idx >= idx[-1] - pd.DateOffset(months=12)]
    best, bs = None, -9
    for tk, trr in trend.items():
        for ck, crr in carry.items():
            a, b = combine.align(trr.reindex(trw).dropna(), crr.reindex(trw).dropna())
            if len(a) < 30:
                continue
            wa, wb = combine.inverse_vol_weights(a, b)
            s = _sharpe(combine.blend(a, b, wa, wb))
            if s > bs:
                bs, best = s, (tk, ck)
    drift = best != DEPLOYED

    # paper-vs-backtest drift
    paper = []
    for key in ("xasset_vt", "xasset", "combo", "funding", "xsec_momentum"):
        try:
            d = json.load(open(OUT / f"{key}.json"))
            st, ref = d.get("stats", {}), d.get("ref", {})
            fwd, refs = st.get("sharpe"), ref.get("oos_sharpe")
            decay = (fwd is not None and refs is not None and st.get("days", 0) >= 10
                     and fwd < refs - 1.0)
            paper.append({"key": key, "fwd_sharpe": fwd, "navnow": st.get("navnow"),
                          "days": st.get("days"), "ref_sharpe": refs, "decay_flag": bool(decay)})
        except Exception:  # noqa: BLE001
            pass

    edge_real = dsr > 0.95 and pbo < 0.5
    review = drift or (not edge_real) or any(p["decay_flag"] for p in paper)
    if not review:
        verdict = "STABIL — parametre kaymadı, edge DSR/PBO'yu geçiyor, paper backtest'le uyumlu. Aksiyon yok."
    else:
        bits = []
        if drift:
            bits.append(f"param-drift (WF en iyi {best} ≠ deploy {DEPLOYED})")
        if not edge_real:
            bits.append(f"edge zayıfladı (DSR {dsr:.2f}/PBO {pbo:.2f})")
        if any(p["decay_flag"] for p in paper):
            bits.append("paper-NAV backtest'ten saptı")
        verdict = "GÖZDEN GEÇİR → " + "; ".join(bits) + ". (İnsan onayı gerekir; OTOMATIK DEPLOY YOK.)"

    rep = {"ts": time.strftime("%Y-%m-%d %H:%M"), "universe": len(frames),
           "dsr": round(dsr, 3), "pbo": round(pbo, 3),
           "obs_sharpe_ann": round(sr_d * float(ANN), 2), "null_sharpe_ann": round(sr0 * float(ANN), 2),
           "deployed": str(DEPLOYED), "wf_best": str(best), "param_drift": bool(drift),
           "edge_real": bool(edge_real), "needs_review": bool(review),
           "paper": paper, "verdict": verdict}
    OUT.mkdir(exist_ok=True)
    (OUT / "research.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2))
    print(f"  DSR {dsr:.3f} | PBO {pbo:.3f} | param_drift {drift} | review {review}", flush=True)
    print(f"  -> {verdict}", flush=True)
    print("  ✓ paper/research.json yazıldı.", flush=True)


if __name__ == "__main__":
    main()
