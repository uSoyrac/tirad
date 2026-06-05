#!/usr/bin/env python3
"""train_meta_v2.py — v2+vov feature setiyle production meta-modeli eğit+kaydet."""
import json, pickle, numpy as np, warnings
warnings.filterwarnings("ignore")
from sklearn.ensemble import HistGradientBoostingClassifier
from meta_features_v2 import build_v2, FEATURES_V2, wf_lift

THRESHOLD = 0.35
def main():
    import os
    if os.path.exists("/tmp/meta_dataset_v2vov.json"):
        rows = json.load(open("/tmp/meta_dataset_v2vov.json"))
    else:
        rows = build_v2(); json.dump(rows, open("/tmp/meta_dataset_v2vov.json","w"))
    # OOS lift doğrula (kaydetmeden önce)
    r = wf_lift(rows, FEATURES_V2)
    print(f"v2+vov walk-forward OOS: base {r['base_e']:+.3f}R → meta {r['sel_e']:+.3f}R (N={r['sel_n']}, {r['pos']}/{r['tot']} coin+)")
    X = np.array([[row.get(f,np.nan) for f in FEATURES_V2] for row in rows], float)
    y = np.array([row["win"] for row in rows])
    clf = HistGradientBoostingClassifier(max_depth=3, max_iter=200, learning_rate=0.05,
            l2_regularization=1.0, min_samples_leaf=80, random_state=42)
    clf.fit(X, y)
    pickle.dump({"model": clf, "features": FEATURES_V2, "threshold": THRESHOLD}, open("meta_model_v2.pkl","wb"))
    print(f"✅ meta_model_v2.pkl ({len(FEATURES_V2)} feature, {len(rows)} trade)")

if __name__ == "__main__":
    main()
