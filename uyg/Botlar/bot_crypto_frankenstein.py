#!/usr/bin/env python3
import sys, os
import pandas as pd
import numpy as np

sys.path.insert(0, "/Users/uygar/trade/uyg/src")
sys.path.insert(0, "/Users/uygar/trade/uyg/Botlar")

import compound_engine as E
import forex_features as FF
import bot_optimal

# ENFORCE CRYPTO SETTINGS
E.COINS = ["BTC", "ETH", "BNB", "SOL", "XRP"]
E.TP = 0.05
E.SL = 0.025
E.COST = 0.001
E.FILE_SFX = "_USDT_1h.csv"
E.DATA_DIR = "/Users/uygar/trade/uyg/src/mktdata_1h"
E.OOS_START = "2024-01-01"

def backtest_frankenstein_crypto(rows, P, df_dict, bankroll=250.0, gate=0.20):
    print("Training HMM for Crypto Regime Shielding...")
    
    hmm_data_list = []
    for sym, df in df_dict.items():
        feat_df = FF.compute_advanced_features(df)
        hmm_data_list.append(feat_df)
    
    full_feat_df = pd.concat(hmm_data_list).dropna()
    hmm_model, _, vol_state, calm_state = FF.train_hmm_regimes(full_feat_df, n_components=2)
    print(f"HMM Trained. Volatile/Whipsaw State ID: {vol_state}")

    feat_lookup = {}
    for sym, df in df_dict.items():
        feat_lookup[sym] = FF.compute_advanced_features(df)

    keep = np.array([P[i] for i in P])
    if len(keep) == 0: return dict()
    
    thr = np.quantile(keep, 1-gate)
    passed = keep[keep >= thr]
    lo, hi = np.quantile(passed, 0.40), np.quantile(passed, 0.80)
    
    eq = bankroll
    peak = bankroll
    mdd = 0.0
    free = pd.Timestamp("2000")
    trades = []
    shield_activations = 0
    
    for i, r in enumerate(rows):
        if str(r["et"]) < E.OOS_START or i not in P or P[i] < thr or r["et"] < free: 
            continue
            
        sym = r["c"]
        et = r["et"]
        sym_feat = feat_lookup[sym]
        
        if et in sym_feat.index:
            recent = sym_feat.loc[:et]
            regime = FF.predict_hmm_regime(hmm_model, recent)
        else:
            regime = -1
        
        prob = P[i]
        nt = bot_optimal.confidence_notional(prob, lo, hi)
        
        # FRANKENSTEIN SHIELD: If HMM detects noise regime, cut risk
        if regime == vol_state:
            nt *= 0.25
            shield_activations += 1
            
        eq *= (1 + nt*(r["ret"] - E.COST))
        free = r["xt"]
        
        peak = max(peak, eq)
        mdd = max(mdd, (peak-eq)/peak if peak>0 else 0)
        trades.append(r["win"])
        
        if eq <= 0: break
        
    yrs = max(1e-9, (pd.Timestamp(str(rows[-1]["xt"])) - pd.Timestamp(E.OOS_START)).days / 365.25)
    cagr = ((eq/bankroll)**(1/yrs) - 1) * 100 if eq > 0 else -100
    
    return dict(eq=eq, cagr=cagr, mdd=mdd*100, n=len(trades), wr=np.mean(trades)*100, 
                shield_acts=shield_activations)

def main():
    print("="*60)
    print("  CRYPTO FRANKENSTEIN BOT (Bot Optimal + ML4T HMM)")
    print("="*60)
    
    df_dict = {}
    for sym in E.COINS:
        df = pd.read_csv(os.path.join(E.DATA_DIR, f"{sym}{E.FILE_SFX}"), parse_dates=["ts"]).set_index("ts").sort_index()
        df_dict[sym] = df
        
    print("1. Loading Crypto signals & running XGBoost Walk-Forward...")
    cache_path = "/tmp/crypto_frankenstein_sigs.pkl"
    if os.path.exists(cache_path):
        os.remove(cache_path)
        
    rows = E.build_signals(cache=cache_path)
    P = E.walk_forward_proba(rows)
    
    print("2. Running Base XGBoost (Bot Optimal) for Comparison...")
    bot_opt_res = bot_optimal.backtest_confidence(rows, P, bankroll=250.0, gate=0.20)
    
    print("3. Running Crypto Frankenstein (HMM Shielded)...")
    frank_res = backtest_frankenstein_crypto(rows, P, df_dict, bankroll=250.0, gate=0.20)
    
    print("\n" + "="*60)
    print("  KARSILASTIRMA SONUCLARI ($250 Baslangic - 2024/2026)")
    print("="*60)
    print("--- 1. BOT OPTIMAL (XGBoost Sadece) ---")
    print(f"Bakiye: ${bot_opt_res['eq']:.2f} | CAGR: %{bot_opt_res['cagr']:.1f} | MaxDD: %{bot_opt_res['mdd']:.1f} | İSLEM: {bot_opt_res['n']}")
    
    print("\n--- 2. CRYPTO FRANKENSTEIN (XGBoost + HMM Kalkanı) ---")
    print(f"Bakiye: ${frank_res['eq']:.2f} | CAGR: %{frank_res['cagr']:.1f} | MaxDD: %{frank_res['mdd']:.1f} | İSLEM: {frank_res['n']}")
    print(f"Kalkan Aktifleşme Sayısı (Gürültü Koruması): {frank_res['shield_acts']}")
    print("============================================================")

if __name__ == "__main__":
    main()
