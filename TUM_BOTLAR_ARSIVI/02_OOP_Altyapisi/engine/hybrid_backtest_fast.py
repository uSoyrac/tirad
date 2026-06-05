import pandas as pd
import numpy as np
import xgboost as xgb
import json
import os
import sys

# live_scan ve backtest_enhanced'dan gerekli fonksiyonları import edelim
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from backtest_enhanced import score_slice_v2, WARMUP

def run_hybrid_backtest():
    # Model ve metadatayı yükle
    model = xgb.XGBClassifier()
    model.load_model("bot/engine/v23_xgb_model.json")
    with open("bot/engine/v23_xgb_meta.json", "r") as f:
        meta = json.load(f)
    features = meta["features"]
    
    features_dir = "bot/engine/features"
    data_dir = "bot/engine/data"
    files = ["BTC_USDT.csv"] # Sadece BTC test et (Çok hızlı olması için)
    
    TP_PCT = 2.5
    SL_PCT = 1.0
    COMMISSION = 0.18 
    
    total_trades = 0
    wins = 0
    losses = 0
    gross_win = 0.0
    gross_loss = 0.0
    
    capital = 10000.0
    risk_per_trade = 0.02
    equity_curve = [capital]
    
    print("="*50)
    print(" V23 HYBRID (AI + SMC) BACKTEST")
    print("="*50)
    
    for file in files:
        # Önceden hesaplanmış feature'lar (sadece AI onayı almak için hızlı tarama)
        df_feat = pd.read_csv(os.path.join(features_dir, file))
        df_feat = df_feat.dropna(subset=['target'])
        
        # Test seti (son %20) - Out of sample test
        split_idx = int(len(df_feat) * 0.8)
        df_test = df_feat.iloc[split_idx:]
        
        if len(df_test) == 0: continue
        
        X = df_test[features]
        probs = model.predict_proba(X)[:, 1]
        df_test = df_test.copy()
        df_test['win_prob'] = probs
        
        # Sinyaller: win_prob >= 0.44 ise AI Onayı var
        signals = df_test[df_test['win_prob'] >= 0.44]
        
        # SMC / ICT kurallarını çalıştırmak için asıl fiyat datasını yükle
        df_raw = pd.read_csv(os.path.join(data_dir, file), parse_dates=['ts'])
        df_raw.set_index('ts', inplace=True)
        
        symbol_trades = 0
        
        for idx, row in signals.iterrows():
            ts = row['ts']
            
            # DataFrame'de bu timestamp'in indexini bul
            try:
                raw_idx = df_raw.index.get_loc(ts)
            except KeyError:
                continue
                
            if raw_idx < WARMUP:
                continue
                
            # df_slice: ilgili muma kadarki tüm geçmiş (o mum dahil)
            df_slice = df_raw.iloc[:raw_idx+1]
            
            # AĞIR HESAPLAMA: SMC/ICT Puanlama (Sadece AI'ın onayladığı yerlerde)
            comp, trend, entry_, sl_, atr_, vol_ok_ = score_slice_v2(df_slice)
            
            # KURAL: Hem AI onayı var, hem SMC skoru > 4.5, hem trend var, hem de hacim onaylı
            if comp >= 4.5 and trend in ("BULLISH", "BEARISH") and entry_ is not None and vol_ok_:
                target = row['target']
                risk_amount = capital * risk_per_trade
                
                # Sadece Long işlemler (AI modelimiz sadece Long hedefli eğitilmişti, veya iki yönlü de test edilebilir)
                if trend == "BULLISH":
                    if target == 1:
                        pnl = risk_amount * ((TP_PCT - COMMISSION) / SL_PCT)
                        capital += pnl
                        wins += 1
                        gross_win += pnl
                    else:
                        pnl = -risk_amount * ((SL_PCT + COMMISSION) / SL_PCT)
                        capital += pnl
                        losses += 1
                        gross_loss -= pnl
                        
                    equity_curve.append(capital)
                    total_trades += 1
                    symbol_trades += 1
                    
        print(f"Processed {file}: Found {symbol_trades} high-quality hybrid trades.")
        sys.stdout.flush()
            
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    pf = (gross_win / gross_loss) if gross_loss > 0 else float('inf')
    net_return = (capital - 10000.0) / 10000.0 * 100
    
    eq_arr = np.array(equity_curve)
    peak = np.maximum.accumulate(eq_arr)
    dd = (eq_arr - peak) / peak * 100
    max_dd = abs(dd.min()) if len(dd) > 0 else 0
    
    print("="*50)
    print(" HYBRID BACKTEST RESULTS (OOS)")
    print("="*50)
    print(f"Total Trades : {total_trades}")
    print(f"Wins / Losses: {wins} / {losses}")
    print(f"Win Rate     : {win_rate:.2f}%")
    print(f"Profit Factor: {pf:.2f}")
    print(f"Max Drawdown : {max_dd:.2f}%")
    print(f"Net P&L      : {net_return:+.2f}%")
    print(f"Final Capital: ${capital:.2f}")
    print("="*50)

if __name__ == "__main__":
    run_hybrid_backtest()
