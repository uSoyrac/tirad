#!/usr/bin/env python3
import os, sys, time, warnings
import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")

from realistic_limit_backtester import precalculate_signals, run_backtest_strategy, WARMUP
from dynamic_optimizer import run_orp_dynamic

COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]
TIMEFRAME = "4h"

def main():
    print("="*80)
    print("  🚀 4H MULTI-COIN PORTFÖY BACKTESTER (5 COİN) — SCALE-IN DCA")
    print("="*80)
    
    all_trades = []
    
    t0 = time.time()
    for i, coin in enumerate(COINS):
        print(f"\n  [{i+1}/{len(COINS)}] {coin}/USDT ({TIMEFRAME}) işleniyor...")
        csv_path = f"data/historical/{coin}_USDT_{TIMEFRAME}.csv"
        if not os.path.exists(csv_path):
            print("   Veri bulunamadı.")
            continue
            
        df = pd.read_csv(csv_path)
        if len(df) < WARMUP + 50:
            print("   Yetersiz veri.")
            continue
            
        df["ts"] = pd.to_datetime(df["ts"])
        df.set_index("ts", inplace=True)
        df = df.sort_index()
        # Ensure we have enough data (e.g. 2190 bars = 1 year 4H)
        df = df.tail(2190)
        
        print("   Precalculating signals...")
        signals = precalculate_signals(df)
        print(f"   Sinyal sayısı: {len(signals)}")
        
        # Test scale-in
        trades = run_backtest_strategy(coin, df, signals, strategy_type="scale_in")
        
        print(f"   Bulunan Scale-In işlemi: {len(trades)}")
        
        # We need to adapt trades format for ORP
        for t in trades:
            all_trades.append({
                "symbol": coin,
                "exit_ts": t["exit_date"],
                "r_mult": t["r_mult"] * t["size_mult"], # adjust for partial fill
                "sl_pct": t["sl_pct"]
            })
            
    elapsed = time.time() - t0
    
    print(f"\n\n  ✅ Tarama tamamlandı! ({elapsed:.1f}s)")
    print(f"  📊 Toplam İşlem (Portföy): {len(all_trades)}")
    
    if not all_trades:
        return
        
    wins = sum(1 for t in all_trades if t["r_mult"] > 0)
    wr = (wins / len(all_trades)) * 100
    avg_r = sum(t["r_mult"] for t in all_trades) / len(all_trades)
    
    print(f"  📈 Win Rate (WR)  : %{wr:.1f}")
    print(f"  📈 Ortalama Getiri : {avg_r:+.2f}R")
    
    # Sort trades chronologically
    all_trades.sort(key=lambda x: pd.to_datetime(x["exit_ts"]))
    
    # Run ORP using the new optimal parameters
    params = {
        "cycle_target_pct": 0.10,
        "recovery_factor": 1.0,
        "max_risk_cap": 0.20,
        "base_risk_pct": 0.04,
        "max_leverage": 10.0,
        "dynamic_recovery": False,
        "dd_scaling": False,
        "start_capital": 100.0
    }
    
    orp_res = run_orp_dynamic(all_trades, params)
    
    print("\n  🧠 ORP BİLEŞİK BÜYÜME SİMÜLASYONU (Optimal Parametreler)")
    print(f"     Başlangıç      : $100.00")
    print(f"     Bitiş ($)      : ${orp_res['final_eq']:,.2f} ({orp_res['total_growth']:.1f}x)")
    print(f"     Tamamlanan Adım: {orp_res['steps_achieved']}")
    print(f"     Max Drawdown   : %{orp_res['max_drawdown']:.1f}")
    print(f"     Batma          : {'EVET' if orp_res['wiped_out'] else 'HAYIR'}")
    
    print("\n" + "="*80)

if __name__ == "__main__":
    main()
