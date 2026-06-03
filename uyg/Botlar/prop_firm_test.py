#!/usr/bin/env python3
"""
PROP FIRM (FTMO) ROLLING MONTHS SIMULATOR
Her ayın başında yeni bir 100k'lık sınava girilir. Bakalım Kelly Botumuz hangi aylarda geçip hangi aylarda takılıyor?
"""
import os, sys, pickle, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
from datetime import datetime
from dateutil.relativedelta import relativedelta

sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))
import ta, xgboost as xgb

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

def run_exam_for_month(rows, P, gate_top, start_date_str, max_kelly_lev=1.5):
    thr=np.quantile([P[i] for i in P], 1-gate_top)
    
    eq = START_BALANCE
    sodb = START_BALANCE
    current_day = None
    
    exam_start_date = pd.Timestamp(start_date_str)
    # Prop firm exams usually have a 30 day limit for Phase 1, though FTMO removed it.
    # Let's see if it passes within 60 days.
    exam_end_date = exam_start_date + pd.Timedelta(days=60) 
    
    status = "ONGOING (Time Limit)"
    days_taken = 0
    first_trade_date = None
    trades_today = 0
    
    for i,r in enumerate(rows):
        trade_date = r["et"]
        if trade_date < exam_start_date: continue
        if trade_date > exam_end_date: break
        if i not in P or P[i]<thr: continue
        
        if first_trade_date is None: first_trade_date = trade_date.date()
        
        if current_day != trade_date.date():
            sodb = eq 
            current_day = trade_date.date()
            trades_today = 0
            if first_trade_date is not None:
                days_taken = (current_day - first_trade_date).days
                
        if trades_today >= 1:
            continue # Günlük 1 işlem kotası (Concurrency Limit)
            
        trades_today += 1
                
        prob = P[i]
        kf = max(0.1, prob - ((1.0 - prob)/2.0))
        lev = min(max_kelly_lev, kf * 15.0)
        
        # Dinamik Kâr Tamponu (Eğer toplam kasa eksideyse riskleri çok sert daralt)
        if eq < START_BALANCE * 0.98:
            lev *= 0.5
        if eq < START_BALANCE * 0.95:
            lev *= 0.25 # Uçurumun kenarında mini risk
            
        worst_floating_g = lev * (-0.025 - COST) if r["ret"] < 0 else lev * (-COST)
        floating_eq = eq * (1 + worst_floating_g)
        
        if floating_eq < sodb * (1.0 - MAX_DAILY_DD_PCT):
            status = "FAILED: Daily DD (-5%)"
            eq = floating_eq
            days_taken = (trade_date.date() - first_trade_date).days
            break
            
        if floating_eq < MAX_TOTAL_DD_FLOOR:
            status = "FAILED: Total DD (-10%)"
            eq = floating_eq
            days_taken = (trade_date.date() - first_trade_date).days
            break
            
        g = lev * (r["ret"] - COST)
        eq *= (1 + g)
        
        if eq < MAX_TOTAL_DD_FLOOR:
             status = "FAILED: Total DD (-10%)"
             days_taken = (trade_date.date() - first_trade_date).days
             break
             
        if eq >= TARGET_PROFIT:
            status = "PASSED: Target (+8%)"
            days_taken = (trade_date.date() - first_trade_date).days
            break
            
    return status, eq, days_taken

def main():
    print("="*80)
    print("  KAPSAMLI PROP FIRM TESTİ: ROLLING MONTHS (Kelly Max 1.5x)")
    print("="*80)
    
    r_smart = pickle.load(open("/tmp/smartmoney_sigs.pkl", "rb"))
    p_smart = walk_forward_proba(r_smart)
    
    start_date = datetime(2024, 10, 1)
    end_date = datetime(2026, 5, 1) # Son 20 Ay
    
    current_test_date = start_date
    results = []
    
    passed_count = 0
    failed_count = 0
    
    while current_test_date <= end_date:
        date_str = current_test_date.strftime("%Y-%m-01")
        st, eq, d = run_exam_for_month(r_smart, p_smart, gate_top=0.20, start_date_str=date_str, max_kelly_lev=1.5)
        results.append((date_str, st, eq, d))
        if "PASSED" in st: passed_count += 1
        elif "FAILED" in st: failed_count += 1
        
        current_test_date += relativedelta(months=1)
        
    print(f"{'SINAV AYI':<15} | {'DURUM':<30} | {'SÜRE':<10} | {'SON BAKİYE'}")
    print("-" * 80)
    for date_str, st, eq, d in results:
        marker = "🏆" if "PASSED" in st else "❌" if "FAILED" in st else "⏳"
        print(f"{date_str:<15} | {st:<30} | {d:<4} Gün   | ${eq:,.2f} {marker}")
        
    print("=" * 80)
    print(f"TOPLAM SINAV SAYISI: {len(results)}")
    print(f"GEÇİLEN SINAV      : {passed_count}")
    print(f"KALINAN SINAV      : {failed_count}")
    print(f"ZAMANA TAKILAN     : {len(results) - passed_count - failed_count}")
    print("=" * 80)

if __name__ == "__main__":
    main()
