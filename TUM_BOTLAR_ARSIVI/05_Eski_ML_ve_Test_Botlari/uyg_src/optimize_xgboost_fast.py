import os
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from sklearn.metrics import make_scorer, precision_score, accuracy_score
import warnings
warnings.filterwarnings("ignore")

dataset_path = "/Users/uygar/.gemini/antigravity/scratch/tirad/uyg/src/ml_dataset_12m.csv"
df = pd.read_csv(dataset_path)

features = ["comp_score", "is_bullish", "atr_pct", "rsi", "macd_hist_norm", "vol_ratio"]
X = df[features]
y = df["label"]

split_idx = int(len(df) * 0.8)
X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

param_grid = {
    'max_depth': [2],
    'learning_rate': [0.01, 0.05],
    'n_estimators': [50, 100],
    'subsample': [0.8],
    'colsample_bytree': [0.8]
}

tscv = TimeSeriesSplit(n_splits=3)
precision_scorer = make_scorer(precision_score, zero_division=0)
base_model = xgb.XGBClassifier(objective="binary:logistic", random_state=42)

grid_search = GridSearchCV(
    estimator=base_model,
    param_grid=param_grid,
    scoring=precision_scorer,
    cv=tscv,
    n_jobs=-1
)
grid_search.fit(X_train, y_train)

best_model = grid_search.best_estimator_
y_pred_proba = best_model.predict_proba(X_test)[:, 1]
y_pred = (y_pred_proba > 0.65).astype(int) # EŞİĞİ 0.65'e ÇEKTİK

prec = precision_score(y_test, y_pred, zero_division=0)
acc = accuracy_score(y_test, y_pred)

print(f"Accuracy: %{acc*100:.1f}")
print(f"STRICT TimeSeriesPrecision (Prob > 0.65): %{prec*100:.1f}")

model_path = "/Users/uygar/.gemini/antigravity/scratch/tirad/ilk_bot/optimal_xgb_model.json"
best_model.save_model(model_path)
print("Model Kaydedildi.")
