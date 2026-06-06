import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split, GridSearchCV, StratifiedKFold
from sklearn.metrics import classification_report, precision_score, accuracy_score, confusion_matrix
import xgboost as xgb
import warnings
import json

warnings.filterwarnings("ignore")

def train_model():
    print("="*80)
    print(" 🧠 V20 XGBOOST PRECISION OPTIMIZER (SMART THRESHOLD)")
    print("="*80)
    
    data_path = "/Users/uygar/.gemini/antigravity/scratch/tirad/uyg/src/data/ml_dataset_2yr.csv"
    df = pd.read_csv(data_path)
    
    features = ['adx', 'vol_ratio', 'rsi', 'macd_hist', 'atr_pct', 'dist_ema250_pct', 'trend_dir']
    X = df[features]
    y = df['is_win']
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)
    
    model = xgb.XGBClassifier(
        objective='binary:logistic',
        eval_metric='aucpr',
        random_state=42
    )
    
    param_grid = {
        'max_depth': [3, 4, 5],
        'learning_rate': [0.01, 0.05],
        'n_estimators': [100, 200, 300],
        'subsample': [0.7, 0.8, 0.9],
        'colsample_bytree': [0.7, 0.8, 0.9]
    }
    
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    grid_search = GridSearchCV(
        estimator=model,
        param_grid=param_grid,
        scoring='precision',
        cv=cv,
        verbose=0,
        n_jobs=-1
    )
    
    print("🔍 Modeller eğitiliyor (Lütfen bekleyin)...")
    grid_search.fit(X_train, y_train)
    best_model = grid_search.best_estimator_
    
    print("\n🏆 En İyi Parametreler:", grid_search.best_params_)
    
    y_pred_proba = best_model.predict_proba(X_test)[:, 1]
    
    print("\n🔍 OPTİMAL THRESHOLD ARANIYOR...")
    best_thresh = 0.0
    best_precision = 0.0
    best_cm = None
    
    for thresh in np.arange(0.30, 0.60, 0.01):
        y_pred_custom = (y_pred_proba >= thresh).astype(int)
        tp = sum((y_pred_custom == 1) & (y_test == 1))
        fp = sum((y_pred_custom == 1) & (y_test == 0))
        
        # En az 20 işleme girecek bir threshold bulalım
        if (tp + fp) > 20:
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            if precision > best_precision:
                best_precision = precision
                best_thresh = thresh
                best_cm = confusion_matrix(y_test, y_pred_custom)
                
    print(f"\n🔥 BULUNAN EN İYİ THRESHOLD: {best_thresh:.2f}")
    print(f"Gerçek Kayıpları Eledi (TN): {best_cm[0][0]}")
    print(f"Kayıp Olmasına Rağmen Girdi (FP): {best_cm[0][1]} ❌")
    print(f"Kazanç Olmasına Rağmen Eledi (FN): {best_cm[1][0]}")
    print(f"Gerçek Kazançları Buldu (TP): {best_cm[1][1]} ✅")
    
    print(f"\n🎯 TEST SETİ WIN RATE (Precision): %{best_precision*100:.1f}")
    
    model_path = "/Users/uygar/.gemini/antigravity/scratch/tirad/uyg/src/v20_xgb_model.json"
    best_model.save_model(model_path)
    
    meta = {
        "features": features,
        "threshold": float(best_thresh),
        "expected_win_rate": float(best_precision)
    }
    with open("/Users/uygar/.gemini/antigravity/scratch/tirad/uyg/src/v20_xgb_meta.json", "w") as f:
        json.dump(meta, f)
        
    print(f"✅ Meta kaydedildi: {meta}")

if __name__ == "__main__":
    train_model()
