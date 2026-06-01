import pandas as pd
import numpy as np
import xgboost as xgb
import os
import json
from sklearn.model_selection import TimeSeriesSplit, GridSearchCV
from sklearn.metrics import accuracy_score, precision_score, classification_report

def load_data():
    features_dir = 'bot/engine/features'
    files = [f for f in os.listdir(features_dir) if f.endswith('.csv')]
    
    all_data = []
    for f in files:
        df = pd.read_csv(os.path.join(features_dir, f), parse_dates=['ts'])
        df.set_index('ts', inplace=True)
        # Sadece hedefin NaN olmadığı satırları al (son horizon barları hariç)
        df = df.dropna(subset=['target'])
        all_data.append(df)
        
    if not all_data:
        print("No feature data found!")
        return None
        
    # Zaman sırasına göre birleştir (Tarihsel sızıntıyı önlemek için)
    combined_df = pd.concat(all_data)
    combined_df.sort_index(inplace=True)
    return combined_df

def train_and_optimize():
    df = load_data()
    if df is None: return
    
    print(f"Total training samples: {len(df)}")
    
    # Hedef (Target) sütununu ayır
    y = df['target'].astype(int)
    X = df.drop(columns=['target', 'open', 'high', 'low', 'close', 'volume'])
    
    features = list(X.columns)
    print(f"Features used ({len(features)}): {features}")
    
    # Train / Test Ayrımı (%80 Train, %20 Test) zaman bazlı
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    
    print(f"Training on {len(X_train)} samples, testing on {len(X_test)} samples.")
    
    # XGBoost Modeli (Sınıf dengesizliğini çözmek için scale_pos_weight eklendi)
    scale_pos_weight = len(y_train[y_train == 0]) / len(y_train[y_train == 1])
    print(f"Calculated scale_pos_weight for imbalance: {scale_pos_weight:.2f}")
    
    model = xgb.XGBClassifier(
        objective='binary:logistic',
        eval_metric='logloss',
        use_label_encoder=False,
        scale_pos_weight=scale_pos_weight,
        tree_method='hist' # Daha hızlı eğitim için
    )
    
    # GridSearch ile Hiper-parametre Optimizasyonu
    param_grid = {
        'max_depth': [3, 5, 7],
        'learning_rate': [0.01, 0.05, 0.1],
        'n_estimators': [100, 200, 300],
        'subsample': [0.8, 0.9],
        'colsample_bytree': [0.8, 0.9]
    }
    
    # Zaman Serisi Çapraz Doğrulama (Gelecekten veri sızmasını önler)
    tscv = TimeSeriesSplit(n_splits=3)
    
    print("Starting Grid Search CV optimization... (This may take a few minutes)")
    grid_search = GridSearchCV(
        estimator=model,
        param_grid=param_grid,
        cv=tscv,
        scoring='precision', # Bizim için precision çok önemli (yanlış sinyal istemiyoruz)
        n_jobs=-1, # Tüm işlemci çekirdeklerini kullan
        verbose=1
    )
    
    grid_search.fit(X_train, y_train)
    
    print("\nBest Parameters found:")
    print(grid_search.best_params_)
    
    best_model = grid_search.best_estimator_
    
    # Test Verisi Üzerinde Değerlendirme
    y_pred = best_model.predict(X_test)
    y_prob = best_model.predict_proba(X_test)[:, 1]
    
    print("\nTest Set Evaluation:")
    print(classification_report(y_test, y_pred))
    print(f"Accuracy: {accuracy_score(y_test, y_pred):.4f}")
    print(f"Precision: {precision_score(y_test, y_pred):.4f}")
    
    # Özellik Önemini (Feature Importance) Kaydet
    importance = best_model.feature_importances_
    feature_imp = pd.DataFrame({'Feature': features, 'Importance': importance})
    feature_imp = feature_imp.sort_values(by='Importance', ascending=False)
    
    print("\nTop 10 Most Important Features:")
    print(feature_imp.head(10).to_string(index=False))
    
    # Modeli Kaydet
    model_path = "bot/engine/v23_xgb_model.json"
    best_model.save_model(model_path)
    print(f"\nModel saved to {model_path}")
    
    # Metadata Kaydet
    meta = {
        "features": features,
        "best_params": grid_search.best_params_,
        "metrics": {
            "accuracy": float(accuracy_score(y_test, y_pred)),
            "precision": float(precision_score(y_test, y_pred))
        }
    }
    with open("bot/engine/v23_xgb_meta.json", "w") as f:
        json.dump(meta, f, indent=4)
    print("Metadata saved to bot/engine/v23_xgb_meta.json")
    
    # Feature Importance Raporunu Metin Olarak Kaydet
    with open("bot/engine/v23_feature_importance.txt", "w") as f:
        f.write("V23 Ultimate AI Feature Importance\n")
        f.write("="*35 + "\n")
        f.write(feature_imp.to_string(index=False))

if __name__ == "__main__":
    train_and_optimize()
