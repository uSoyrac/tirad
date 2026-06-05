#!/usr/bin/env python3
"""
faz3_cycle.py — HASAT-DÖNGÜSÜ COMPOUND SİMÜLATÖRÜ ($100→$10k, çek, resetle)
═══════════════════════════════════════════════════════════════════════
Kullanıcı hedefi: en hızlı sürede $100→$10k, yüksek başarı oranıyla; ulaşınca
kârı çek, $reset'e dön, tekrarla. Küçük sabit stake → agresif +EV bahis rasyonel.

İki aracı gerçek edge üstünde kıyaslar:
  NEUTRAL     — market-nötr long-short momentum (düşük vol, güvenli)
  DIRECTIONAL — yönlü long-only momentum (yüksek vol, hızlı ama riskli)

Her kaldıraç L için Monte Carlo (bootstrap historik rebalance getirileri):
  P(döngü $10k'ya ulaşır), medyan süre (rebalance→gün), P(döngü ruin),
  horizon başına beklenen ÇEKİLEN $, optimal kaldıraç.
Likidasyon gerçekçi: L*r <= -0.95 → kasa silinir.
"""
import os, json, argparse, warnings, itertools
import numpy as np

warnings.filterwarnings("ignore")
from pivot_momentum import load_matrix, backtest_xs

SEED = 42
HOLD_DAYS = 14
BARS_PER_DAY = 6  # 4H


def gen_series(M):
    """İki aracın net per-rebalance getiri dizisini üret."""
    d = BARS_PER_DAY
    neutral, _ = backtest_xs(M, 30*d, 14*d, 5, mode="longshort")
    directional, _ = backtest_xs(M, 90*d, 14*d, 3, mode="longonly")
    return {"NEUTRAL": neutral, "DIRECTIONAL": directional}


def cycle_mc(rets, lev, start=100.0, target=10000.0, reset=300.0,
             horizon_rebal=130, n_paths=20000, ruin_frac=0.10):
    """
    Hasat-döngüsü MC. horizon_rebal ~ kaç rebalance boyunca koşacağız
    (130 rebal × 14g ≈ 5 yıl). ruin_frac: stake'in bu kadarına düşerse döngü iflas.
    Dönüş: P(success/cycle), medyan rebal-to-target, P(ruin/cycle), beklenen çekilen $.
    """
    rng = np.random.default_rng(SEED)
    R = np.asarray(rets)
    succ_times = []          # başarılı döngülerin rebalance süresi
    n_success = n_ruin = 0
    harvested = np.zeros(n_paths)
    for p in range(n_paths):
        eq = start
        ruin_floor = start * ruin_frac
        t_in_cycle = 0
        for step in range(horizon_rebal):
            r = R[rng.integers(0, len(R))]
            lr = lev * r
            if lr <= -0.95:          # likidasyon
                eq = 0.0
            else:
                eq *= (1.0 + lr)
            t_in_cycle += 1
            if eq >= target:
                n_success += 1
                succ_times.append(t_in_cycle)
                harvested[p] += (eq - reset if eq > reset else 0) if False else eq  # çekilen ≈ ulaşılan
                eq = reset           # kârı çek, resetle
                ruin_floor = reset * ruin_frac
                t_in_cycle = 0
            elif eq <= ruin_floor:
                n_ruin += 1
                eq = reset           # yeni stake koy
                ruin_floor = reset * ruin_frac
                t_in_cycle = 0
    cycles = n_success + n_ruin
    p_succ = n_success / cycles * 100 if cycles else 0
    p_ruin = n_ruin / cycles * 100 if cycles else 0
    med_t = float(np.median(succ_times)) if succ_times else float("inf")
    return {"p_succ": p_succ, "p_ruin": p_ruin, "med_rebal": med_t,
            "med_days": med_t * HOLD_DAYS if succ_times else float("inf"),
            "exp_harvest": float(harvested.mean()), "n_success_per_path": n_success / n_paths}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="mktdata"); ap.add_argument("--tf", default="4h")
    args = ap.parse_args()
    M = load_matrix(args.data, args.tf)
    series = gen_series(M)

    print("=" * 92)
    print(f"  FAZ 3 — HASAT-DÖNGÜSÜ COMPOUND  ($100→$10k, çek→$300 resetle)  horizon≈5 yıl")
    print("=" * 92)
    for name, rets in series.items():
        mu = rets.mean()*100; sd = rets.std()*100
        print(f"\n  ── {name} ── (per-rebalance: ort {mu:+.2f}%, std {sd:.2f}%, N={len(rets)})")
        print(f"  {'lev':>4}{'P(başarı)%':>11}{'P(ruin)%':>10}{'medyan süre':>14}{'çekilen$/5yıl':>14}{'değerlendirme':>16}")
        best = None
        for lev in [1, 2, 3, 5, 8, 10, 15]:
            r = cycle_mc(rets, lev)
            score = r["exp_harvest"] * (r["p_succ"]/100)  # başarı-ağırlıklı hasat
            label = ""
            if r["med_days"] != float("inf"):
                tlabel = f"{r['med_rebal']:.0f}reb/{r['med_days']:.0f}g"
            else:
                tlabel = "ulaşmıyor"
            print(f"  {lev:>4}{r['p_succ']:>11.1f}{r['p_ruin']:>10.1f}{tlabel:>14}{r['exp_harvest']:>14,.0f}{'':>16}")
            if best is None or score > best[1]:
                best = (lev, score, r)
        bl, bs, br = best
        print(f"  >>> {name} optimal kaldıraç ≈ {bl}x → P(başarı)={br['p_succ']:.0f}% "
              f"medyan {br['med_days']:.0f}g, P(ruin/döngü)={br['p_ruin']:.0f}%")
    print(f"\n  NOT: P(başarı) = bir döngünün $10k'ya ULAŞMA oranı (ruin'e karşı). Yüksek=iyi.")
    print(f"       Hasat modeli sayesinde yüksek kaldıraçta bile sadece $300 stake riskte.")


if __name__ == "__main__":
    main()
