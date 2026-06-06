import pandas as pd
import numpy as np
import xgboost as xgb
import os
import json
from sklearn.model_selection import TimeSeriesSplit, GridSearchCV
from sklearn.metrics import accuracy_score, precision_score, classification_report

def load_data_v24():
    features_dir = 'bot/engine/features_v24'
    files = [f for f in os.listdir(features_dir) if f.endswith('.csv')]
    
    all_data = []
    for f in files:
        df = pd.read_csv(os.path.join(features_dir, f), parse_dates=['ts'])
        df.set_index('ts', inplace=True)
        df = df.dropna(subset=['target'])
        all_data.append(df)
        
    if not all_data:
        print("No feature data found!")
        return None
        
    combined_df = pd.concat(all_data)
    combined_df.sort_index(inplace=True)
    return combined_df

def train_and_optimize_v24():
    df = load_data_v24()
    if df is None: return
    
    print(f"Total training samples (1H data): {len(df)}")
    
    y = df['target'].astype(int)
    X = df.drop(columns=['target', 'open', 'high', 'low', 'close', 'volume'])
    
    features = list(X.columns)
    print(f"Features used ({len(features)}): {features}")
    
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    
    print(f"Training on {len(X_train)} samples, testing on {len(X_test)} samples.")
    
    scale_pos_weight = len(y_train[y_train == 0]) / len(y_train[y_train == 1])
    print(f"Calculated scale_pos_weight for imbalance: {scale_pos_weight:.2f}")
    
    model = xgb.XGBClassifier(
        objective='binary:logistic',
        eval_metric='logloss',
        use_label_encoder=False,
        scale_pos_weight=scale_pos_weight,
        tree_method='hist'
    )
    
    param_grid = {
        'max_depth': [3, 5],
        'learning_rate': [0.05, 0.1],
        'n_estimators': [100, 200],
        'subsample': [0.8, 0.9],
    }
    
    tscv = TimeSeriesSplit(n_splits=3)
    
    print("Starting Grid Search CV optimization for V24...")
    grid_search = GridSearchCV(
        estimator=model,
        param_grid=param_grid,
        cv=tscv,
        scoring='precision',
        n_jobs=-1,
        verbose=1
    )
    
    grid_search.fit(X_train, y_train)
    
    print("\nBest Parameters found:")
    print(grid_search.best_params_)
    
    best_model = grid_search.best_estimator_
    
    y_pred = best_model.predict(X_test)
    y_prob = best_model.predict_proba(X_test)[:, 1]
    
    print("\nTest Set Evaluation:")
    print(classification_report(y_test, y_pred))
    print(f"Accuracy: {accuracy_score(y_test, y_pred):.4f}")
    print(f"Precision: {precision_score(y_test, y_pred):.4f}")
    
    importance = best_model.feature_importances_
    feature_imp = pd.DataFrame({'Feature': features, 'Importance': importance})
    feature_imp = feature_imp.sort_values(by='Importance', ascending=False)
    
    print("\nTop 10 Most Important Features:")
    print(feature_imp.head(10).to_string(index=False))
    
    model_path = "bot/engine/v24_xgb_model.json"
    best_model.save_model(model_path)
    print(f"\nModel saved to {model_path}")
    
    meta = {
        "features": features,
        "best_params": grid_search.best_params_,
        "metrics": {
            "accuracy": float(accuracy_score(y_test, y_pred)),
            "precision": float(precision_score(y_test, y_pred))
        }
    }
    with open("bot/engine/v24_xgb_meta.json", "w") as f:
        json.dump(meta, f, indent=4)
    print("Metadata saved to bot/engine/v24_xgb_meta.json")

if __name__ == "__main__":
    train_and_optimize_v24()
