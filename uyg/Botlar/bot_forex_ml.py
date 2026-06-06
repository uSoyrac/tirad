import sys, os
import pandas as pd
import numpy as np

sys.path.insert(0, "/Users/uygar/trade/uyg/src")
sys.path.insert(0, "/Users/uygar/trade/uyg/Botlar")

import compound_engine as E
import forex_features as FF
import forex_model as FM
import _engine_path as B

# Enforce Forex settings globally
E.COINS = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X"]
E.TP = 0.005
E.SL = 0.0025
E.COST = 0.00015
E.FILE_SFX = ".csv"
E.DATA_DIR = "/Users/uygar/trade/uyg/src/mktdata_forex_4h"
E.OOS_START = "2024-08-01"  # 1 year train, ~2 years test for Forex

def build_advanced_dataset(rows, df_dict):
    """Combines signal rows with advanced HMM & Entropy features."""
    # First, calculate advanced features for all symbols
    adv_feats = {}
    for sym, df in df_dict.items():
        adv_feats[sym] = FF.compute_advanced_features(df)
        
    X_list, y_list, new_rows = [], [], []
    
    for r in rows:
        sym = r["c"]
        et = r["et"]
        
        # Get advanced features at entry time
        sym_df = adv_feats[sym]
        if et not in sym_df.index: continue
        
        row_feat = sym_df.loc[et]
        
        # Combine original XGBoost features with advanced features
        # Original: ['er', 'volr', 'atr', 'adx', 'rsi', 'macd', 'ret_20', 'ret_50']
        # Wait, the rows already have r["x"]. We can just append.
        orig_x = r["x"]
        
        # advanced: volatility_20, entropy_20, chop_20, log_ret
        adv_x = np.array([
            row_feat['volatility_20'],
            row_feat['entropy_20'],
            row_feat['chop_20'],
            row_feat['log_ret']
        ])
        
        final_x = np.concatenate([orig_x, adv_x])
        X_list.append(final_x)
        y_list.append(r["win"])
        
        # Store advanced features in the row dict for backtesting
        r_new = r.copy()
        r_new["adv_x"] = final_x
        r_new["volatility_20"] = row_feat['volatility_20']
        r_new["log_ret"] = row_feat['log_ret']
        new_rows.append(r_new)
        
    return np.array(X_list), np.array(y_list), new_rows

def backtest_hmm_ensemble(rows, P_ensemble, HMM_states, volatile_state, bankroll=10000.0, gate=0.20):
    """
    Backtests the ML ensemble with HMM Regime filtering.
    Prop-firm baseline: $10,000 starting capital.
    """
    keep = np.array([P_ensemble[i] for i in P_ensemble])
    if len(keep) == 0:
        return dict(eq=bankroll, cagr=0, mdd=0, n=0, wr=0)
        
    thr = np.quantile(keep, 1-gate)
    passed = keep[keep >= thr]
    lo, hi = np.quantile(passed, 0.40), np.quantile(passed, 0.80)
    
    eq = bankroll
    peak = bankroll
    mdd = 0.0
    free = pd.Timestamp("2000")
    trades = []
    
    for i, r in enumerate(rows):
        if str(r["et"]) < E.OOS_START or i not in P_ensemble or P_ensemble[i] < thr or r["et"] < free: 
            continue
            
        prob = P_ensemble[i]
        regime = HMM_states[i]
        
        # Dynamic Sizing Base (Kelly approach)
        if prob < lo: 
            nt = 0.6
        elif prob < hi: 
            nt = 1.25
        else: 
            nt = 2.5
            
        # HMM REGIME OVERRIDE
        # If the market is in a Whipsaw (High Volatility) regime, cut sizing significantly!
        if regime == volatile_state:
            nt *= 0.25  # 75% risk reduction during pure noise
            
        eq *= (1 + nt*(r["ret"] - E.COST))
        free = r["xt"]
        
        peak = max(peak, eq)
        mdd = max(mdd, (peak-eq)/peak if peak>0 else 0)
        trades.append(r["win"])
        
        if eq <= 0: break
        
    if len(trades) == 0:
        return dict(eq=bankroll, cagr=0, mdd=0, n=0, wr=0)
        
    yrs = max(1e-9, (pd.Timestamp(str(rows[-1]["xt"])) - pd.Timestamp(E.OOS_START)).days / 365.25)
    cagr = ((eq/bankroll)**(1/yrs) - 1) * 100 if eq > 0 else -100
    
    return dict(eq=eq, cagr=cagr, mdd=mdd*100, n=len(trades), wr=np.mean(trades)*100, lo=lo, hi=hi)

def run_pipeline():
    print("1. Loading Forex data & generating base signals...")
    # Load all data into a dict for advanced feature calculation
    df_dict = {}
    for sym in E.COINS:
        df = pd.read_csv(os.path.join(E.DATA_DIR, f"{sym}{E.FILE_SFX}"), parse_dates=["ts"]).set_index("ts").sort_index()
        df_dict[sym] = df
        
    rows = E.build_signals(cache="/tmp/forex_ml_sigs.pkl")
    
    print("2. Computing Advanced ML4T Features (Entropy, Choppiness)...")
    X, y, adv_rows = build_advanced_dataset(rows, df_dict)
    
    # Split into train and test based on OOS_START
    train_idx = [i for i, r in enumerate(adv_rows) if str(r["et"]) < E.OOS_START]
    test_idx = [i for i, r in enumerate(adv_rows) if str(r["et"]) >= E.OOS_START]
    
    if len(train_idx) == 0 or len(test_idx) == 0:
        print("Not enough data to split.")
        return
        
    X_train, y_train = X[train_idx], y[train_idx]
    X_test = X[test_idx]
    
    print("3. Training HMM for Unsupervised Regime Detection...")
    # We train HMM on the training data's log_ret and volatility
    hmm_train_data = pd.DataFrame([{'log_ret': adv_rows[i]['log_ret'], 'volatility_20': adv_rows[i]['volatility_20']} for i in train_idx])
    hmm_model, _, vol_state, calm_state = FF.train_hmm_regimes(hmm_train_data, n_components=2)
    print(f"HMM trained. Volatile State ID: {vol_state}, Calm State ID: {calm_state}")
    
    # Predict HMM states for all rows
    all_hmm_data = pd.DataFrame([{'log_ret': r['log_ret'], 'volatility_20': r['volatility_20']} for r in adv_rows]).values
    all_hmm_states = hmm_model.predict(all_hmm_data)
    
    print("4. Training LightGBM & CatBoost Ensemble with Purged CV...")
    final_lgb, final_cat = FM.train_ensemble_models(X_train, y_train, gap=100, n_splits=5)
    
    print("5. Generating Predictions...")
    P_ensemble_test = FM.predict_ensemble(final_lgb, final_cat, X_test)
    
    # Map back to rows
    P_dict = {}
    for idx_in_test, original_row_idx in enumerate(test_idx):
        P_dict[original_row_idx] = P_ensemble_test[idx_in_test]
        
    print("\n6. Running Backtest ($10,000 Prop-Firm Capital)...")
    # Base Ensemble (Without HMM)
    res_base = backtest_hmm_ensemble(adv_rows, P_dict, all_hmm_states, volatile_state=-1, bankroll=10000.0)
    
    # HMM Shield Ensemble
    res_hmm = backtest_hmm_ensemble(adv_rows, P_dict, all_hmm_states, volatile_state=vol_state, bankroll=10000.0)
    
    print("="*60)
    print("  SONUÇLAR: ML4T FOREX YZ SİSTEMİ")
    print("="*60)
    print("--- SADECE ENSEMBLE (LightGBM + CatBoost) ---")
    print(f"Bakiye: ${res_base['eq']:.2f} | CAGR: %{res_base['cagr']:.1f} | MaxDD: %{res_base['mdd']:.1f} | WR: %{res_base['wr']:.1f}")
    
    print("\n--- ENSEMBLE + HMM REGIME SHIELD (Whipsaw Koruması) ---")
    print(f"Bakiye: ${res_hmm['eq']:.2f} | CAGR: %{res_hmm['cagr']:.1f} | MaxDD: %{res_hmm['mdd']:.1f} | WR: %{res_hmm['wr']:.1f}")
    print("============================================================")

if __name__ == "__main__":
    run_pipeline()
