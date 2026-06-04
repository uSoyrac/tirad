#!/usr/bin/env python3
"""
THE ULTIMATE HARVEST TOURNAMENT
Elimizdeki tüm bot felsefelerinin (Klasik, Kelly, Sniper, Scalp) 
"Maaş Çekme (Harvest)" hedefine koşturulduğu devasa simülasyon.
"""
import os, sys, pickle, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")

sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))
import ta, xgboost as xgb

OOS_START = "2024-01-01"
COST = 0.0018

def walk_forward_proba(rows, test_years=("2024","2025","2026")):
    P={}
    for y in test_years:
        tr=[r for r in rows if str(r["et"])[:4]<y]; te=[r for r in rows if str(r["et"])[:4]==y]
        if len(tr)<300 or not te: continue
        clf=xgb.XGBClassifier(n_estimators=250,max_depth=4,learning_rate=0.05,subsample=0.8,
            colsample_bytree=0.8,eval_metric="logloss",random_state=42).fit(
            np.array([r["x"] for r in tr]), np.array([r["win"] for r in tr]))
        for i,r in enumerate(rows):
            if str(r["et"])[:4]==y: P[i]=float(clf.predict_proba(np.array([r["x"]]))[:,1][0])
    return P

def backtest_fixed(rows, P, gate_top, leverage, target, start_bank=100.0):
    thr=np.quantile([P[i] for i in P], 1-gate_top)
    eq = start_bank
    harvested = 0.0
    bankruptcies = 0
    free = pd.Timestamp("2000")
    for i,r in enumerate(rows):
        if str(r["et"])<OOS_START or i not in P or P[i]<thr or r["et"]<free: continue
        g = leverage * (r["ret"] - COST)
        eq *= (1 + g)
        free = r["xt"]
        if eq >= target:
            harvested += (eq - start_bank)
            eq = start_bank
        elif eq <= 0:
            bankruptcies += 1
            eq = start_bank
    return harvested, bankruptcies

def backtest_kelly(rows, P, gate_top, max_lev, target, start_bank=100.0):
    thr=np.quantile([P[i] for i in P], 1-gate_top)
    eq = start_bank
    harvested = 0.0
    bankruptcies = 0
    free = pd.Timestamp("2000")
    for i,r in enumerate(rows):
        if str(r["et"])<OOS_START or i not in P or P[i]<thr or r["et"]<free: continue
        prob = P[i]
        kf = max(0.1, prob - ((1.0 - prob)/2.0))
        lev = min(max_lev, kf * 15.0)
        g = lev * (r["ret"] - COST)
        eq *= (1 + g)
        free = r["xt"]
        if eq >= target:
            harvested += (eq - start_bank)
            eq = start_bank
        elif eq <= 0:
            bankruptcies += 1
            eq = start_bank
    return harvested, bankruptcies

def main():
    print("="*75)
    print("  BÜYÜK HASAT (HARVEST) TURNUVASI BAŞLIYOR... (2024-2026)")
    print("="*75)
    print("Veriler yükleniyor (Saniyeler sürecek)...")
    
    # 1. Klasik (Smart Money) Sinyalleri
    r_smart = pickle.load(open("/tmp/smartmoney_sigs.pkl", "rb"))
    p_smart = walk_forward_proba(r_smart)
    
    # 2. Sniper Sinyalleri
    r_sniper = pickle.load(open("/tmp/sniper_sigs.pkl", "rb"))
    p_sniper = walk_forward_proba(r_sniper)
    
    # 3. Scalp Sinyalleri
    r_scalp = pickle.load(open("/tmp/scalp_harvest_sigs.pkl", "rb"))
    p_scalp = walk_forward_proba(r_scalp)
    
    print("Tüm stratejiler aynı 'Maaş Çekme' hedefine koşturuluyor...\n")
    
    results = []
    # --- MODEL 1: Klasik Güvenli Hasat (Bot 02) ---
    h1, b1 = backtest_fixed(r_smart, p_smart, gate_top=0.20, leverage=3.0, target=120.0)
    results.append(("1. Klasik Güvenli Hasat (Sabit 3x)", h1, b1))
    
    # --- MODEL 2: Dinamik Kelly Hasat (Bot 05 - En Optimal) ---
    h2, b2 = backtest_kelly(r_smart, p_smart, gate_top=0.20, max_lev=10.0, target=150.0)
    results.append(("2. Dinamik Kelly Hasat (Yapay Zeka 1x-10x)", h2, b2))
    
    # --- MODEL 3: Asimetrik Sniper Hasat (Bot 04 - Arşiv) ---
    h3, b3 = backtest_fixed(r_sniper, p_sniper, gate_top=0.05, leverage=5.0, target=150.0)
    results.append(("3. Asimetrik Sniper Hasat (1'e 5 Risk)", h3, b3))
    
    # --- MODEL 4: Yüksek Frekanslı Scalp Hasat ---
    h4, b4 = backtest_fixed(r_scalp, p_scalp, gate_top=0.20, leverage=5.0, target=110.0)
    results.append(("4. Yüksek Frekanslı Scalp Hasat (Komisyon Ezilmesi)", h4, b4))
    
    # Sonuçları kâra göre sırala
    results.sort(key=lambda x: x[1], reverse=True)
    
    print(f"{'STRATEJİ ADI':<50} | {'TOPLAM MAAŞ (KÂR)':<20} | {'İFLAS SAYISI'}")
    print("-" * 90)
    for name, h, b in results:
        star = "🏆 ŞAMPİYON!" if name == results[0][0] else ""
        print(f"{name:<50} | ${h:<19.2f} | {b} {star}")
    print("-" * 90)

if __name__ == "__main__":
    main()
