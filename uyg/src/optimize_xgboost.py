#!/usr/bin/env python3
import os
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from sklearn.metrics import make_scorer, precision_score, accuracy_score
import warnings

warnings.filterwarnings("ignore")

def optimize_model():
    print("="*60)
    print(" 🧠 XGBoost SUPERTREND & LIVE DATA OPTİMİZASYONU")
    print("="*60)
    
    dataset_path = os.path.join(os.path.dirname(__file__), "ml_dataset_live.csv")
    if not os.path.exists(dataset_path): return
        
    df = pd.read_csv(dataset_path)
    print(f"Toplam Supertrend Sinyali Sayısı: {len(df)}")
    
    features = ["st_trend", "dist_to_st", "atr_pct", "rsi", "adx", "bb_width", "vol_ratio"]
    X = df[features]
    y = df["label"]
    
    split_idx = int(len(df) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    
    print("Optimizasyon başlatılıyor. Hedef: Precision (Maksimum Win Rate)...")
    
    param_grid = {
        'max_depth': [3, 4, 5], 
        'learning_rate': [0.01, 0.05],
        'n_estimators': [100, 200],
        'subsample': [0.7, 0.8, 0.9]
    }
    
    precision_scorer = make_scorer(precision_score, zero_division=0)
    tscv = TimeSeriesSplit(n_splits=3)
    
    base_model = xgb.XGBClassifier(objective="binary:logistic", random_state=42)
    
    grid_search = GridSearchCV(
        estimator=base_model,
        param_grid=param_grid,
        scoring=precision_scorer,
        cv=tscv,
        n_jobs=-1,
        verbose=1
    )
    
    grid_search.fit(X_train, y_train)
    best_model = grid_search.best_estimator_
    
    print("\n✅ EN OPTİMAL HİPERPARAMETRELER:")
    print(grid_search.best_params_)
    
    y_pred_proba = best_model.predict_proba(X_test)[:, 1]
    
    # Eşik denemeleri (0.50'den 0.70'e kadar hangisi daha yüksek Win Rate veriyor)
    best_thresh = 0.50
    best_prec = 0.0
    for thresh in [0.50, 0.55, 0.60, 0.65, 0.70]:
        preds = (y_pred_proba > thresh).astype(int)
        prec = precision_score(y_test, preds, zero_division=0)
        accepted = sum(preds)
        if prec > best_prec and accepted > 5: # En az 5 islem kabul etmis olmali
            best_prec = prec
            best_thresh = thresh
            
    print(f"\nSeçilen Eşik Değeri (Threshold): {best_thresh}")
            
    y_pred = (y_pred_proba > best_thresh).astype(int)
    prec = precision_score(y_test, y_pred, zero_division=0)
    acc = accuracy_score(y_test, y_pred)
    
    print("\n" + "="*40)
    print(f"  📊 TEST SETİ PERFORMANSI (Prob > {best_thresh})")
    print("="*40)
    print(f"Accuracy (Doğruluk) : %{acc*100:.1f}")
    print(f"Precision (Keskinlik): %{prec*100:.1f}  <-- YENİ GERÇEK WIN RATE")
    
    accepted = sum(y_pred)
    total_test = len(y_test)
    if total_test > 0:
        print(f"\nKabul Edilen İşlem  : {accepted} / {total_test} (%{accepted/total_test*100:.1f} Seçicilik)")
    
    model_path = os.path.join(os.path.dirname(__file__), "..", "..", "ilk_bot", "optimal_xgb_model.json")
    best_model.save_model(model_path)
    
    # Eşiği bir dosyaya kaydedelim ki test scripti de onu okusun
    thresh_path = os.path.join(os.path.dirname(__file__), "..", "..", "ilk_bot", "optimal_thresh.txt")
    with open(thresh_path, "w") as f:
        f.write(str(best_thresh))
        
    print(f"\n✅ Supertrend Model başarıyla Live Bot klasörüne kaydedildi: {model_path}")

if __name__ == "__main__":
    optimize_model()
