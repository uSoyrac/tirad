#!/usr/bin/env python3
"""
SABİT R/R (RİSK/ÖDÜL) PROP FIRM SİMÜLATÖRÜ VE AY-AY RAPOR (5K HESAP)
Bu simülatör Kelly formülünü devreden çıkarır ve sabit bir risk yönetimi uygular:
- Her işlemde %2 risk alınır (Zarar = -%2.28 maliyetlerle).
- Her kârlı işlemde +%4 kazanılır (Kâr = +%3.72 maliyetlerle).
- $36'lık standart kurallar geçerlidir (Phase 1: %8, Phase 2: %5, Günlük Limit: %5, Toplam: %10).
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

WIN_PCT = 0.0372   # +4% Kâr - %0.28 Komisyon/Slippage
LOSS_PCT = -0.0228 # -2% Zarar - %0.28 Komisyon/Slippage

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

def run_journey_rr(rows, P, gate_top=0.20, start_date_str="2024-12-01"):
    thr = np.quantile([P[i] for i in P], 1-gate_top)
    
    eq = START_BALANCE
    sodb = START_BALANCE
    current_day = None
    current_month = None
    
    phase = "PHASE_1"
    target = START_BALANCE * 1.08 # +%8 HEDEF
    
    status = "ONGOING"
    career_start = pd.Timestamp(start_date_str)
    
    # Aylık raporlama için değişkenler
    month_trades = 0
    month_wins = 0
    
    print("\n" + "="*70)
    print(f"🚀 {start_date_str} İTİBARIYLA 5K'LIK KARİYER BAŞLIYOR...")
    print("="*70)

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
        
        # Sabit R/R Kâr-Zarar Hesabı
        is_win = r["ret"] > 0
        if is_win:
            month_wins += 1
            eq *= (1 + WIN_PCT)
        else:
            eq *= (1 + LOSS_PCT)
            
        # İhlal Kontrolleri (-%5 Günlük Limit)
        # Zarar ettiğimiz an floating check'i yapmaya gerek yok, çünkü max float loss zaten loss pct kadar.
        # Fixed R/R'de max float = loss pct.
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

    if status == "ONGOING":
        print(f"✅ SİMÜLASYON TAMAMLANDI. Nihai Aşama: {phase}, Son Kasa: ${eq:,.2f}")
    
    print("="*70 + "\n")

def main():
    r_smart = pickle.load(open("/tmp/smartmoney_sigs.pkl", "rb"))
    p_smart = walk_forward_proba(r_smart)
    
    print(" 🏙️  SABİT R/R: $36'LIK STANDART FON AY-AY YOLCULUĞU 🏙️")
    
    # 2024 Aralık Kariyeri
    run_journey_rr(r_smart, p_smart, gate_top=0.20, start_date_str="2024-12-01")

if __name__ == "__main__":
    main()
