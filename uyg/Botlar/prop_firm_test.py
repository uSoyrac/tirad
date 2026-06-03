#!/usr/bin/env python3
"""
PROP FIRM (FTMO / FUNDING PIPS) EVALUATION SIMULATOR
Hedef: $100.000 sanal bakiyeyi, kuralları ihlal etmeden %8 kârla ($108.000) tamamlamak.

KURALLAR:
1. Max Daily Drawdown: Kasa, o günkü başlangıç bakiyesinin %5'inden fazla düşemez.
2. Max Total Drawdown: Kasa, başlangıç sermayesinin (100k) %10'undan fazla düşemez (90.000 altı yasak).
"""
import os, sys, pickle, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")

sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))
import ta, xgboost as xgb

OOS_START = "2024-01-01"
COST = 0.0018

START_BALANCE = 100000.0
TARGET_PROFIT = 108000.0
MAX_DAILY_DD_PCT = 0.05
MAX_TOTAL_DD_FLOOR = 90000.0

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

def backtest_prop_firm(rows, P, gate_top, strategy_type="kelly", fixed_lev=5.0, max_kelly_lev=10.0):
    thr=np.quantile([P[i] for i in P], 1-gate_top)
    
    eq = START_BALANCE
    sodb = START_BALANCE  # Start of Day Balance
    current_day = None
    
    free = pd.Timestamp("2000")
    status = "ONGOING"
    days_taken = 0
    first_trade_date = None
    
    for i,r in enumerate(rows):
        if str(r["et"])<OOS_START or i not in P or P[i]<thr or r["et"]<free: continue
        
        trade_date = r["et"]
        if first_trade_date is None: first_trade_date = trade_date.date()
        
        # Gün Değişimi Kontrolü
        if current_day != trade_date.date():
            sodb = eq  # Yeni günün başlangıç bakiyesi
            current_day = trade_date.date()
            if first_trade_date is not None:
                days_taken = (current_day - first_trade_date).days
                
        # Leverage Hesaplama
        if strategy_type == "kelly":
            prob = P[i]
            kf = max(0.1, prob - ((1.0 - prob)/2.0))
            lev = min(max_kelly_lev, kf * 15.0)
        else:
            lev = fixed_lev
            
        # Trade Uygulama (Gün İçi)
        # Prop firmalarında işlem anındaki Floating Zarar da DD'yi tetikler.
        # Bu yüzden işlemin en kötü anını (SL vurmasını) da simüle etmeliyiz.
        # R["ret"] stop olmuşsa zaten en kötü andır. Kâr etmişse stopa değmemiş demektir.
        
        worst_floating_g = lev * (-0.025 - COST) if r["ret"] < 0 else lev * (-COST) # Basit bir floating DD yaklaşımı
        if strategy_type == "sniper":
             worst_floating_g = lev * (-0.02 - COST) if r["ret"] < 0 else lev * (-COST)
             
        floating_eq = eq * (1 + worst_floating_g)
        
        # Günlük DD İhlali Kontrolü
        if floating_eq < sodb * (1.0 - MAX_DAILY_DD_PCT):
            status = "FAILED: Daily Drawdown Limit Reached (-5%)"
            eq = floating_eq
            days_taken = (trade_date.date() - first_trade_date).days
            break
            
        # Toplam DD İhlali Kontrolü
        if floating_eq < MAX_TOTAL_DD_FLOOR:
            status = "FAILED: Max Total Drawdown Limit Reached (-10%)"
            eq = floating_eq
            days_taken = (trade_date.date() - first_trade_date).days
            break
            
        # Kapanış Gerçekleşmesi
        g = lev * (r["ret"] - COST)
        eq *= (1 + g)
        free = r["xt"]
        
        # Gün sonu kârı da Toplam DD'yi ihlal etmiş mi?
        if eq < MAX_TOTAL_DD_FLOOR:
             status = "FAILED: Max Total Drawdown Limit Reached (-10%)"
             days_taken = (trade_date.date() - first_trade_date).days
             break
             
        # Hedef Kontrolü
        if eq >= TARGET_PROFIT:
            status = "PASSED: Target Reached (+8%)"
            days_taken = (trade_date.date() - first_trade_date).days
            break
            
    return status, eq, days_taken

def main():
    print("="*75)
    print("  PROP FIRM (FTMO) SINAV SİMÜLASYONU BAŞLIYOR... ($100.000 Hesap)")
    print("="*75)
    print("Veriler yükleniyor...")
    
    # Sinyaller
    r_smart = pickle.load(open("/tmp/smartmoney_sigs.pkl", "rb"))
    p_smart = walk_forward_proba(r_smart)
    
    r_sniper = pickle.load(open("/tmp/sniper_sigs.pkl", "rb"))
    p_sniper = walk_forward_proba(r_sniper)
    
    results = []
    
    # 1. 05 Nolu Kelly Botu (Max 10x Lev)
    status_k, eq_k, days_k = backtest_prop_firm(r_smart, p_smart, gate_top=0.20, strategy_type="kelly", max_kelly_lev=10.0)
    results.append(("Dinamik Kelly (Max 10x)", status_k, eq_k, days_k))
    
    # 2. 05 Nolu Kelly Botu (Max 1.5x Lev - PROP FIRM SAFE)
    status_k_safe, eq_k_safe, days_k_safe = backtest_prop_firm(r_smart, p_smart, gate_top=0.20, strategy_type="kelly", max_kelly_lev=1.5)
    results.append(("Dinamik Kelly (Max 1.5x - Prop Safe)", status_k_safe, eq_k_safe, days_k_safe))
    
    # 3. 01 Nolu Sniper Botu (Sabit 5x Lev)
    status_s, eq_s, days_s = backtest_prop_firm(r_sniper, p_sniper, gate_top=0.05, strategy_type="sniper", fixed_lev=5.0)
    results.append(("Asimetrik Sniper (Sabit 5x)", status_s, eq_s, days_s))
    
    print("\nSONUÇLAR:")
    print("-" * 80)
    for name, st, eq, d in results:
        print(f"BOT    : {name}")
        print(f"BAKİYE : ${eq:,.2f}")
        print(f"SÜRE   : {d} Gün")
        print(f"DURUM  : {st}")
        print("-" * 80)

if __name__ == "__main__":
    main()
