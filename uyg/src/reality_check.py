#!/usr/bin/env python3
"""
REALITY CHECK — Tirad sisteminin GERÇEK Win Rate ve ORP dayanıklılık doğrulaması.

Amaç: AGENT.md / README'deki "%65" ve simulate_orp_math.py'deki hardcoded "%75"
iddialarını, hayal değil, ELDEKİ GERÇEK VERİ (ml_dataset_12m.csv) ile sınamak.

Çıktı:
  1) Veri setindeki ham (base) win rate.
  2) XGBoost'un 0.60 eşiğinde GERÇEK precision'ı (= botun gerçek Win Rate'i),
     kronolojik hold-out + zaman serisi cross-validation ile.
  3) Bu gerçek WR ile ORP'nin ardışık-stop dayanıklılığı (3/4/5 üst üste stop)
     ve Monte Carlo ile iflas (ruin) olasılığı.

Bu dosya MEVCUT KODA DOKUNMAZ. Sadece okur ve raporlar.
"""
import os
import sys
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from sklearn.metrics import precision_score

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HERE)
from dynamic_optimizer import run_orp_dynamic

DATA = os.path.join(HERE, "ml_dataset_12m.csv")
FEATURES = ["comp_score", "is_bullish", "atr_pct", "rsi", "macd_hist_norm", "vol_ratio"]
THRESHOLD = 0.60  # AGENT.md: ASLA esnetme


def wilson_ci(k, n, z=1.96):
    """Bir oranın Wilson %95 güven aralığı (küçük örneklem için dürüst belirsizlik)."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = (z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def section(t):
    print("\n" + "=" * 64)
    print(" " + t)
    print("=" * 64)


def step1_base_rate(df):
    section("1) HAM VERİ — Filtresiz Win Rate (SMC sinyalinin ham hali)")
    n = len(df)
    w = int(df.label.sum())
    lo, hi = wilson_ci(w, n)
    print(f"Toplam sinyal      : {n}")
    print(f"Kazanan (label=1)  : {w}  ->  Ham WR = %{100*w/n:.1f}")
    print(f"%95 Güven Aralığı  : %{100*lo:.1f} – %{100*hi:.1f}")
    print("Not: AGENT.md klasik SMC'yi ~%30-45 WR diye anlatıyor; ham orana bak.")
    return w / n


def step2_real_winrate(df):
    section("2) XGBoost GERÇEK Win Rate (0.60 eşik, kronolojik hold-out)")
    X, y = df[FEATURES], df["label"]
    split = int(len(df) * 0.8)
    Xtr, Xte = X.iloc[:split], X.iloc[split:]
    ytr, yte = y.iloc[:split], y.iloc[split:]

    param_grid = {
        "max_depth": [2, 3],            # AGENT.md: overfit'e karşı <=3
        "learning_rate": [0.01, 0.05, 0.1],
        "n_estimators": [50, 100, 200],
        "subsample": [0.8, 1.0],
        "colsample_bytree": [0.8, 1.0],
    }
    gs = GridSearchCV(
        xgb.XGBClassifier(objective="binary:logistic", random_state=42, eval_metric="logloss"),
        param_grid,
        scoring="precision",
        cv=TimeSeriesSplit(n_splits=4),  # look-ahead bias YOK
        n_jobs=-1,
    )
    gs.fit(Xtr, ytr)
    best = gs.best_estimator_
    print(f"En iyi parametreler: {gs.best_params_}")

    proba = best.predict_proba(Xte)[:, 1]
    taken = proba >= THRESHOLD
    n_taken = int(taken.sum())
    if n_taken == 0:
        print("UYARI: Hold-out'ta 0.60 eşiğini geçen işlem YOK. WR ölçülemez.")
        return None, best
    real_wr = precision_score(yte, taken.astype(int), zero_division=0)
    wins = int(yte[taken].sum())
    lo, hi = wilson_ci(wins, n_taken)
    print(f"Hold-out işlem     : {len(yte)}")
    print(f"Eşiği geçen (alınan): {n_taken}  (%{100*n_taken/len(yte):.0f} seçicilik)")
    print(f"GERÇEK Win Rate    : %{100*real_wr:.1f}  ({wins}/{n_taken} kazandı)")
    print(f"%95 Güven Aralığı  : %{100*lo:.1f} – %{100*hi:.1f}")
    print(">>> DİKKAT: hold-out örneklemi küçükse bu WR gürültülüdür; CI'ya bak.")
    return real_wr, best


def step3_orp_durability(real_wr):
    section("3) ORP DAYANIKLILIK — Gerçek WR ile en kötü senaryolar")
    if real_wr is None:
        real_wr = 0.55
        print("(Ölçülemediği için temkinli %55 ile devam ediliyor.)")

    base_params = {
        "cycle_target_pct": 0.10,
        "recovery_factor": 1.0,
        "max_risk_cap": 0.20,
        "base_risk_pct": 0.04,
        "max_leverage": 10.0,
        "dynamic_recovery": False,
        "dd_scaling": False,
        "start_capital": 100.0,
    }

    # --- 3a) "3 kere üst üste stop olursa ne olur?" (en kötü an, başta) ---
    print("\n-- 3a) Soğuk başlangıç: ardışık N stop ($100, 5% SL, R=-1) --")
    for n_loss in (3, 4, 5):
        trades = [{"r_mult": -1.0, "sl_pct": 5.0} for _ in range(n_loss)]
        res = run_orp_dynamic(trades, base_params)
        eq = res["final_eq"]
        print(f"   {n_loss} üst üste stop -> kasa ${eq:6.2f}  "
              f"(düşüş %{100*(1-eq/100):.1f}, maxDD %{res['max_drawdown']:.1f})")

    # --- 3b) Monte Carlo: gerçek WR ile iflas olasılığı ---
    print(f"\n-- 3b) Monte Carlo (WR=%{100*real_wr:.0f}, R kazanç=+2, 60 işlem/çeyrek) --")
    rng = np.random.default_rng(7)
    N = 5000
    finals, ruined, dds = [], 0, []
    for _ in range(N):
        outs = rng.random(60) < real_wr
        trades = [{"r_mult": 2.0 if w else -1.0, "sl_pct": 5.0} for w in outs]
        res = run_orp_dynamic(trades, base_params)
        finals.append(res["final_eq"])
        dds.append(res["max_drawdown"])
        if res["final_eq"] <= 1.0:
            ruined += 1
    finals = np.array(finals)
    print(f"   Medyan kasa  : ${np.median(finals):,.0f}")
    print(f"   Ortalama kasa: ${finals.mean():,.0f}  (ortalama yanıltıcı; medyana bak)")
    print(f"   %10 kötü dilim (P10): ${np.percentile(finals,10):,.0f}")
    print(f"   %90 iyi dilim (P90) : ${np.percentile(finals,90):,.0f}")
    print(f"   Ortalama maxDD     : %{np.mean(dds):.1f}")
    print(f"   İFLAS OLASILIĞI    : %{100*ruined/N:.2f}  ({ruined}/{N})")
    print("\nYorum: iflas olasılığı >%1 ise ORP 'risksiz' DEĞİLDİR; "
          "recovery_factor / max_risk_cap gözden geçirilmeli.")


def main():
    if not os.path.exists(DATA):
        print(f"Veri yok: {DATA}")
        return
    df = pd.read_csv(DATA)
    print(f"Yüklendi: {len(df)} satır, {DATA}")
    step1_base_rate(df)
    real_wr, _ = step2_real_winrate(df)
    step3_orp_durability(real_wr)
    section("ÖZET")
    print("Yukarıdaki sayılar ELDEKİ 12 aylık veriden hesaplandı (hayal değil).")
    print("Canlı veri (Binance/CMC) bu konteynerde allowlist dışı olduğundan,")
    print("güncel veriyle tekrar üretim VPS/yerel ortamda yapılmalı.")


if __name__ == "__main__":
    main()
