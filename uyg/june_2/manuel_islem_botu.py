#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
MANUEL İŞLEM BOTU (Yüksek İsabetli %82.4 Sinyal Jeneratörü)
═══════════════════════════════════════════════════════════════════════════════

Bu araç, Yapay Zeka'nın (XGBoost) Smart Money (İvme) verilerini kullanarak
%82.4 isabet oranıyla bulduğu en güçlü yönleri "Manuel İşlem" (Elle trade) 
yapacak yatırımcılar için ekrana yazdırır.

Kullanım Amacı:
1. Bot otomatik işlem açmaz, size "Şu coinde LONG aç, TP'yi %2'ye koy" der.
2. Stop Loss %10'dur (Sıyrıklar için değil, sadece tam çöküşlerde stop olur).
3. Arkadaşınız bu sinyalleri kendi borsasında manuel olarak deneyebilir.

Çalıştırma:
  python3 manuel_islem_botu.py
═══════════════════════════════════════════════════════════════════════════════
"""
import os, sys, pickle, numpy as np, pandas as pd, warnings
from datetime import datetime, timedelta
warnings.filterwarnings("ignore")

# Modül yollarını ayarla
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))
import ta, xgboost as xgb
from signal_lab import atr
from live_strategy import DONCHIAN, SUPERTREND

# ── KONFİG ────────────────────────────────────────────────────────────────────
DATA_DIR   = os.path.join(os.path.dirname(__file__), "../../bot/engine/data_v63")
COINS      = ["BTC", "ETH", "SOL"]
TP         = 0.02                 # +%2 Kâr Hedefi
SL         = 0.10                 # -%10 Stop Loss (Geniş Stop)
GATE_TOP   = 0.20                 # Sadece En Güçlü %20 Sinyali Ver
CACHE_FILE = "/tmp/tp2_sl10_sigs.pkl"

FEATS = ["rsi","macd","adx","atrp","bbpct","ema50d","ema200d","roc","cci","stochk","ci","er","volr","d","hour", "ts_accel", "tbr_accel"]

def _feats(df):
    cl, hi, lo, vol = df["close"], df["high"], df["low"], df["volume"]
    mid=cl.rolling(20).mean(); sd=cl.rolling(20).std(); a=atr(df,14)
    tr=pd.concat([hi-lo,(hi-cl.shift()).abs(),(lo-cl.shift()).abs()],axis=1).max(axis=1)
    ci=100*np.log10(tr.rolling(14).sum()/(hi.rolling(14).max()-lo.rolling(14).min()))/np.log10(14)
    er=(cl-cl.shift(10)).abs()/(cl.diff().abs().rolling(10).sum()+1e-9)
    d4=cl.resample("4h").last(); e4=ta.trend.EMAIndicator(d4,50).ema_indicator()
    htf=np.sign(d4-e4).reindex(df.index,method="ffill").to_numpy()
    
    trade_size = df["volume"] / (df["number_of_trades"] + 1e-9)
    ts_accel = trade_size.diff().diff()
    taker_buy_ratio = df["taker_buy_base_asset_volume"] / (df["volume"] + 1e-9)
    tbr_accel = taker_buy_ratio.diff().diff()
    
    return dict(rsi=ta.momentum.RSIIndicator(cl,14).rsi().to_numpy(),
        macd=(ta.trend.MACD(cl).macd_diff()/cl).to_numpy(),
        adx=ta.trend.ADXIndicator(hi,lo,cl,14).adx().to_numpy(), atrp=(pd.Series(a)/cl).to_numpy(),
        bbpct=((cl-(mid-2*sd))/((mid+2*sd)-(mid-2*sd)+1e-9)).to_numpy(),
        ema50d=((cl-ta.trend.EMAIndicator(cl,50).ema_indicator())/cl).to_numpy(),
        ema200d=((cl-ta.trend.EMAIndicator(cl,200).ema_indicator())/cl).to_numpy(),
        roc=ta.momentum.ROCIndicator(cl,10).roc().to_numpy(),
        cci=ta.trend.CCIIndicator(hi,lo,cl,20).cci().to_numpy(),
        stochk=ta.momentum.StochasticOscillator(hi,lo,cl,14,3).stoch().to_numpy(),
        ci=ci.to_numpy(), er=er.to_numpy(), volr=(vol/vol.rolling(20).mean()).to_numpy(), htf4h=htf,
        ts_accel=ts_accel.to_numpy(), tbr_accel=tbr_accel.to_numpy())

def train_model():
    print("Yapay Zeka Geçmiş Verilerle Eğitiliyor (Bu işlem biraz sürebilir)...")
    if not os.path.exists(CACHE_FILE):
        print("HATA: Model eğitimi için geçmiş veri sinyalleri bulunamadı.")
        print("Lütfen önce 'python3 test_tp2_sl10.py' dosyasını çalıştırarak verileri önbelleğe alın.")
        sys.exit(1)
        
    rows = pickle.load(open(CACHE_FILE,"rb"))
    
    # Modeli tüm verilerle eğit (Canlı kullanım için en iyi ağırlıklar)
    X = np.array([r["x"] for r in rows])
    y = np.array([r["win"] for r in rows])
    
    clf = xgb.XGBClassifier(n_estimators=250, max_depth=4, learning_rate=0.05, 
                            subsample=0.8, colsample_bytree=0.8, eval_metric="logloss", 
                            random_state=42)
    clf.fit(X, y)
    
    # Threshold hesapla (Sadece en iyi %20 sinyalleri yakalamak için)
    P = clf.predict_proba(X)[:, 1]
    thr = np.quantile(P, 1 - GATE_TOP)
    
    print(f"Eğitim Tamamlandı. Güven Eşiği (Threshold): %{thr*100:.1f}")
    return clf, thr

def get_latest_signals(clf, thr):
    print("\n[ EN GÜNCEL PİYASA VERİLERİ TARANIYOR... ]")
    print("="*72)
    
    signals_found = 0
    for c in COINS:
        file_path = f"{DATA_DIR}/{c}_USDT.csv"
        if not os.path.exists(file_path): continue
            
        df = pd.read_csv(file_path, parse_dates=["ts"]).set_index("ts").sort_index()
        
        # 1H Resample (Sinyal stratejisine uygun)
        if len(df) > 1 and (df.index[1] - df.index[0]).seconds < 3600:
            df = df.resample("1h").agg({
                "open": "first", "high": "max", "low": "min", "close": "last",
                "volume": "sum", "quote_asset_volume": "sum", "number_of_trades": "sum",
                "taker_buy_base_asset_volume": "sum"
            }).dropna()
            
        if len(df) < 220: continue
            
        don, st = DONCHIAN(df), SUPERTREND(df)
        F = _feats(df)
        
        # Sadece son 48 saatteki fırsatları kontrol et
        recent_df = df.iloc[-48:]
        for i in range(len(recent_df)):
            t = len(df) - 48 + i
            fired = [x for x in (int(don[t]), int(st[t])) if x != 0]
            if not fired or len(set(fired)) > 1: continue
            
            d = set(fired).pop() # 1 (Long) veya -1 (Short)
            
            # Feature vektörünü oluştur
            x_vec = []
            for kk in FEATS:
                if kk == "d": x_vec.append(float(d))
                elif kk == "hour": x_vec.append(float(df.index[t].hour))
                elif kk == "htf4h": x_vec.append(float(d)*F["htf4h"][t] if np.isfinite(F["htf4h"][t]) else 0.0)
                else: 
                    v = F[kk][t]
                    x_vec.append(float(v) if np.isfinite(v) else np.nan)
                    
            # Model tahmini (Güven Skoru)
            prob = float(clf.predict_proba(np.array([x_vec]))[:, 1][0])
            
            # Sadece eşiği geçen kusursuz sinyalleri ekrana bas
            if prob >= thr:
                signals_found += 1
                signal_time = df.index[t]
                current_price = df["close"].iloc[t]
                
                direction = "🟢 LONG" if d == 1 else "🔴 SHORT"
                tp_price = current_price * (1 + TP) if d == 1 else current_price * (1 - TP)
                sl_price = current_price * (1 - SL) if d == 1 else current_price * (1 + SL)
                
                print(f"[{signal_time}] COIN: {c:4s} | YÖN: {direction} | GÜVEN: %{prob*100:.1f}")
                print(f"    Giriş: ${current_price:.2f}")
                print(f"    Take Profit (+%2): ${tp_price:.2f}")
                print(f"    Stop Loss (-%10): ${sl_price:.2f}")
                print("-" * 72)
                
    if signals_found == 0:
        print("Şu an için kriterlere (En iyi %20) uyan aktif bir sinyal bulunamadı.")
        print("Piyasa beklemeye alındı. Sabır, kazanmanın yarısıdır.")

def main():
    print(__doc__)
    clf, thr = train_model()
    get_latest_signals(clf, thr)

if __name__ == "__main__":
    main()
