#!/usr/bin/env python3
"""
ÖZEL 5K PROP FIRM SİMÜLATÖRÜ (3% Daily DD, 6% Max DD)
Bu simülatör, görseldeki spesifik şartlara göre uyarlanmıştır:
- Kasa: $5.000
- Hedefler: %6 Phase 1, %6 Phase 2
- Max Daily DD: -%3 (Çok Tehlikeli!)
- Max Total DD: -%6
- Güvenlik: max_kelly_lev = 0.8 olarak kısıtlandı.
"""
import os, sys, pickle, numpy as np, pandas as pd, warnings
from datetime import datetime
warnings.filterwarnings("ignore")

sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))
import ta, xgboost as xgb

COST = 0.0028 # HARDCORE
START_BALANCE = 5000.0
MAX_DAILY_DD_PCT = 0.03 # GÖRSELDEKİ -%3 ŞARTI
MAX_TOTAL_DD_PCT = 0.06 # GÖRSELDEKİ -%6 ŞARTI
MAX_TOTAL_DD_FLOOR = START_BALANCE * (1.0 - MAX_TOTAL_DD_PCT)

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

def run_journey(rows, P, gate_top=0.20, start_date_str="2024-12-01", max_kelly_lev=0.8, payout_threshold=None):
    thr=np.quantile([P[i] for i in P], 1-gate_top)
    
    eq = START_BALANCE
    sodb = START_BALANCE
    current_day = None
    
    phase = "PHASE_1"
    target = START_BALANCE * 1.06 # +%6 HEDEF
    
    total_payouts = 0.0
    payout_history = []
    
    status = "ONGOING"
    career_start = pd.Timestamp(start_date_str)
    
    for i,r in enumerate(rows):
        trade_date = r["et"]
        if trade_date < career_start: continue
        
        # Akıllı Kâr Çekimi (On-Demand Payout)
        if phase == "FUNDED":
            if not hasattr(run_journey, 'max_funded_eq'): run_journey.max_funded_eq = START_BALANCE
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
        
        # Kâr Tamponu (Drawdown Koruması - Daraltılmış Sınırlar İçin)
        if eq < START_BALANCE * 0.98: # %2 eksideyse (Zaten %6 limit var, %2 çok tehlikeli)
            lev *= 0.5
        if eq < START_BALANCE * 0.96: # %4 eksideyse (Uçurumun tam kenarı)
            lev *= 0.25 
            
        # Hardcore Floating Drawdown (-%2 Wick DD + Cost)
        worst_floating_g = lev * (-0.025 - COST) if r["ret"] < 0 else lev * (-0.02 - COST)
        floating_eq = eq * (1 + worst_floating_g)
        
        # İhlal Kontrolleri (-%3 Günlük Limit)
        if floating_eq < sodb * (1.0 - MAX_DAILY_DD_PCT):
            status = f"BÜYÜK YIKIM: {phase}'de Günlük DD Limitine Çarpıldı! (Kasa: ${floating_eq:,.2f})"
            break
            
        if floating_eq <= MAX_TOTAL_DD_FLOOR:
            status = f"BÜYÜK YIKIM: {phase}'de Toplam DD Limitine Çarpıldı! (Kasa: ${floating_eq:,.2f})"
            break
            
        # İşlem Kapanışı
        g = lev * (r["ret"] - COST)
        eq *= (1 + g)
        
        if eq <= MAX_TOTAL_DD_FLOOR:
             status = f"BÜYÜK YIKIM: {phase}'de Toplam DD Limitine Çarpıldı! (Kasa: ${eq:,.2f})"
             break
             
        # Faz Geçişleri (Terfi)
        if phase == "PHASE_1" and eq >= target:
            phase = "PHASE_2"
            target = START_BALANCE * 1.06 # Phase 2 hedefi de +%6
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
        
    return status, phase, total_payouts, payout_history

def main():
    r_smart = pickle.load(open("/tmp/smartmoney_sigs.pkl", "rb"))
    p_smart = walk_forward_proba(r_smart)
    
    thresholds = [100, 250] # 5K hesap için 100$ veya 250$ kâr çekim senaryoları
    start_dates = ["2024-12-01", "2025-04-01"] # Kariyer başlangıçları
    
    print("="*85)
    print(" 🏙️  WALL STREET: 5K ÖZEL PROP FIRM (3% DAILY DD) SİMÜLASYONU 🏙️")
    print("="*85)
    
    for start in start_dates:
        print(f"\n🚀 KARİYER BAŞLANGICI: {start}")
        for th in thresholds:
            print(f"  --- SENARYO: +{th}$ Kâr Eşiği (Hedef: ${START_BALANCE + th:,.2f}) ---")
            
            run_journey.max_funded_eq = START_BALANCE
            status, final_phase, total_payout, history = run_journey(
                r_smart, p_smart, gate_top=0.20, start_date_str=start, 
                max_kelly_lev=0.8, payout_threshold=th
            )
            
            print(f"  Sonuç: {status}")
            if total_payout > 0:
                print("  💸 NAKİT ÇEKİMLERİ:")
                for date, amount in history:
                     print(f"    - Tarih: {date} | Çekilen: ${amount:,.2f}")
                print(f"  💰 TOPLAM CEBE GİREN: ${total_payout:,.2f}")
            else:
                max_reached = run_journey.max_funded_eq if hasattr(run_journey, 'max_funded_eq') else START_BALANCE
                print(f"  💰 TOPLAM CEBE GİREN: $0.00 (Canlıdaki Max Bakiye: ${max_reached:,.2f})")
            print("  " + "-"*50)
    print("="*85)

if __name__ == "__main__":
    main()
