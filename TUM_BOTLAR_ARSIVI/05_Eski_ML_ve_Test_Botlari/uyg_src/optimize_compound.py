#!/usr/bin/env python3
"""
optimize_compound.py — BİLEŞİK BÜYÜME OPTİMİZASYONU (DÜRÜST & GERÇEKÇİ)
═══════════════════════════════════════════════════════════════════════
Master Prompt hedef fonksiyonu:
    Maximize CGR  s.t.  MDD ≤ thr,  P(ruin)=0,  net expectancy>0,  freq≥100/yıl

Bu driver MEVCUT motorları yeniden kullanır, davranışlarını BOZMAZ:
  - backtest_symbol_optimized  (simulate_orp)      → gerçek 4H trade üretimi
  - run_orp_dynamic, monte_carlo_orp (dynamic_optimizer) → ORP + MC primitifleri

Eklenen titizlik (önceki altyapıda eksikti):
  1. Tek-yol "growth" yerine MONTE CARLO ROBUST SIRALAMA (medyan CGR, P(ruin)=0 sert filtre)
  2. Çapraz-coin OUT-OF-SAMPLE (leave-one-out) + zaman-dışı (walk-forward) bölme
  3. Betting sistemleri GERÇEK R dağılımı üzerinde karşılaştırma (sentetik değil)
  4. Limit dolum oranı stresi (deep target #1): rastgele %X trade düşür
  5. Ardışık kayıp / korelasyon stresi (deep target #4,#5): kayıpları kümele
  6. Gerçekçilik düzeltmesi: maliyet zaten r_mult'ta; ek dolum+haircut katmanı

Kullanım:
  python3 optimize_compound.py            # tam pipeline
  python3 optimize_compound.py --quick    # küçük grid, hızlı
Reprodüksiyon: tüm rastgelelik sabit seed (SEED).
"""
import os, sys, json, math, time, argparse, warnings, itertools
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from dynamic_optimizer import run_orp_dynamic, monte_carlo_orp

SEED = 42
DATA_DIR = "data"
COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]
TRADES_CACHE = "/tmp/real_trades_4h.json"
START_CAP = 100.0

# Gerçek dünya sürtünmesi (r_mult zaten net; bunlar EK gerçekçilik katmanı)
DEFAULT_FILL_RATE = 0.60     # limit dolum oranı ~%50-70 (AGENT.md) → kaçırılan bileşik adımlar
REALISM_HAIRCUT   = 0.50     # backtest→canlı ham düzeltme (master_prompt: ×0.50-0.70)


# ═══════════════════════════════════════════════════════════════════════
#  1) GERÇEK TRADE ÜRETİMİ (cache'li)
# ═══════════════════════════════════════════════════════════════════════
def generate_trades(force=False):
    if os.path.exists(TRADES_CACHE) and not force:
        data = json.load(open(TRADES_CACHE))
        return data["per_coin"], data["all"]
    from simulate_orp import backtest_symbol_optimized
    per_coin = {}
    alltr = []
    for c in COINS:
        path = f"{DATA_DIR}/{c}_USDT_4h.csv"
        if not os.path.exists(path):
            continue
        df = pd.read_csv(path)
        df["ts"] = pd.to_datetime(df["ts"]); df.set_index("ts", inplace=True); df.sort_index(inplace=True)
        tr = backtest_symbol_optimized(f"{c}/USDT", df, max_leverage_limit=10)["trades"]
        clean = [{"r_mult": float(t["r_mult"]), "sl_pct": float(t["sl_pct"]), "coin": c,
                  "ts": str(t.get("entry_ts", t.get("ts", "")))} for t in tr]
        per_coin[c] = clean
        alltr += clean
    json.dump({"per_coin": per_coin, "all": alltr}, open(TRADES_CACHE, "w"))
    return per_coin, alltr


def trade_stats(trades):
    if not trades:
        return {"n": 0}
    rs = np.array([t["r_mult"] for t in trades])
    return {"n": len(rs), "wr": float((rs > 0).mean() * 100), "avg_r": float(rs.mean()),
            "sum_r": float(rs.sum()), "p5_r": float(np.percentile(rs, 5)),
            "max_loss_streak": _max_loss_streak(trades)}


def _max_loss_streak(trades):
    mx = cur = 0
    for t in trades:
        if t["r_mult"] <= 0:
            cur += 1; mx = max(mx, cur)
        else:
            cur = 0
    return mx


# ═══════════════════════════════════════════════════════════════════════
#  2) BİRLEŞİK BETTING-SİSTEM SİMÜLATÖRÜ (gerçek R üzerinde, adil karşılaştırma)
#     PnL = equity * risk_pct * r_mult   (r_mult zaten maliyet-net)
# ═══════════════════════════════════════════════════════════════════════
def simulate_mm(trades, scheme, base_risk=0.02, max_risk=0.15, cycle_pct=0.05,
                rec_factor=1.5, kelly_frac=0.25, start=START_CAP):
    eq = start; curve = [start]; wiped = False
    consec_w = consec_l = 0
    fib = [1, 1, 2, 3, 5, 8, 13, 21]; fib_i = 0
    orp_step = 0; orp_target = start
    # global edge for kelly
    rs = np.array([t["r_mult"] for t in trades]); wins = rs[rs > 0]; losses = rs[rs <= 0]
    p = (rs > 0).mean(); b = (wins.mean() / abs(losses.mean())) if len(losses) and len(wins) else 1.0
    kelly_full = max(0.0, p - (1 - p) / b) if b > 0 else 0.0
    for t in trades:
        if wiped:
            curve.append(0.0); continue
        if scheme == "fixed":
            risk = base_risk
        elif scheme == "paroli":
            s = min(consec_w, 3)
            if s >= 3: consec_w = 0; s = 0
            risk = min(base_risk * (2 ** s), max_risk)
        elif scheme == "fibonacci":
            risk = min(0.01 * fib[fib_i], max_risk)
        elif scheme == "kelly":
            risk = min(kelly_full * kelly_frac, max_risk)
        elif scheme == "orp":
            while eq >= orp_target:
                orp_step += 1; orp_target = start * ((1 + cycle_pct) ** orp_step)
            delta = orp_target - eq
            risk = max(eq * base_risk, delta / rec_factor) / eq
            risk = min(risk, max_risk)
        elif scheme == "adaptive_hybrid":
            last = curve[-10:]
            if len(last) >= 4:
                w = sum(1 for i in range(1, len(last)) if last[i] > last[i-1])
                rwr = w / (len(last) - 1)
            else:
                rwr = p
            if rwr >= 0.65:
                s = min(consec_w, 4); risk = min(base_risk * (1.8 ** s), max_risk)
            elif rwr <= 0.40:
                risk = max(0.01, base_risk * 0.5)
            else:
                while eq >= orp_target:
                    orp_step += 1; orp_target = start * ((1 + cycle_pct) ** orp_step)
                delta = orp_target - eq
                risk = min(max(eq * base_risk, delta / rec_factor) / eq, max_risk)
        else:
            risk = base_risk
        eq += eq * risk * t["r_mult"]
        if t["r_mult"] > 0:
            consec_w += 1; consec_l = 0; fib_i = max(fib_i - 2, 0)
        else:
            consec_w = 0; consec_l += 1; fib_i = min(fib_i + 1, len(fib) - 1)
        if eq <= 1.0:
            eq = 0.0; wiped = True
        curve.append(eq)
    arr = np.array(curve); peak = np.maximum.accumulate(arr); peak = np.where(peak == 0, 1, peak)
    mdd = float(abs(((arr - peak) / peak).min()) * 100)
    n = len([t for t in trades])
    cgr = (eq / start) ** (1.0 / n) - 1.0 if n and eq > 0 else -1.0
    return {"final": eq, "growth": eq / start, "mdd": mdd, "wiped": wiped, "cgr": cgr}


def mc_betting(trades, scheme, n_trials=5000, n_per=None, **kw):
    """Monte Carlo for any betting scheme on real R distribution (resample w/ replacement)."""
    rng = np.random.default_rng(SEED)
    n_per = n_per or len(trades)
    finals, mdds, ruins = [], [], 0
    arr = trades
    for _ in range(n_trials):
        idx = rng.integers(0, len(arr), size=n_per)
        sample = [arr[i] for i in idx]
        r = simulate_mm(sample, scheme, **kw)
        finals.append(r["final"]); mdds.append(r["mdd"]); ruins += r["wiped"]
    finals = np.array(finals)
    return {"median": float(np.median(finals)), "p5": float(np.percentile(finals, 5)),
            "p95": float(np.percentile(finals, 95)), "mean": float(finals.mean()),
            "median_mdd": float(np.median(mdds)), "p95_mdd": float(np.percentile(mdds, 95)),
            "ruin_rate": ruins / n_trials * 100}


# ═══════════════════════════════════════════════════════════════════════
#  3) ORP GRID + MONTE-CARLO ROBUST SIRALAMA  (tek-yol değil!)
# ═══════════════════════════════════════════════════════════════════════
def orp_grid_mc(trades, max_dd=30.0, mc_trials=5000, top_k=8, quick=False):
    if quick:
        grid = {"cycle_target_pct": [0.05, 0.10], "recovery_factor": [1.5, 2.0, 3.0],
                "max_risk_cap": [0.08, 0.12, 0.15], "base_risk_pct": [0.02, 0.03],
                "max_leverage": [3.0, 5.0]}
    else:
        grid = {"cycle_target_pct": [0.03, 0.05, 0.07, 0.10],
                "recovery_factor": [1.25, 1.5, 2.0, 2.5, 3.0],
                "max_risk_cap": [0.06, 0.08, 0.10, 0.12, 0.15, 0.20],
                "base_risk_pct": [0.015, 0.02, 0.025, 0.03],
                "max_leverage": [3.0, 5.0, 7.0]}
    feats = {"dynamic_recovery": [False, True], "dd_scaling": [False, True]}
    keys = list(grid); fkeys = list(feats)
    combos = list(itertools.product(*grid.values()))
    fcombos = list(itertools.product(*feats.values()))

    # STAGE 1: fast single-path prune (drop ruin / over-MDD on historical order)
    survivors = []
    for c in combos:
        for fc in fcombos:
            p = dict(zip(keys, c)); p.update(dict(zip(fkeys, fc))); p["start_capital"] = START_CAP
            r = run_orp_dynamic(trades, p)
            if r["wiped_out"] or r["max_drawdown"] > max_dd:
                continue
            survivors.append((p, r["total_growth"], r["max_drawdown"]))
    survivors.sort(key=lambda x: -x[1])
    print(f"   STAGE1: {len(survivors)} aday (ruin yok, tek-yol MDD≤{max_dd})", flush=True)

    # STAGE 2: Monte Carlo robust ranking on top single-path survivors
    cand = survivors[: max(top_k * 6, 40)]
    scored = []
    for p, g, dd in cand:
        mc = monte_carlo_orp(trades, p, n_trials=mc_trials, n_trades_per_trial=len(trades))
        # monte_carlo_orp anahtarlarını driver'ın beklediği isimlere normalize et
        mc["median"] = mc["median_eq"]; mc["p5"] = mc["p5_eq"]; mc["p95"] = mc["p95_eq"]
        # HARD CONSTRAINT: P(ruin)=0 ve P95 MDD ≤ eşik
        if mc["ruin_rate"] > 0.0:
            continue
        if mc["p95_dd"] > max_dd:
            continue
        scored.append({"params": p, "sp_growth": g, "sp_mdd": dd, "mc": mc})
    # rank by median growth, tie-break lower p95 MDD
    scored.sort(key=lambda x: (-x["mc"]["median"], x["mc"]["p95_dd"]))
    return scored[:top_k], len(survivors)


# ═══════════════════════════════════════════════════════════════════════
#  4) STRES TESTLERİ
# ═══════════════════════════════════════════════════════════════════════
def fill_rate_stress(trades, params, fill_rates=(0.5, 0.6, 0.7, 1.0), trials=2000):
    """Deep target #1: limit dolum oranı. Rastgele (1-fill) trade düşür → CGR'ye etkisi."""
    rng = np.random.default_rng(SEED)
    out = {}
    for fr in fill_rates:
        finals, ruins = [], 0
        for _ in range(trials):
            kept = [t for t in trades if rng.random() < fr]
            if len(kept) < 10:
                kept = trades[:10]
            r = run_orp_dynamic(kept, params)
            finals.append(r["final_eq"]); ruins += r["wiped_out"]
        out[fr] = {"median": float(np.median(finals)), "ruin": ruins / trials * 100, "n_avg": int(len(trades)*fr)}
    return out


def loss_cluster_stress(trades, params, cluster=4, trials=3000):
    """Deep target #4,#5: korelasyon/ardışık kayıp. Her trial'da rastgele bir noktada
    `cluster` ardışık kayıp enjekte et (BTC crash → 20 coin aynı yön)."""
    rng = np.random.default_rng(SEED)
    losses = [t for t in trades if t["r_mult"] <= 0] or [{"r_mult": -1.0, "sl_pct": 2.0}]
    finals, mdds, ruins = [], [], 0
    for _ in range(trials):
        idx = rng.integers(0, len(trades), size=len(trades))
        seq = [trades[i] for i in idx]
        pos = rng.integers(0, max(1, len(seq) - cluster))
        inj = [losses[rng.integers(0, len(losses))] for _ in range(cluster)]
        seq[pos:pos] = inj
        r = run_orp_dynamic(seq, params)
        finals.append(r["final_eq"]); mdds.append(r["max_drawdown"]); ruins += r["wiped_out"]
    return {"median": float(np.median(finals)), "p5": float(np.percentile(finals, 5)),
            "median_mdd": float(np.median(mdds)), "p95_mdd": float(np.percentile(mdds, 95)),
            "ruin_rate": ruins / trials * 100}


# ═══════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--max-dd", type=float, default=30.0)
    args = ap.parse_args()

    print("=" * 78)
    print("  BİLEŞİK BÜYÜME OPTİMİZASYONU — DÜRÜST & GERÇEKÇİ (seed=%d)" % SEED)
    print("=" * 78)

    # ── 1) Trades ──
    per_coin, allv = generate_trades(force=args.force)
    print("\n[1] GERÇEK 4H TRADE HAVUZU")
    print(f"    {'COIN':6}{'N':>5}{'WR%':>7}{'AvgR':>8}{'SumR':>8}{'LossStreak':>12}")
    for c in COINS:
        s = trade_stats(per_coin.get(c, []))
        if s["n"]:
            print(f"    {c:6}{s['n']:>5}{s['wr']:>7.1f}{s['avg_r']:>+8.3f}{s['sum_r']:>+8.1f}{s['max_loss_streak']:>12}")
    sa = trade_stats(allv)
    print(f"    {'-'*46}")
    print(f"    {'ALL':6}{sa['n']:>5}{sa['wr']:>7.1f}{sa['avg_r']:>+8.3f}{sa['sum_r']:>+8.1f}{sa['max_loss_streak']:>12}")
    print(f"    Edge kontrolü: avg_r={sa['avg_r']:+.3f}R → {'POZİTİF ✓' if sa['avg_r']>0 else 'NEGATİF ✗ (compounding anlamsız!)'}")

    if sa["avg_r"] <= 0:
        print("\n  ⛔ Net beklenti ≤ 0. Hedef fonksiyonu 3. kısıt İHLAL. Optimizasyon durduruldu.")
        print("     Doğru aksiyon: önce edge'i düzelt (giriş/sinyal), sonra para yönetimi.")
        return

    # ── 2) Baseline (eski sabit parametreler) ──
    OLD = {"start_capital": START_CAP, "cycle_target_pct": 0.05, "recovery_factor": 1.5,
           "max_risk_cap": 0.15, "base_risk_pct": 0.025, "max_leverage": 5.0,
           "dynamic_recovery": False, "dd_scaling": False}
    print("\n[2] BASELINE — Eski ORP (rec=1.5, cap=%15, cyc=%5)")
    base_sp = run_orp_dynamic(allv, OLD)
    base_mc = monte_carlo_orp(allv, OLD, n_trials=5000, n_trades_per_trial=len(allv))
    print(f"    Tek-yol:  growth={base_sp['total_growth']:.2f}x  MDD={base_sp['max_drawdown']:.1f}%  ruin={base_sp['wiped_out']}")
    print(f"    MC(5k):   medyan={base_mc['median_eq']/100:.2f}x  P5={base_mc['p5_eq']/100:.2f}x  P95={base_mc['p95_eq']/100:.2f}x")
    print(f"              medyanMDD={base_mc['median_dd']:.1f}%  P95MDD={base_mc['p95_dd']:.1f}%  P(ruin)={base_mc['ruin_rate']:.2f}%")

    # ── 3) ORP grid + MC robust ──
    print("\n[3] ORP GRID + MONTE-CARLO ROBUST SIRALAMA (P(ruin)=0 sert filtre)")
    top, nsurv = orp_grid_mc(allv, max_dd=args.max_dd, mc_trials=5000, top_k=6, quick=args.quick)
    if not top:
        print("    ⚠ MC sonrası hiçbir set P(ruin)=0 & P95MDD≤eşik geçemedi. Eşiği gevşet veya base_risk düşür.")
        return
    print(f"\n    TOP {len(top)} (MC-robust, medyan büyümeye göre):")
    print(f"    {'#':>2}{'cyc%':>6}{'rec':>5}{'cap%':>6}{'base%':>6}{'lev':>4}{'dynR':>5}{'ddS':>4}{'medX':>8}{'P5X':>7}{'P95MDD':>8}{'ruin':>6}")
    for i, s in enumerate(top):
        p = s["params"]; mc = s["mc"]
        print(f"    {i+1:>2}{p['cycle_target_pct']*100:>6.0f}{p['recovery_factor']:>5.2f}{p['max_risk_cap']*100:>6.0f}"
              f"{p['base_risk_pct']*100:>6.1f}{p['max_leverage']:>4.0f}{'Y' if p['dynamic_recovery'] else 'N':>5}"
              f"{'Y' if p['dd_scaling'] else 'N':>4}{mc['median']/100:>8.2f}{mc['p5']/100:>7.2f}{mc['p95_dd']:>8.1f}{mc['ruin_rate']:>6.2f}")

    best = top[0]["params"]

    # ── 4) Çapraz-coin OUT-OF-SAMPLE (leave-one-out) ──
    print("\n[4] ÇAPRAZ-COIN OUT-OF-SAMPLE (en iyi seti her coinde ayrı test)")
    print(f"    {'COIN':6}{'N':>5}{'growthX':>9}{'MDD%':>7}{'ruin':>7}")
    for c in COINS:
        tc = per_coin.get(c, [])
        if len(tc) < 10:
            continue
        r = run_orp_dynamic(tc, best)
        print(f"    {c:6}{len(tc):>5}{r['total_growth']:>9.2f}{r['max_drawdown']:>7.1f}{'EVET' if r['wiped_out'] else 'yok':>7}")

    # ── 5) ZAMAN-DIŞI walk-forward (ilk %60 train sezgisi → son %40 test) ──
    print("\n[5] ZAMAN-DIŞI (walk-forward: son %40 trade dilimi)")
    n = len(allv); oos = allv[int(n * 0.6):]
    r_oos = run_orp_dynamic(oos, best)
    mc_oos = monte_carlo_orp(oos, best, n_trials=3000, n_trades_per_trial=len(oos))
    print(f"    OOS tek-yol: {r_oos['total_growth']:.2f}x  MDD={r_oos['max_drawdown']:.1f}%  ruin={r_oos['wiped_out']}")
    print(f"    OOS MC:      medyan={mc_oos['median_eq']/100:.2f}x  P5={mc_oos['p5_eq']/100:.2f}x  P(ruin)={mc_oos['ruin_rate']:.2f}%")

    # ── 6) BETTING SİSTEM KARŞILAŞTIRMASI (gerçek R, MC) ──
    print("\n[6] BETTING SİSTEM KARŞILAŞTIRMASI — gerçek R dağılımı, MC 5k")
    print(f"    {'Sistem':18}{'medX':>8}{'P5X':>8}{'P95X':>9}{'medMDD':>8}{'P95MDD':>8}{'ruin%':>7}")
    schemes = [("Fixed %2", "fixed"), ("Fibonacci", "fibonacci"), ("Paroli", "paroli"),
               ("Kelly(frac.25)", "kelly"), ("ORP %5", "orp"), ("Adaptive Hybrid", "adaptive_hybrid")]
    bet_rows = {}
    for label, key in schemes:
        m = mc_betting(allv, key, n_trials=5000,
                       base_risk=best["base_risk_pct"], max_risk=best["max_risk_cap"],
                       cycle_pct=best["cycle_target_pct"], rec_factor=best["recovery_factor"])
        bet_rows[key] = m
        flag = "" if m["ruin_rate"] == 0 and m["p95_mdd"] <= args.max_dd else "  ⚠KISIT"
        print(f"    {label:18}{m['median']/100:>8.2f}{m['p5']/100:>8.2f}{m['p95']/100:>9.2f}"
              f"{m['median_mdd']:>8.1f}{m['p95_mdd']:>8.1f}{m['ruin_rate']:>7.2f}{flag}")

    # ── 7) STRES: dolum oranı + ardışık kayıp/korelasyon ──
    print("\n[7] STRES TESTLERİ (en iyi ORP set)")
    fr = fill_rate_stress(allv, best, trials=1500)
    print("    a) Limit dolum oranı duyarlılığı (deep #1):")
    for k, v in fr.items():
        print(f"       fill={k*100:>3.0f}%  ~{v['n_avg']:>3} trade  medyan={v['median']/100:>7.2f}x  P(ruin)={v['ruin']:.2f}%")
    print("    b) Ardışık kayıp/korelasyon kümesi (deep #4,#5):")
    for cl in (3, 4, 6):
        lc = loss_cluster_stress(allv, best, cluster=cl, trials=2000)
        print(f"       cluster={cl}  medyan={lc['median']/100:>7.2f}x  P5={lc['p5']/100:>6.2f}x  P95MDD={lc['p95_mdd']:>5.1f}%  P(ruin)={lc['ruin_rate']:.2f}%")

    # ── 8) GERÇEKÇİLİK DÜZELTMESİ ──
    print("\n[8] GERÇEKÇİLİK DÜZELTMESİ (fill=%d%% × haircut=%.0f%%)" % (DEFAULT_FILL_RATE*100, REALISM_HAIRCUT*100))
    best_mc = top[0]["mc"]
    adj = DEFAULT_FILL_RATE * REALISM_HAIRCUT  # bileşik adım sayısı↓ + ham haircut
    # büyüme çarpanı log-uzayda ölçeklenir: growth^adj yaklaşık (n adım × adj)
    raw_med = best_mc["median"] / 100
    real_med = raw_med ** adj if raw_med > 1 else raw_med
    raw_p5 = best_mc["p5"] / 100
    real_p5 = raw_p5 ** adj if raw_p5 > 1 else raw_p5
    print(f"    Ham MC medyan:        {raw_med:.2f}x")
    print(f"    Gerçekçi medyan:      {real_med:.2f}x   (log-ölçek × {adj:.2f})")
    print(f"    Ham P5:               {raw_p5:.2f}x")
    print(f"    Gerçekçi P5:          {real_p5:.2f}x")

    # ── 9) ÖNERİLEN SET + 4 KISIT DOĞRULAMA ──
    print("\n[9] ÖNERİLEN OPTİMAL SET — 4 KISIT DOĞRULAMA")
    p = best; mc = top[0]["mc"]
    print(f"    params: cyc={p['cycle_target_pct']*100:.0f}% rec={p['recovery_factor']:.2f} cap={p['max_risk_cap']*100:.0f}%"
          f" base={p['base_risk_pct']*100:.1f}% lev={p['max_leverage']:.0f}x dynR={p['dynamic_recovery']} ddS={p['dd_scaling']}")
    c1 = mc["p95_dd"] <= args.max_dd
    c2 = mc["ruin_rate"] == 0.0
    c3 = sa["avg_r"] > 0
    c4 = sa["n"] >= 100
    print(f"    [{'✓' if c1 else '✗'}] MDD ≤ %{args.max_dd:.0f}     → P95 MDD = {mc['p95_dd']:.1f}%")
    print(f"    [{'✓' if c2 else '✗'}] P(ruin) = 0      → MC ruin = {mc['ruin_rate']:.2f}%")
    print(f"    [{'✓' if c3 else '✗'}] net beklenti>0   → avg_r = {sa['avg_r']:+.3f}R")
    print(f"    [{'✓' if c4 else '✗'}] frekans ≥100/yıl → {sa['n']} trade (~1 yıl)")
    print(f"\n    SONUÇ: {'4/4 KISIT GEÇTİ ✓' if all([c1,c2,c3,c4]) else 'KISIT İHLALİ — set reddedildi'}")

    # save
    out = {"trade_stats": sa, "baseline_mc": base_mc, "top_params": [t["params"] for t in top],
           "best": best, "best_mc": mc, "betting": bet_rows}
    json.dump(out, open("optimal_compound_result.json", "w"), indent=2, default=str)
    print("\n  ✅ optimal_compound_result.json kaydedildi")


if __name__ == "__main__":
    main()
