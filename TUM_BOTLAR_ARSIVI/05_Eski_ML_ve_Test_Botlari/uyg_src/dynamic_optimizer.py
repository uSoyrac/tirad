#!/usr/bin/env python3
"""
DYNAMIC PARAMETER OPTIMIZER — Alpha İstihbarat
═══════════════════════════════════════════════════════════════
Master Prompt'taki felsefeye uygun:
- Hiçbir parametre sabit değil, hepsi optimize edilecek
- Hedef: Maximize CGR subject to MDD ≤ threshold, P(ruin) = 0
- Yöntem: Grid Search + Monte Carlo Validation
"""
import os, sys, math, time, warnings, itertools, json
import numpy as np
import pandas as pd
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed

warnings.filterwarnings("ignore")

# ═══════════════════════════════════════════════════════════════
#  CORE ORP ENGINE — FULLY PARAMETERIZED (NO HARDCODED VALUES)
# ═══════════════════════════════════════════════════════════════

def run_orp_dynamic(trades, params):
    """
    Fully parameterized ORP engine.
    
    params dict keys:
        start_capital: float (default 100)
        cycle_target_pct: float — each ORP cycle growth target (e.g. 0.05 = 5%)
        recovery_factor: float — deficit divisor for recovery risk (was hardcoded 1.5)
        max_risk_cap: float — max fraction of equity risked per trade (was hardcoded 0.15)
        base_risk_pct: float — minimum risk when no deficit (was hardcoded 0.025)
        max_leverage: float — max leverage cap (was hardcoded 5.0)
        dynamic_recovery: bool — if True, recovery_factor adapts based on consecutive losses
        dd_scaling: bool — if True, max_risk_cap shrinks as drawdown deepens
    """
    start_capital = params.get("start_capital", 100.0)
    cycle_pct = params["cycle_target_pct"]
    rec_factor = params["recovery_factor"]
    max_risk = params["max_risk_cap"]
    base_risk = params["base_risk_pct"]
    max_lev = params["max_leverage"]
    dynamic_recovery = params.get("dynamic_recovery", False)
    dd_scaling = params.get("dd_scaling", False)
    
    equity = start_capital
    target_step = 0
    target_equity = start_capital
    equity_curve = [start_capital]
    wiped_out = False
    max_lev_used = 1.0
    peak_equity = start_capital
    consecutive_losses = 0
    total_wins = 0
    total_trades = 0
    
    for t in trades:
        if wiped_out:
            equity_curve.append(0.0)
            continue
        
        # Update target equity
        while equity >= target_equity:
            target_step += 1
            target_equity = start_capital * ((1.0 + cycle_pct) ** target_step)
        
        # Track drawdown
        if equity > peak_equity:
            peak_equity = equity
        current_dd = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0
        
        # --- DYNAMIC RECOVERY FACTOR ---
        if dynamic_recovery:
            # Adapt recovery aggressiveness based on consecutive losses
            # More losses = less aggressive (protect capital)
            # Fewer losses = more aggressive (recover faster)
            if consecutive_losses >= 3:
                effective_rec = rec_factor * 1.5  # More conservative after 3+ losses
            elif consecutive_losses >= 2:
                effective_rec = rec_factor * 1.2
            else:
                effective_rec = rec_factor
        else:
            effective_rec = rec_factor
        
        # --- DYNAMIC DD SCALING ---
        if dd_scaling:
            # Reduce max risk as drawdown deepens
            if current_dd > 0.20:
                effective_max_risk = max_risk * 0.5  # Half risk at 20%+ DD
            elif current_dd > 0.10:
                effective_max_risk = max_risk * 0.75  # 75% at 10-20% DD
            else:
                effective_max_risk = max_risk
        else:
            effective_max_risk = max_risk
        
        # Calculate risk
        delta = target_equity - equity
        base_risk_amt = equity * base_risk
        required_risk = max(base_risk_amt, delta / effective_rec)
        
        # SL fraction from trade data
        sl_fraction = t["sl_pct"] / 100.0
        if sl_fraction <= 0.0:
            sl_fraction = 0.015
        
        # Position sizing
        pos_size = required_risk / sl_fraction
        req_lev = pos_size / equity if equity > 0 else 999
        
        actual_lev = min(req_lev, max_lev)
        max_lev_used = max(max_lev_used, actual_lev)
        
        actual_pos_size = actual_lev * equity
        actual_risk = actual_pos_size * sl_fraction
        
        # Apply risk cap
        if actual_risk > equity * effective_max_risk:
            actual_risk = equity * effective_max_risk
            actual_pos_size = actual_risk / sl_fraction
            actual_lev = actual_pos_size / equity if equity > 0 else 0
        
        # Execute trade
        dollar_pnl = actual_risk * t["r_mult"]
        equity += dollar_pnl
        total_trades += 1
        
        # Track consecutive losses
        if t["r_mult"] > 0:
            consecutive_losses = 0
            total_wins += 1
        else:
            consecutive_losses += 1
        
        # Ruin check
        if equity <= 1.0:
            equity = 0.0
            wiped_out = True
        
        equity_curve.append(equity)
    
    # Calculate metrics
    eq_arr = np.array(equity_curve)
    if len(eq_arr) > 1:
        peak_arr = np.maximum.accumulate(eq_arr)
        peak_arr = np.where(peak_arr == 0, 1.0, peak_arr)
        dd_arr = (eq_arr - peak_arr) / peak_arr
        max_drawdown = float(abs(dd_arr.min()) * 100)
    else:
        max_drawdown = 0.0
    
    if equity > 0 and equity > start_capital:
        steps_achieved = int(math.log(equity / start_capital) / math.log(1.0 + cycle_pct))
    else:
        steps_achieved = 0
    
    # Compound Growth Rate (per trade)
    if total_trades > 0 and equity > 0 and start_capital > 0:
        cgr = (equity / start_capital) ** (1.0 / total_trades) - 1.0
    else:
        cgr = -1.0
    
    win_rate = total_wins / total_trades * 100 if total_trades > 0 else 0
    
    return {
        "final_eq": equity,
        "max_drawdown": max_drawdown,
        "max_lev_used": max_lev_used,
        "wiped_out": wiped_out,
        "steps_achieved": steps_achieved,
        "cgr_per_trade": cgr,
        "total_growth": equity / start_capital if start_capital > 0 else 0,
        "win_rate": win_rate,
        "total_trades": total_trades
    }


# ═══════════════════════════════════════════════════════════════
#  MONTE CARLO ENGINE
# ═══════════════════════════════════════════════════════════════

def monte_carlo_orp(trades, params, n_trials=1000, n_trades_per_trial=None):
    """
    Monte Carlo simulation: shuffle trade order, run ORP, collect statistics.
    """
    if n_trades_per_trial is None:
        n_trades_per_trial = len(trades)
    
    results = []
    rng = np.random.default_rng(42)
    
    for _ in range(n_trials):
        # Resample with replacement
        indices = rng.integers(0, len(trades), size=n_trades_per_trial)
        sampled = [trades[i] for i in indices]
        
        res = run_orp_dynamic(sampled, params)
        results.append(res)
    
    final_eqs = [r["final_eq"] for r in results]
    max_dds = [r["max_drawdown"] for r in results]
    ruin_count = sum(1 for r in results if r["wiped_out"])
    
    return {
        "median_eq": float(np.median(final_eqs)),
        "mean_eq": float(np.mean(final_eqs)),
        "p5_eq": float(np.percentile(final_eqs, 5)),
        "p25_eq": float(np.percentile(final_eqs, 25)),
        "p75_eq": float(np.percentile(final_eqs, 75)),
        "p95_eq": float(np.percentile(final_eqs, 95)),
        "median_dd": float(np.median(max_dds)),
        "p95_dd": float(np.percentile(max_dds, 95)),
        "max_dd": float(np.max(max_dds)),
        "ruin_rate": ruin_count / n_trials * 100,
        "n_trials": n_trials
    }


# ═══════════════════════════════════════════════════════════════
#  GRID SEARCH OPTIMIZER
# ═══════════════════════════════════════════════════════════════

def grid_search(trades, max_dd_threshold=30.0):
    """
    Grid search over ALL ORP parameters.
    Returns sorted list of parameter combinations ranked by CGR.
    """
    # Parameter grid — NO hardcoded values, AI explores full space
    param_grid = {
        "cycle_target_pct": [0.02, 0.03, 0.05, 0.07, 0.10],
        "recovery_factor":  [1.0, 1.25, 1.5, 2.0, 2.5, 3.0],
        "max_risk_cap":     [0.08, 0.10, 0.15, 0.20, 0.25, 0.30],
        "base_risk_pct":    [0.015, 0.02, 0.025, 0.03, 0.04],
        "max_leverage":     [2.0, 3.0, 5.0, 7.0, 10.0],
    }
    
    # Feature toggles
    feature_grid = {
        "dynamic_recovery": [False, True],
        "dd_scaling":       [False, True],
    }
    
    keys = list(param_grid.keys())
    feat_keys = list(feature_grid.keys())
    
    all_combos = list(itertools.product(*param_grid.values()))
    feat_combos = list(itertools.product(*feature_grid.values()))
    
    total = len(all_combos) * len(feat_combos)
    print(f"\n📊 Grid Search: {total:,} kombinasyon test ediliyor...")
    print(f"   Max DD Threshold: %{max_dd_threshold}")
    
    results = []
    tested = 0
    t0 = time.time()
    
    for combo in all_combos:
        for feat_combo in feat_combos:
            params = dict(zip(keys, combo))
            params.update(dict(zip(feat_keys, feat_combo)))
            params["start_capital"] = 100.0
            
            res = run_orp_dynamic(trades, params)
            
            tested += 1
            if tested % 500 == 0:
                elapsed = time.time() - t0
                rate = tested / elapsed
                eta = (total - tested) / rate
                sys.stdout.write(f"\r   İlerleme: {tested}/{total} ({tested/total*100:.1f}%) | ETA: {eta:.0f}s")
                sys.stdout.flush()
            
            # Filter: only keep non-ruin results within DD threshold
            if res["wiped_out"]:
                continue
            
            results.append({
                "params": params.copy(),
                "final_eq": res["final_eq"],
                "total_growth": res["total_growth"],
                "max_drawdown": res["max_drawdown"],
                "cgr_per_trade": res["cgr_per_trade"],
                "steps_achieved": res["steps_achieved"],
                "max_lev_used": res["max_lev_used"],
            })
    
    elapsed = time.time() - t0
    print(f"\n   ✅ Tamamlandı: {elapsed:.1f}s | {len(results)} geçerli sonuç (toplam {total})")
    
    # Sort by total growth (descending), then by max_drawdown (ascending)
    results.sort(key=lambda x: (-x["total_growth"], x["max_drawdown"]))
    
    # Filter by DD threshold
    filtered = [r for r in results if r["max_drawdown"] <= max_dd_threshold]
    
    return filtered, results


def print_top_results(results, n=20):
    """Print top N results in a formatted table."""
    print(f"\n{'='*140}")
    print(f"{'#':>3} | {'Cycle%':>7} | {'RecFac':>7} | {'MaxRisk':>8} | {'BaseRisk':>9} | {'MaxLev':>7} | {'DynRec':>6} | {'DDScl':>5} | {'Growth':>10} | {'MaxDD%':>7} | {'Steps':>6} | {'MaxLevUsed':>11}")
    print(f"{'-'*140}")
    
    for i, r in enumerate(results[:n]):
        p = r["params"]
        print(f"{i+1:>3} | {p['cycle_target_pct']*100:>6.1f}% | {p['recovery_factor']:>7.2f} | {p['max_risk_cap']*100:>7.1f}% | {p['base_risk_pct']*100:>8.2f}% | {p['max_leverage']:>6.1f}x | {'Y' if p.get('dynamic_recovery') else 'N':>6} | {'Y' if p.get('dd_scaling') else 'N':>5} | {r['total_growth']:>9.1f}x | {r['max_drawdown']:>6.1f}% | {r['steps_achieved']:>6} | {r['max_lev_used']:>10.2f}x")


# ═══════════════════════════════════════════════════════════════
#  TRADE DATA LOADERS
# ═══════════════════════════════════════════════════════════════

def load_trades_from_backtest(symbol="ETH", tf="1h"):
    """Load and run backtest to generate trade sequence."""
    csv_path = f"data/historical/{symbol}_USDT_{tf}.csv"
    if not os.path.exists(csv_path):
        print(f"❌ Veri bulunamadı: {csv_path}")
        return []
    
    from backtest_multi_tf import score_slice_v2, WARMUP, EMA_TREND_PERIOD
    
    df = pd.read_csv(csv_path)
    df["ts"] = pd.to_datetime(df["ts"])
    df.set_index("ts", inplace=True)
    df = df.sort_index()
    
    bar_limit = {"1d": 365, "4h": 2190, "1h": 4000, "30m": 4000, "15m": 4000}.get(tf, 4000)
    df = df.tail(bar_limit)
    
    if df.empty or len(df) < WARMUP + 20:
        print(f"❌ Yetersiz veri: {len(df)} bar")
        return []
    
    from simulate_orp import backtest_symbol_optimized
    print(f"  📈 {symbol}/USDT {tf} backtest çalıştırılıyor ({len(df)} bar)...")
    
    t0 = time.time()
    result = backtest_symbol_optimized(f"{symbol}/USDT", df, max_leverage_limit=10)
    elapsed = time.time() - t0
    
    trades = result["trades"]
    print(f"  ✅ {len(trades)} işlem üretildi ({elapsed:.1f}s)")
    
    return trades


def load_trades_confluence(symbol="ETH", limit_days=180):
    """Load trades from 15M confluence backtest."""
    from simulate_15m_confluence import run_confluence_backtest
    
    print(f"  📈 {symbol} 1H+15M Confluence backtest ({limit_days} gün)...")
    t0 = time.time()
    res = run_confluence_backtest(symbol, limit_days=limit_days)
    elapsed = time.time() - t0
    
    if not res or not res["trades"]:
        print(f"  ❌ İşlem üretilmedi")
        return []
    
    trades = res["trades"]
    print(f"  ✅ {len(trades)} işlem ({elapsed:.1f}s)")
    return trades


# ═══════════════════════════════════════════════════════════════
#  MAIN — FULL OPTIMIZATION PIPELINE
# ═══════════════════════════════════════════════════════════════

def main():
    print("\n" + "="*80)
    print("  🧠 ALPHA İSTİHBARAT — DİNAMİK PARAMETRE OPTİMİZASYONU")
    print("  Master Prompt v2.0: Hiçbir parametre sabit değil")
    print("="*80)
    
    # ── STEP 1: Load trade data ──
    print("\n" + "─"*60)
    print("  ADIM 1: İşlem Verisi Yükleme")
    print("─"*60)
    
    # Load from multiple sources for robustness
    trades_eth_1h = load_trades_from_backtest("ETH", "1h")
    trades_sol_1h = load_trades_from_backtest("SOL", "1h")
    trades_btc_1h = load_trades_from_backtest("BTC", "1h")
    
    # Combine for multi-coin portfolio simulation
    all_trades = trades_eth_1h + trades_sol_1h + trades_btc_1h
    
    if not all_trades:
        print("❌ Hiçbir veri yüklenemedi!")
        return
    
    print(f"\n  📊 Toplam İşlem: {len(all_trades)}")
    print(f"     ETH: {len(trades_eth_1h)} | SOL: {len(trades_sol_1h)} | BTC: {len(trades_btc_1h)}")
    
    wins = sum(1 for t in all_trades if t["r_mult"] > 0)
    avg_r = np.mean([t["r_mult"] for t in all_trades])
    print(f"     Win Rate: %{wins/len(all_trades)*100:.1f} | Ort R: {avg_r:+.3f}")
    
    # ── STEP 2: Grid Search ──
    print("\n" + "─"*60)
    print("  ADIM 2: Grid Search Optimizasyonu (ETH tek coin)")
    print("─"*60)
    
    if trades_eth_1h:
        filtered_eth, all_results_eth = grid_search(trades_eth_1h, max_dd_threshold=30.0)
        
        print(f"\n  🏆 ETH — TOP 20 SONUÇ (MDD ≤ %30):")
        print_top_results(filtered_eth, n=20)
        
        # Cross-validate top 5 on SOL
        if filtered_eth and trades_sol_1h:
            print(f"\n\n  🔬 ÇAPRAZ DOĞRULAMA — TOP 5 Parametreyi SOL'da Test Etme:")
            print(f"{'#':>3} | {'Growth(ETH)':>12} | {'Growth(SOL)':>12} | {'DD(ETH)':>8} | {'DD(SOL)':>8} | {'Cycle':>6} | {'RecFac':>7} | {'MaxRisk':>8}")
            print(f"{'-'*90}")
            
            for i, r in enumerate(filtered_eth[:5]):
                sol_res = run_orp_dynamic(trades_sol_1h, r["params"])
                print(f"{i+1:>3} | {r['total_growth']:>11.1f}x | {sol_res['total_growth']:>11.1f}x | {r['max_drawdown']:>7.1f}% | {sol_res['max_drawdown']:>7.1f}% | {r['params']['cycle_target_pct']*100:>5.1f}% | {r['params']['recovery_factor']:>7.2f} | {r['params']['max_risk_cap']*100:>7.1f}%")
        
        # BTC cross-validation
        if filtered_eth and trades_btc_1h:
            print(f"\n  🔬 ÇAPRAZ DOĞRULAMA — TOP 5 Parametreyi BTC'de Test Etme:")
            print(f"{'#':>3} | {'Growth(ETH)':>12} | {'Growth(BTC)':>12} | {'DD(ETH)':>8} | {'DD(BTC)':>8}")
            print(f"{'-'*70}")
            
            for i, r in enumerate(filtered_eth[:5]):
                btc_res = run_orp_dynamic(trades_btc_1h, r["params"])
                print(f"{i+1:>3} | {r['total_growth']:>11.1f}x | {btc_res['total_growth']:>11.1f}x | {r['max_drawdown']:>7.1f}% | {btc_res['max_drawdown']:>7.1f}%")
    
    # ── STEP 3: Monte Carlo Validation of Top 3 ──
    print("\n" + "─"*60)
    print("  ADIM 3: Monte Carlo Validasyonu (TOP 3 — 10,000 Trial)")
    print("─"*60)
    
    if filtered_eth:
        for i, r in enumerate(filtered_eth[:3]):
            params = r["params"]
            print(f"\n  🎰 Parametre Seti #{i+1}:")
            print(f"     Cycle: {params['cycle_target_pct']*100:.1f}% | RecFac: {params['recovery_factor']:.2f} | MaxRisk: {params['max_risk_cap']*100:.1f}% | BaseRisk: {params['base_risk_pct']*100:.2f}% | MaxLev: {params['max_leverage']:.1f}x | DynRec: {params.get('dynamic_recovery')} | DDScl: {params.get('dd_scaling')}")
            
            t0 = time.time()
            mc = monte_carlo_orp(trades_eth_1h, params, n_trials=10000, n_trades_per_trial=len(trades_eth_1h))
            elapsed = time.time() - t0
            
            print(f"     ────────────────────────────────────────")
            print(f"     Medyan Bitiş:     ${mc['median_eq']:>12,.2f} ({mc['median_eq']/100:.1f}x)")
            print(f"     Ortalama Bitiş:   ${mc['mean_eq']:>12,.2f}")
            print(f"     %5 Worst Case:    ${mc['p5_eq']:>12,.2f}")
            print(f"     %25 Percentile:   ${mc['p25_eq']:>12,.2f}")
            print(f"     %75 Percentile:   ${mc['p75_eq']:>12,.2f}")
            print(f"     %95 Best Case:    ${mc['p95_eq']:>12,.2f}")
            print(f"     Medyan Max DD:    %{mc['median_dd']:>6.1f}")
            print(f"     %95 Max DD:       %{mc['p95_dd']:>6.1f}")
            print(f"     Batma Oranı:      %{mc['ruin_rate']:>6.2f}")
            print(f"     ({elapsed:.1f}s | {mc['n_trials']} trial)")
            
            # Gerçekçi düzeltme (%50)
            realistic_median = mc['median_eq'] * 0.5
            realistic_worst = mc['p5_eq'] * 0.5
            print(f"\n     📍 GERÇEKÇİ DÜZELTME (%50):")
            print(f"        Medyan: ${realistic_median:>10,.2f} ({realistic_median/100:.1f}x)")
            print(f"        Worst:  ${realistic_worst:>10,.2f} ({realistic_worst/100:.1f}x)")
    
    # ── STEP 4: Multi-Coin Portfolio Test ──
    print("\n" + "─"*60)
    print("  ADIM 4: Çoklu Coin Portföy Optimizasyonu")
    print("─"*60)
    
    if filtered_eth and all_trades:
        best_params = filtered_eth[0]["params"]
        print(f"\n  🏆 En iyi ETH parametreleri ile portföy testi:")
        
        # Simulate multi-coin by merging trades from all coins
        portfolio_res = run_orp_dynamic(all_trades, best_params)
        
        print(f"     Portföy ({len(all_trades)} işlem):")
        print(f"     Bitiş: ${portfolio_res['final_eq']:>12,.2f} ({portfolio_res['total_growth']:.1f}x)")
        print(f"     Max DD: %{portfolio_res['max_drawdown']:.1f}")
        print(f"     Adımlar: {portfolio_res['steps_achieved']}")
        print(f"     Batma: {'❌ EVET' if portfolio_res['wiped_out'] else '✅ HAYIR'}")
        
        # Monte Carlo on portfolio
        print(f"\n  🎰 Portföy Monte Carlo (5,000 trial):")
        mc_port = monte_carlo_orp(all_trades, best_params, n_trials=5000, n_trades_per_trial=min(400, len(all_trades)))
        print(f"     Medyan: ${mc_port['median_eq']:>12,.2f} ({mc_port['median_eq']/100:.1f}x)")
        print(f"     %5 Worst: ${mc_port['p5_eq']:>12,.2f}")
        print(f"     Batma: %{mc_port['ruin_rate']:.2f}")
        print(f"     Medyan DD: %{mc_port['median_dd']:.1f}")
    
    # ── STEP 5: OLD vs NEW Comparison ──
    print("\n" + "─"*60)
    print("  ADIM 5: ESKİ (Sabit 1.5) vs YENİ (Optimized) Karşılaştırma")
    print("─"*60)
    
    if trades_eth_1h:
        old_params = {
            "start_capital": 100.0,
            "cycle_target_pct": 0.05,
            "recovery_factor": 1.5,
            "max_risk_cap": 0.15,
            "base_risk_pct": 0.025,
            "max_leverage": 5.0,
            "dynamic_recovery": False,
            "dd_scaling": False,
        }
        
        old_res = run_orp_dynamic(trades_eth_1h, old_params)
        
        if filtered_eth:
            new_params = filtered_eth[0]["params"]
            new_res = run_orp_dynamic(trades_eth_1h, new_params)
        else:
            new_res = old_res
            new_params = old_params
        
        print(f"\n  {'Metrik':<25} | {'ESKİ (1.5 sabit)':>18} | {'YENİ (optimized)':>18} | {'Fark':>10}")
        print(f"  {'-'*80}")
        print(f"  {'Cycle Target':.<25} | {old_params['cycle_target_pct']*100:>17.1f}% | {new_params['cycle_target_pct']*100:>17.1f}% |")
        print(f"  {'Recovery Factor':.<25} | {old_params['recovery_factor']:>18.2f} | {new_params['recovery_factor']:>18.2f} |")
        print(f"  {'Max Risk Cap':.<25} | {old_params['max_risk_cap']*100:>17.1f}% | {new_params['max_risk_cap']*100:>17.1f}% |")
        print(f"  {'Base Risk':.<25} | {old_params['base_risk_pct']*100:>17.2f}% | {new_params['base_risk_pct']*100:>17.2f}% |")
        print(f"  {'Max Leverage':.<25} | {old_params['max_leverage']:>17.1f}x | {new_params['max_leverage']:>17.1f}x |")
        print(f"  {'Dynamic Recovery':.<25} | {'Y' if old_params.get('dynamic_recovery') else 'N':>18} | {'Y' if new_params.get('dynamic_recovery') else 'N':>18} |")
        print(f"  {'DD Scaling':.<25} | {'Y' if old_params.get('dd_scaling') else 'N':>18} | {'Y' if new_params.get('dd_scaling') else 'N':>18} |")
        print(f"  {'-'*80}")
        
        growth_diff = (new_res['total_growth'] / old_res['total_growth'] - 1) * 100 if old_res['total_growth'] > 0 else 0
        dd_diff = new_res['max_drawdown'] - old_res['max_drawdown']
        
        print(f"  {'Bitiş ($)':.<25} | ${old_res['final_eq']:>17,.2f} | ${new_res['final_eq']:>17,.2f} | {'+' if growth_diff > 0 else ''}{growth_diff:.1f}%")
        print(f"  {'Büyüme (x)':.<25} | {old_res['total_growth']:>17.1f}x | {new_res['total_growth']:>17.1f}x |")
        print(f"  {'Max DD':.<25} | {old_res['max_drawdown']:>17.1f}% | {new_res['max_drawdown']:>17.1f}% | {'+' if dd_diff > 0 else ''}{dd_diff:.1f}%")
        print(f"  {'Adım':.<25} | {old_res['steps_achieved']:>18} | {new_res['steps_achieved']:>18} |")
        print(f"  {'Batma':.<25} | {'EVET' if old_res['wiped_out'] else 'HAYIR':>18} | {'EVET' if new_res['wiped_out'] else 'HAYIR':>18} |")
    
    # ── STEP 6: Save optimal params ──
    print("\n" + "─"*60)
    print("  ADIM 6: Optimal Parametreleri Kaydet")
    print("─"*60)
    
    if filtered_eth:
        output = {
            "version": "2.0_dynamic",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "optimization_method": "grid_search + monte_carlo",
            "top_5_params": [],
            "trade_data": {
                "eth_trades": len(trades_eth_1h),
                "sol_trades": len(trades_sol_1h),
                "btc_trades": len(trades_btc_1h),
            }
        }
        
        for i, r in enumerate(filtered_eth[:5]):
            entry = {
                "rank": i + 1,
                "params": {k: v for k, v in r["params"].items()},
                "backtest_growth": r["total_growth"],
                "backtest_max_dd": r["max_drawdown"],
                "steps_achieved": r["steps_achieved"],
            }
            output["top_5_params"].append(entry)
        
        out_path = "optimal_params.json"
        with open(out_path, "w") as f:
            json.dump(output, f, indent=2, default=str)
        print(f"  ✅ Kaydedildi: {out_path}")
    
    print("\n" + "="*80)
    print("  🎯 OPTİMİZASYON TAMAMLANDI")
    print("="*80)


if __name__ == "__main__":
    main()
