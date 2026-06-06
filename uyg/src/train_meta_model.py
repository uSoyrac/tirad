#!/usr/bin/env python3
"""
train_meta_model.py — Meta-label modelini eğit + kaydet (üretim için)
Bot bunu yükleyip her aday trade'i skorlar. Periyodik yeniden eğitilmeli.
"""
import json, pickle, numpy as np, warnings
warnings.filterwarnings("ignore")
from sklearn.ensemble import HistGradientBoostingClassifier

FEATURES = ["rsi","macd_h","adx","atrp","vol_ratio","ema50d","ema200d","roc_s","roc_l","st_dir","dir","sl_dist"]
THRESHOLD = 0.35   # walk-forward'da en iyi başarı/robustluk dengesi
MODEL_PATH = "meta_model.pkl"

def main():
    import os
    if not os.path.exists("/tmp/meta_dataset.json"):
        from meta_label import build_dataset
        rows = build_dataset(); json.dump(rows, open("/tmp/meta_dataset.json","w"))
    else:
        rows = json.load(open("/tmp/meta_dataset.json"))
    X = np.array([[r.get(f,np.nan) for f in FEATURES] for r in rows], float)
    y = np.array([r["win"] for r in rows])
    clf = HistGradientBoostingClassifier(max_depth=3, max_iter=200, learning_rate=0.05,
            l2_regularization=1.0, min_samples_leaf=80, random_state=42)
    clf.fit(X, y)
    pickle.dump({"model": clf, "features": FEATURES, "threshold": THRESHOLD},
                open(MODEL_PATH, "wb"))
    # in-sample sanity (gerçek OOS meta_label.py'de ölçüldü: +0.068→+0.122R)
    proba = clf.predict_proba(X)[:,1]
    print(f"✅ {MODEL_PATH} kaydedildi | {len(rows)} trade ile eğitildi")
    print(f"   in-sample: tüm WR={y.mean()*100:.1f}%, proba≥{THRESHOLD} seçilen %{(proba>=THRESHOLD).mean()*100:.0f}")
    print(f"   (gerçek OOS lift meta_label.py'de doğrulandı: +0.068→+0.122R, 15/20 coin)")

if __name__ == "__main__":
    main()
