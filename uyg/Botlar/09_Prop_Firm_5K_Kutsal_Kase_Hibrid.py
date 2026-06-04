#!/usr/bin/env python3
"""
HİBRİD MODEL PROP FIRM SİMÜLATÖRÜ (Stamina + Keskin R/R)
- Hesap: $5K, Daily DD: 5%, Max DD: 10%
- Her işlemde %1 Risk alınır (-%1 Kayıp).
- Her kârlı işlemde +%2 Kâr alınır (1:2 R/R).
- Kâr çekim eşikleri (100$ veya 250$) kullanılarak vur-kaç yapılır.
"""
import os, sys, pickle, numpy as np, pandas as pd, warnings
from datetime import datetime
warnings.filterwarnings("ignore")

sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))
import ta, xgboost as xgb

START_BALANCE = 5000.0
MAX_DAILY_DD_PCT = 0.05
MAX_TOTAL_DD_PCT = 0.10
MAX_TOTAL_DD_FLOOR = START_BALANCE * (1.0 - MAX_TOTAL_DD_PCT)

WIN_PCT = 0.02   # +%2 Kâr
LOSS_PCT = -0.01 # -%1 Zarar

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

def run_journey_hybrid(rows, P, gate_top=0.20, start_date_str="2024-12-01", payout_threshold=100):
    thr = np.quantile([P[i] for i in P], 1-gate_top)
    
    eq = START_BALANCE
    sodb = START_BALANCE
    current_day = None
    current_month = None
    
    phase = "PHASE_1"
    target = START_BALANCE * 1.08 # +%8 HEDEF
    
    total_payouts = 0.0
    payout_history = []
    
    status = "ONGOING"
    career_start = pd.Timestamp(start_date_str)
    
    # Aylık raporlama için değişkenler
    month_trades = 0
    month_wins = 0
    max_funded_eq = START_BALANCE

    for i, r in enumerate(rows):
        trade_date = r["et"]
        if trade_date < career_start: continue
        
        # Ay değişimi kontrolü ve Raporlama
        if current_month is None:
            current_month = trade_date.month
            
        elif current_month != trade_date.month:
            # Önceki ayın sonu raporu
            win_rate = (month_wins / month_trades * 100) if month_trades > 0 else 0
            print(f"🗓️  AY SONU RAPORU [{trade_date.year}-{current_month:02d}]:")
            print(f"    - Bulunulan Aşama : {phase}")
            print(f"    - Ay Sonu Bakiye  : ${eq:,.2f}")
            print(f"    - İşlem Sayısı    : {month_trades} (Kazanma Oranı: %{win_rate:.1f})")
            print("-" * 70)
            
            # Yeni ay sıfırlaması
            current_month = trade_date.month
            month_trades = 0
            month_wins = 0

        # Akıllı Kâr Çekimi (On-Demand Payout)
        if phase == "FUNDED":
            if eq > max_funded_eq: max_funded_eq = eq
            if eq >= START_BALANCE + payout_threshold:
                profit = eq - START_BALANCE
                trader_cut = profit * 0.80
                total_payouts += trader_cut
                payout_history.append((trade_date.date(), trader_cut))
                print(f"💰 VUR-KAÇ BAŞARILI! {trade_date.date()} tarihinde ${trader_cut:,.2f} nakit çekildi!")
                eq = START_BALANCE # Kasayı resetle
                sodb = START_BALANCE # SODB'u da resetle

        # İşlem tetiklenmiyor mu?
        if i not in P or P[i] < thr: continue
        
        # Gün Değişimi (Günlük Limit Sıfırlama)
        if current_day != trade_date.date():
            sodb = eq 
            current_day = trade_date.date()
            trades_today = 0
                
        if trades_today >= 1:
            continue # Günde max 1 işlem
            
        trades_today += 1
        month_trades += 1
        
        # Sabit R/R Kâr-Zarar Hesabı (-%1 / +%2)
        is_win = r["ret"] > 0
        if is_win:
            month_wins += 1
            eq *= (1 + WIN_PCT)
        else:
            eq *= (1 + LOSS_PCT)
            
        # İhlal Kontrolleri
        if eq < sodb * (1.0 - MAX_DAILY_DD_PCT):
            print(f"💥 BÜYÜK YIKIM: {trade_date.date()} tarihinde GÜNLÜK %5 LİMİTİ DELİNDİ! (Bakiye: ${eq:,.2f})")
            status = "FAILED"
            break
            
        if eq <= MAX_TOTAL_DD_FLOOR:
            print(f"💥 BÜYÜK YIKIM: {trade_date.date()} tarihinde TOPLAM %10 LİMİTİ DELİNDİ! (Bakiye: ${eq:,.2f})")
            status = "FAILED"
            break
             
        # Faz Geçişleri (Terfi)
        if phase == "PHASE_1" and eq >= target:
            print(f"🎉 TEBRİKLER! {trade_date.date()} - PHASE 1 GEÇİLDİ! (+%8 Vuruldu)")
            phase = "PHASE_2"
            target = START_BALANCE * 1.05 # Phase 2 hedefi +%5
            eq = START_BALANCE
            sodb = START_BALANCE
            
        elif phase == "PHASE_2" and eq >= target:
            print(f"🏆 MÜKEMMEL! {trade_date.date()} - PHASE 2 GEÇİLDİ! CANLI FONA (FUNDED) HAK KAZANILDI!")
            phase = "FUNDED"
            target = float('inf')
            eq = START_BALANCE
            sodb = START_BALANCE
            max_funded_eq = START_BALANCE

    if status == "ONGOING":
        # Simülasyon Bitişi (Kalan ufak kârı çek)
        if phase == "FUNDED" and eq > START_BALANCE:
            profit = eq - START_BALANCE
            trader_cut = profit * 0.80
            total_payouts += trader_cut
            payout_history.append(("FİNAL KAPANIŞ", trader_cut))
            print(f"💰 SİMÜLASYON BİTİŞİ! Kalan son nakit ${trader_cut:,.2f} çekildi!")
        print(f"✅ GÖREV TAMAMLANDI. Nihai Aşama: {phase}, Son Kasa: ${eq:,.2f}")
    
    return status, phase, total_payouts, payout_history, max_funded_eq

def main():
    r_smart = pickle.load(open("/tmp/smartmoney_sigs.pkl", "rb"))
    p_smart = walk_forward_proba(r_smart)
    
    thresholds = [100, 250]
    start_dates = ["2024-12-01", "2025-04-01"]
    
    print("="*85)
    print(" 🏙️  WALL STREET: HİBRİD (DÜŞÜK RİSK + KESKİN R/R) SİMÜLASYONU ($36'lık Fon) 🏙️")
    print("="*85)
    
    for start in start_dates:
        for th in thresholds:
            print(f"\n🚀 KARİYER BAŞLANGICI: {start} | SENARYO: +{th}$ Kâr Eşiği (Hedef: ${START_BALANCE + th:,.2f})")
            print("="*85)
            
            status, final_phase, total_payout, history, max_eq = run_journey_hybrid(
                r_smart, p_smart, gate_top=0.20, start_date_str=start, payout_threshold=th
            )
            
            print(f"\n📊 --- HİBRİD KARİYER ÖZETİ ---")
            print(f"  - Sonuç: {status}")
            if total_payout > 0:
                print("  - 💸 NAKİT ÇEKİMLERİ:")
                for date, amount in history:
                     print(f"      * {date} | Çekilen: ${amount:,.2f}")
                print(f"  - 💰 TOPLAM CEBE GİREN: ${total_payout:,.2f}")
            else:
                print(f"  - 💰 TOPLAM CEBE GİREN: $0.00 (Canlıdaki Max Bakiye: ${max_eq:,.2f})")
            print("="*85)

if __name__ == "__main__":
    main()
