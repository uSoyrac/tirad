#!/usr/bin/env python3
"""
NİHAİ PROP FIRM KARİYER SİMÜLATÖRÜ (3-PHASE JOURNEY)
Gerçek bir trader'ın prop firmasındaki ömrünü simüle eder.
- Phase 1: +8% Hedef
- Phase 2: +5% Hedef
- Funded: Hedef yok, ay sonu kârın %80'ini (Payout) çek.
* Hardcore (0.0028) maliyetler ve Wick DD (-%2) her zaman aktiftir.
"""
import os, sys, pickle, numpy as np, pandas as pd, warnings
from datetime import datetime
warnings.filterwarnings("ignore")

sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))
import ta, xgboost as xgb

COST = 0.0028 # HARDCORE
START_BALANCE = 100000.0
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

def run_journey(rows, P, gate_top=0.20, start_date_str="2024-12-01", max_kelly_lev=1.5, payout_threshold=None):
    thr=np.quantile([P[i] for i in P], 1-gate_top)
    
    eq = START_BALANCE
    sodb = START_BALANCE
    current_day = None
    
    phase = "PHASE_1"
    target = START_BALANCE * 1.08
    
    total_payouts = 0.0
    payout_history = []
    
    status = "ONGOING"
    career_start = pd.Timestamp(start_date_str)
    
    for i,r in enumerate(rows):
        trade_date = r["et"]
        if trade_date < career_start: continue
        
        # Akıllı Kâr Çekimi (On-Demand Payout)
        if phase == "FUNDED":
            if not hasattr(run_journey, 'max_funded_eq'): run_journey.max_funded_eq = 100000
            if eq > run_journey.max_funded_eq: run_journey.max_funded_eq = eq
            
            if payout_threshold is not None and eq >= START_BALANCE + payout_threshold:
                profit = eq - START_BALANCE
                trader_cut = profit * 0.80
                total_payouts += trader_cut
                payout_history.append((trade_date.date(), trader_cut))
                eq = START_BALANCE # Kasayı resetle
                sodb = START_BALANCE # SODB'u da resetle

        if i not in P or P[i]<thr: continue
        
        if current_day != trade_date.date():
            sodb = eq 
            current_day = trade_date.date()
            trades_today = 0
                
        if trades_today >= 1:
            continue # Günlük 1 işlem kotası
            
        trades_today += 1
                
        prob = P[i]
        kf = max(0.1, prob - ((1.0 - prob)/2.0))
        lev = min(max_kelly_lev, kf * 15.0)
        
        # Kâr Tamponu (Drawdown Koruması)
        if eq < START_BALANCE * 0.98:
            lev *= 0.5
        if eq < START_BALANCE * 0.95:
            lev *= 0.25 
            
        # Hardcore Floating Drawdown (-%2 Wick DD + Cost)
        worst_floating_g = lev * (-0.025 - COST) if r["ret"] < 0 else lev * (-0.02 - COST)
        floating_eq = eq * (1 + worst_floating_g)
        
        # İhlal Kontrolleri
        if floating_eq < sodb * (1.0 - MAX_DAILY_DD_PCT):
            status = f"BÜYÜK YIKIM: {phase}'de Günlük DD Limitine Çarpıldı!"
            break
            
        if floating_eq < MAX_TOTAL_DD_FLOOR:
            status = f"BÜYÜK YIKIM: {phase}'de Toplam DD Limitine Çarpıldı!"
            break
            
        # İşlem Kapanışı
        g = lev * (r["ret"] - COST)
        eq *= (1 + g)
        
        if eq < MAX_TOTAL_DD_FLOOR:
             status = f"BÜYÜK YIKIM: {phase}'de Toplam DD Limitine Çarpıldı!"
             break
             
        # Faz Geçişleri (Terfi)
        if phase == "PHASE_1" and eq >= target:
            phase = "PHASE_2"
            target = START_BALANCE * 1.05
            eq = START_BALANCE
            sodb = START_BALANCE
            
        elif phase == "PHASE_2" and eq >= target:
            phase = "FUNDED"
            target = float('inf')
            eq = START_BALANCE
            sodb = START_BALANCE

    # Simülasyon Bitişi (Kalan ufak kârı çek)
    if phase == "FUNDED" and "YIKIM" not in status and eq > START_BALANCE:
        profit = eq - START_BALANCE
        trader_cut = profit * 0.80
        total_payouts += trader_cut
        payout_history.append(("FİNAL KAPANIŞ", trader_cut))
        status = "GÖREV TAMAMLANDI"
        
    if hasattr(run_journey, 'max_funded_eq'):
        print(f"DEBUG: Max Funded Equity Reached = {run_journey.max_funded_eq}")
        
    return status, phase, total_payouts, payout_history

def main():
    r_smart = pickle.load(open("/tmp/smartmoney_sigs.pkl", "rb"))
    p_smart = walk_forward_proba(r_smart)
    
    thresholds = [1000, 2000]
    start_dates = ["2025-04-01", "2025-06-01", "2025-09-01"] # Son 12 aydaki farklı başlangıç senaryoları
    
    print("="*85)
    print(" 🏙️  WALL STREET: AKILLI KÂR ÇEKİMİ (ON-DEMAND PAYOUT) SİMÜLASYONU 🏙️")
    print("="*85)
    
    for start in start_dates:
        print(f"\n🚀 KARİYER BAŞLANGICI: {start}")
        for th in thresholds:
            print(f"  --- SENARYO: +{th}$ Kâr Eşiği (Hedef: {START_BALANCE + th}$) ---")
            
            run_journey.max_funded_eq = 100000
            status, final_phase, total_payout, history = run_journey(
                r_smart, p_smart, gate_top=0.20, start_date_str=start, 
                max_kelly_lev=1.5, payout_threshold=th
            )
            
            print(f"  Sonuç: {status}")
            if total_payout > 0:
                print("  💸 NAKİT ÇEKİMLERİ:")
                for date, amount in history:
                     print(f"    - {date} | Çekilen: ${amount:,.2f}")
                print(f"  💰 TOPLAM CEBE GİREN: ${total_payout:,.2f}")
            else:
                print(f"  💰 TOPLAM CEBE GİREN: $0.00 (Max Bakiye: ${run_journey.max_funded_eq:,.2f})")
            print("  " + "-"*50)
    print("="*85)

if __name__ == "__main__":
    main()
