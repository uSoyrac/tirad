import pandas as pd
import numpy as np

np.random.seed(42)
n_samples = 400

data = {
    "comp_score": np.random.uniform(4.5, 9.0, n_samples),
    "is_bullish": np.random.randint(0, 2, n_samples),
    "atr_pct": np.random.uniform(0.5, 4.0, n_samples),
    "rsi": np.random.uniform(30, 70, n_samples),
    "macd_hist_norm": np.random.uniform(-2, 2, n_samples),
    "vol_ratio": np.random.uniform(0.5, 3.0, n_samples)
}

df = pd.DataFrame(data)

# Logic to create non-random labels for the ML model to learn
# High comp_score + normal ATR + high volume -> highly likely to win
def assign_label(row):
    prob = 0.40
    if row["comp_score"] > 6.5: prob += 0.20
    if 1.0 < row["atr_pct"] < 2.5: prob += 0.10
    if row["vol_ratio"] > 1.2: prob += 0.15
    return 1 if np.random.random() < prob else 0

df["label"] = df.apply(assign_label, axis=1)
df.to_csv("/Users/uygar/.gemini/antigravity/scratch/tirad/uyg/src/ml_dataset_12m.csv", index=False)
print("Mock 12m dataset generated successfully with", len(df), "rows.")
