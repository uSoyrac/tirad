#!/usr/bin/env python3
import os
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import GridSearchCV, train_test_split
from sklearn.metrics import make_scorer, precision_score, accuracy_score, classification_report
import warnings

warnings.filterwarnings("ignore")

def optimize_model():
    print("="*60)
    print(" 🧠 XGBoost HIPERPARAMETRE OPTIMIZASYONU (GRID SEARCH)")
    print("="*60)
    
    if not os.path.exists("ml_dataset_12m.csv"):
        print("Hata: ml_dataset_12m.csv bulunamadı.")
        return
        
    df = pd.read_csv("ml_dataset_12m.csv")
    if df.empty:
        print("Hata: Veri seti boş.")
        return
        
    print(f"Toplam Veri Sayısı: {len(df)}")
    
    # Feature columns based on the builder
    features = ["comp_score", "is_bullish", "atr_pct", "rsi", "macd_hist_norm", "vol_ratio"]
    X = df[features]
    y = df["label"]
    
    # Split data chronologically to prevent look-ahead bias
    split_idx = int(len(df) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    
    print("Optimizasyon başlatılıyor. Lütfen bekleyin (Bu işlem biraz sürebilir)...")
    
    # Define hyperparameter grid
    param_grid = {
        'max_depth': [2, 3, 4],
        'learning_rate': [0.01, 0.05, 0.1],
        'n_estimators': [50, 100, 200],
        'subsample': [0.8, 1.0],
        'colsample_bytree': [0.8, 1.0]
    }
    
    # Our primary goal is HIGH PRECISION (When it predicts 1, it should truly be 1)
    precision_scorer = make_scorer(precision_score, zero_division=0)
    
    base_model = xgb.XGBClassifier(objective="binary:logistic", random_state=42)
    
    # Perform Grid Search
    grid_search = GridSearchCV(
        estimator=base_model,
        param_grid=param_grid,
        scoring=precision_scorer,
        cv=3,
        n_jobs=-1,
        verbose=1
    )
    
    grid_search.fit(X_train, y_train)
    
    best_model = grid_search.best_estimator_
    print("\n✅ EN OPTİMAL HİPERPARAMETRELER BULUNDU:")
    print(grid_search.best_params_)
    
    # Test on the hold-out test set
    y_pred_proba = best_model.predict_proba(X_test)[:, 1]
    y_pred = (y_pred_proba > 0.60).astype(int) # Sıkı filtre
    
    prec = precision_score(y_test, y_pred, zero_division=0)
    acc = accuracy_score(y_test, y_pred)
    
    print("\n" + "="*40)
    print("  📊 TEST SETİ PERFORMANSI (Prob > %60)")
    print("="*40)
    print(f"Accuracy (Doğruluk) : %{acc*100:.1f}")
    print(f"Precision (Keskinlik): %{prec*100:.1f}  <-- BOTUN YENİ WIN RATE'İ")
    
    accepted = sum(y_pred)
    total_test = len(y_test)
    print(f"\nKabul Edilen İşlem  : {accepted} / {total_test} (%{accepted/total_test*100:.1f} Seçicilik)")
    
    # Save the absolute best model
    model_path = os.path.join("..", "..", "ilk_bot", "optimal_xgb_model.json")
    best_model.save_model(model_path)
    print(f"\n✅ Model başarıyla Live Bot klasörüne kaydedildi: {model_path}")

if __name__ == "__main__":
    optimize_model()
