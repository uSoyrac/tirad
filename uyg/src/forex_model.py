import numpy as np
import pandas as pd
import lightgbm as lgb
from catboost import CatBoostClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import log_loss, roc_auc_score
import warnings

warnings.filterwarnings("ignore")

def train_ensemble_models(X_train, y_train, gap=100, n_splits=5):
    """
    Trains LightGBM and CatBoost models using Embargoed TimeSeriesSplit (gap=100) 
    to prevent target leakage across the 100-bar maximum hold time.
    """
    tscv = TimeSeriesSplit(n_splits=n_splits, gap=gap)
    
    # Base Hyperparameters
    lgb_params = {
        'objective': 'binary',
        'learning_rate': 0.05,
        'num_leaves': 15,
        'max_depth': 4,
        'verbose': -1,
        'random_state': 42
    }
    
    cat_params = {
        'iterations': 300,
        'learning_rate': 0.05,
        'depth': 4,
        'verbose': 0,
        'random_state': 42
    }

    print(f"Training LightGBM & CatBoost with TimeSeriesSplit (n_splits={n_splits}, gap={gap})...")
    
    best_lgb_auc = 0
    best_cat_auc = 0
    
    # We will just train on the full training set for the final model,
    # but let's use the last CV split to show validation metrics safely.
    for train_index, test_index in tscv.split(X_train):
        X_tr, X_val = X_train[train_index], X_train[test_index]
        y_tr, y_val = y_train[train_index], y_train[test_index]
        
        # Train LightGBM
        train_data = lgb.Dataset(X_tr, label=y_tr)
        val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)
        lgb_model = lgb.train(
            lgb_params, 
            train_data, 
            num_boost_round=300,
            valid_sets=[val_data],
            callbacks=[lgb.early_stopping(stopping_rounds=20, verbose=False)]
        )
        lgb_preds = lgb_model.predict(X_val)
        best_lgb_auc = roc_auc_score(y_val, lgb_preds)
        
        # Train CatBoost
        cat_model = CatBoostClassifier(**cat_params)
        cat_model.fit(X_tr, y_tr, eval_set=(X_val, y_val), early_stopping_rounds=20, verbose=False)
        cat_preds = cat_model.predict_proba(X_val)[:, 1]
        best_cat_auc = roc_auc_score(y_val, cat_preds)
        
    print(f"Validation AUC - LightGBM: {best_lgb_auc:.4f} | CatBoost: {best_cat_auc:.4f}")
    
    # Final models trained on entire X_train
    final_lgb = lgb.train(lgb_params, lgb.Dataset(X_train, label=y_train), num_boost_round=150)
    final_cat = CatBoostClassifier(**cat_params).fit(X_train, y_train, verbose=False)
    
    return final_lgb, final_cat

def predict_ensemble(final_lgb, final_cat, X_test):
    """Returns soft voting (average) probabilities of the ensemble."""
    lgb_probs = final_lgb.predict(X_test)
    cat_probs = final_cat.predict_proba(X_test)[:, 1]
    
    # 50/50 Soft Voting
    return (lgb_probs + cat_probs) / 2.0
