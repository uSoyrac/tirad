#!/usr/bin/env python3
"""
EMIR — XGBoost'u GERÇEK veriyle eğit (GitHub Actions, canlı internet).

Mock (np.random.seed=42) veriyi ÇÖPE atar. Bunun yerine:
  1) Canlı borsadan (Binance->Bybit->OKX) gerçek 4H veri çeker (anahtarsız).
  2) Takımın GERÇEK SMC motoru `score_slice_v2` ile feature üretir
     (comp_score, is_bullish, atr_pct, rsi, macd_hist_norm, vol_ratio) — canlı
     botun beklediği 6 feature ile birebir aynı (vectorized_dataset_builder mantığı).
  3) İleriye-bakan gerçek label üretir (limit dolumu + TP/SL, get_label).
  4) XGBoost'u KRONOLOJİK eğitir (look-ahead yok), GridSearch (precision,
     max_depth<=3 -> overfit kalkanı), 0.60 eşiğinde GERÇEK WR + Wilson CI ölçer.
  5) Çıktıları yazar: emir/ml_dataset_real.csv, emir/optimal_xgb_real.json,
     emir/xgb_real_report.md  (CI bunları repoya geri commit eder).

ML_HANDOVER_GUIDE kuralları: 0.60 eşiği SABİT, max_depth<=3.
"""
import os
import sys
import argparse
import datetime as dt
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "uyg", "src")
sys.path.insert(0, SRC)
sys.path.insert(0, HERE)

import warnings
warnings.filterwarnings("ignore")

from fetch_and_backtest import fetch_any, COINS          # anahtarsız canlı veri
from backtest_multi_tf import score_slice_v2, WARMUP, _trend_1d  # GERÇEK SMC motoru
import ta

THRESHOLD = 0.60   # ML_HANDOVER_GUIDE: ASLA esnetme
FEATURES = ["comp_score", "is_bullish", "atr_pct", "rsi", "macd_hist_norm", "vol_ratio"]


def get_label(df, start_idx, trend, entry, sl, atr):
    """vectorized_dataset_builder ile birebir aynı: limit dolumu + TP/SL ileriye bakar."""
    end_idx = min(start_idx + 30, len(df))   # ~5 gün ileri
    sa = df.iloc[start_idx:end_idx]
    tp = entry + atr * 2 if trend == "BULLISH" else entry - atr * 2
    filled = False
    for _, row in sa.iterrows():
        high, low = row["high"], row["low"]
        if trend == "BULLISH":
            if not filled and low <= entry:
                filled = True
            if filled:
                if low <= sl: return 0
                if high >= tp: return 1
        else:
            if not filled and high >= entry:
                filled = True
            if filled:
                if high >= sl: return 0
                if low <= tp: return 1
    return 0  # timeout = kayıp say


def build_real_dataset(months):
    rows = []
    meta = []
    for sym in COINS:
        try:
            df, src = fetch_any(sym, months)
        except Exception as e:
            meta.append(f"- **{sym}**: veri yok — {e}")
            continue
        df = df.sort_values("ts").reset_index(drop=True)
        # builder ile aynı indikatörler
        df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
        macd = ta.trend.MACD(df["close"], window_slow=26, window_fast=12, window_sign=9)
        df["macd_hist"] = macd.macd_diff()
        df["vol_sma"] = ta.trend.SMAIndicator(df["volume"], window=20).sma_indicator()

        n0 = len(rows)
        for i in range(WARMUP, len(df) - 1):
            df_slice = df.iloc[max(0, i - 300):i]
            comp, trend, entry_, sl_, atr_, vol_ok_ = score_slice_v2(df_slice)
            if comp < 4.5 or trend == "NEUTRAL" or entry_ is None:
                continue
            if _trend_1d(df_slice) != trend:
                continue
            if not vol_ok_:
                continue
            sl_dist = abs(entry_ - sl_) / entry_
            if not (0.005 < sl_dist <= 0.10):
                continue
            close_px = float(df["close"].iloc[i])
            vol_sma = float(df["vol_sma"].iloc[i])
            rsi_v = float(df["rsi"].iloc[i])
            mh = float(df["macd_hist"].iloc[i])
            if not np.isfinite(rsi_v) or not np.isfinite(mh) or vol_sma <= 0:
                continue
            rows.append({
                "ts": df["ts"].iloc[i],
                "comp_score": comp,
                "is_bullish": 1 if trend == "BULLISH" else 0,
                "atr_pct": atr_ / close_px * 100,
                "rsi": rsi_v,
                "macd_hist_norm": mh / close_px * 1000,
                "vol_ratio": float(df["volume"].iloc[i]) / vol_sma,
                "label": get_label(df, i, trend, entry_, sl_, atr_),
            })
        meta.append(f"- **{sym}** ({src}): {len(df)} mum, {len(rows)-n0} sinyal")
    out = pd.DataFrame(rows).dropna().reset_index(drop=True)
    out = out.sort_values("ts").reset_index(drop=True)  # kronolojik (portföy)
    return out, meta


def wilson(k, n, z=1.96):
    if n == 0: return (0.0, 0.0)
    p = k/n; d = 1+z*z/n
    c = (p+z*z/(2*n))/d
    h = (z*np.sqrt(p*(1-p)/n+z*z/(4*n*n)))/d
    return (max(0,c-h), min(1,c+h))


def train(df):
    import xgboost as xgb
    from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
    from sklearn.metrics import precision_score, accuracy_score

    X, y = df[FEATURES], df["label"]
    split = int(len(df)*0.8)
    Xtr, Xte = X.iloc[:split], X.iloc[split:]
    ytr, yte = y.iloc[:split], y.iloc[split:]

    grid = {
        "max_depth": [2, 3],            # overfit kalkanı
        "learning_rate": [0.01, 0.05, 0.1],
        "n_estimators": [50, 100, 200],
        "subsample": [0.8, 1.0],
        "colsample_bytree": [0.8, 1.0],
    }
    gs = GridSearchCV(
        xgb.XGBClassifier(objective="binary:logistic", random_state=42, eval_metric="logloss"),
        grid, scoring="precision", cv=TimeSeriesSplit(n_splits=4), n_jobs=-1)
    gs.fit(Xtr, ytr)
    best = gs.best_estimator_

    proba = best.predict_proba(Xte)[:, 1]
    taken = proba >= THRESHOLD
    n_taken = int(taken.sum())
    res = {
        "best_params": gs.best_params_,
        "test_n": int(len(yte)),
        "taken": n_taken,
        "selectivity": n_taken/len(yte) if len(yte) else 0,
    }
    if n_taken > 0:
        wins = int(yte[taken].sum())
        res["real_wr"] = precision_score(yte, taken.astype(int), zero_division=0)
        res["wins"] = wins
        res["ci"] = wilson(wins, n_taken)
    res["acc"] = accuracy_score(yte, (proba >= 0.5).astype(int))
    return best, res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=float, default=12.0)
    args = ap.parse_args()

    L = []
    def log(s=""): print(s); L.append(s)

    log("# EMIR — XGBoost GERÇEK Veriyle Eğitim Raporu")
    log(f"_Üretim: {dt.datetime.utcnow().isoformat()}Z (GitHub Actions, canlı internet)_")
    log(f"_Eğitim periyodu: son {args.months:.0f} ay · 4H · {', '.join(COINS)}_\n")

    df, meta = build_real_dataset(args.months)
    log("## Veri Çıkarımı (gerçek score_slice_v2)")
    L.extend(meta)
    log(f"\nToplam gerçek sinyal: **{len(df)}**")
    if len(df) < 80:
        log("\n## ❌ Yetersiz veri (model eğitilemedi).")
        _write(L); return
    base_wr = df.label.mean()
    blo, bhi = wilson(int(df.label.sum()), len(df))
    log(f"Ham (filtresiz) WR: **%{100*base_wr:.1f}** (CI %{100*blo:.1f}–%{100*bhi:.1f})")

    df.to_csv(os.path.join(HERE, "ml_dataset_real.csv"), index=False)

    best, r = train(df)
    best.save_model(os.path.join(HERE, "optimal_xgb_real.json"))

    log("\n## XGBoost — Gerçek Hold-out Sonucu (eşik 0.60)")
    log(f"- En iyi parametreler: `{r['best_params']}`")
    log(f"- Hold-out işlem: {r['test_n']}")
    log(f"- Eşiği geçen (alınan): {r['taken']}  (seçicilik %{100*r['selectivity']:.0f})")
    if "real_wr" in r:
        lo, hi = r["ci"]
        log(f"- **GERÇEK Win Rate: %{100*r['real_wr']:.1f}**  ({r['wins']}/{r['taken']})")
        log(f"- %95 Güven Aralığı: %{100*lo:.1f} – %{100*hi:.1f}")
    else:
        log("- ⚠️ Hold-out'ta 0.60 eşiğini geçen işlem YOK — WR ölçülemedi.")

    log("\n## Yorum")
    log("- Bu WR **gerçek piyasa verisinden** geldi; mock değil.")
    log("- Mock'taki %75/%76 ile karşılaştır: aradaki fark = eski beynin yanılsaması.")
    if "real_wr" in r and (r["real_wr"] < 0.60 or r["ci"][0] < 0.50):
        log("- ⚠️ Gerçek WR <0.60 ya da CI alt sınırı <0.50 → edge zayıf/kanıtsız.")
    log("\n_Model: emir/optimal_xgb_real.json · Dataset: emir/ml_dataset_real.csv_")
    _write(L)


def _write(L):
    with open(os.path.join(HERE, "xgb_real_report.md"), "w") as f:
        f.write("\n".join(L) + "\n")
    print("\n[yazıldı] emir/xgb_real_report.md")


if __name__ == "__main__":
    main()
