#!/usr/bin/env python3
import os
import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, precision_score, classification_report, roc_auc_score

def main():
    print("="*60)
    print("  🧠 XGBoost MODEL EĞİTİMİ (Sinyal Keskinleştirme)")
    print("="*60)
    
    if not os.path.exists("ml_dataset.csv"):
        print("Hata: ml_dataset.csv bulunamadı. Önce feature_extractor.py çalıştırın.")
        return
        
    df = pd.read_csv("ml_dataset.csv")
    if df.empty:
        print("Hata: Veri seti boş.")
        return
        
    print(f"Toplam Sinyal Sayısı: {len(df)}")
    print(f"Kârlı Sinyaller (Label=1): {df['label'].sum()} (%{df['label'].mean()*100:.1f})")
    print(f"Zararlı Sinyaller (Label=0): {len(df) - df['label'].sum()}")
    
    # Define features and target
    features = [
        "comp_score", "is_bullish", "atr_pct", 
        "rsi", "macd_hist_norm", "vol_ratio", 
        "hour", "day_of_week"
    ]
    
    X = df[features]
    y = df["label"]
    
    # Chronological Split (No look-ahead bias)
    # We use 80% for training and 20% for testing
    split_idx = int(len(df) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    
    print(f"\nEğitim Seti (Train): {len(X_train)} sinyal")
    print(f"Test Seti (Test)   : {len(X_test)} sinyal")
    
    # Initialize XGBoost Classifier
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=3,
        learning_rate=0.05,
        objective="binary:logistic",
        eval_metric="auc",
        random_state=42
    )
    
    print("\nModel eğitiliyor...")
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
    
    # Predictions
    y_pred_proba = model.predict_proba(X_test)[:, 1]
    y_pred = (y_pred_proba > 0.60).astype(int) # Our threshold for "Keskinlik"
    
    acc = accuracy_score(y_test, y_pred)
    # To handle zero division if precision is undefined (no predicts > 0.60)
    try:
        prec = precision_score(y_test, y_pred, zero_division=0)
    except:
        prec = 0.0
    auc = roc_auc_score(y_test, y_pred_proba)
    
    print("\n" + "="*40)
    print("  📊 TEST SETİ PERFORMANSI (Prob > %60)")
    print("="*40)
    print(f"Accuracy (Doğruluk) : %{acc*100:.1f}")
    print(f"Precision (Keskinlik): %{prec*100:.1f}  <-- BOTUN YENİ WIN RATE'İ")
    print(f"ROC-AUC Skoru       : {auc:.3f}")
    
    # Calculate how many trades were accepted
    accepted = sum(y_pred)
    total_test = len(y_test)
    print(f"\nKabul Edilen İşlem  : {accepted} / {total_test} (%{accepted/total_test*100:.1f})")
    
    print("\nÖzellik Önemleri (Feature Importance):")
    importances = model.feature_importances_
    for feat, imp in sorted(zip(features, importances), key=lambda x: x[1], reverse=True):
        print(f"  - {feat:15s}: {imp:.3f}")
        
    # Save the model
    model.save_model("xgb_model.json")
    print("\n✅ Model başarıyla kaydedildi: xgb_model.json")

if __name__ == "__main__":
    main()
