import pandas as pd
import numpy as np
import xgboost as xgb
import json
import os

def run_fast_backtest():
    # Model ve metadatayı yükle
    model = xgb.XGBClassifier()
    model.load_model("bot/engine/v23_xgb_model.json")
    with open("bot/engine/v23_xgb_meta.json", "r") as f:
        meta = json.load(f)
    features = meta["features"]
    
    features_dir = "bot/engine/features"
    files = [f for f in os.listdir(features_dir) if f.endswith('.csv')]
    
    # Komisyon ve hedefler
    TP_PCT = 2.5
    SL_PCT = 1.0
    COMMISSION = 0.18 # Round trip (Taker + slippage)
    
    total_trades = 0
    wins = 0
    losses = 0
    gross_win = 0.0
    gross_loss = 0.0
    
    capital = 10000.0
    risk_per_trade = 0.02 # 2% risk
    equity_curve = [capital]
    
    all_data = []
    
    for file in files:
        df = pd.read_csv(os.path.join(features_dir, file))
        df = df.dropna(subset=['target'])
        
        # Gelecek sızıntısını önlemek için son 80% kısmı test verisi kabul edelim
        # (Çünkü model ilk %80'de eğitildi)
        split_idx = int(len(df) * 0.8)
        df_test = df.iloc[split_idx:]
        
        if len(df_test) == 0: continue
        
        X = df_test[features]
        # Olasılık tahmini
        probs = model.predict_proba(X)[:, 1]
        
        df_test = df_test.copy()
        df_test['win_prob'] = probs
        
        # Sinyaller: win_prob >= 0.44 ise LONG
        signals = df_test[df_test['win_prob'] >= 0.44]
        
        for idx, row in signals.iterrows():
            target = row['target']
            
            # Risk hesaplama
            risk_amount = capital * risk_per_trade
            
            if target == 1:
                # Kazanç
                net_profit_pct = TP_PCT - COMMISSION
                pnl = risk_amount * (net_profit_pct / SL_PCT) # RR = 2.5/1.0
                capital += pnl
                wins += 1
                gross_win += pnl
            else:
                # Kayıp
                net_loss_pct = SL_PCT + COMMISSION
                pnl = -risk_amount * (net_loss_pct / SL_PCT)
                capital += pnl
                losses += 1
                gross_loss -= pnl # make it positive for PF calculation
                
            equity_curve.append(capital)
            total_trades += 1
            
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    pf = (gross_win / gross_loss) if gross_loss > 0 else float('inf')
    net_return = (capital - 10000.0) / 10000.0 * 100
    
    # Drawdown
    eq_arr = np.array(equity_curve)
    peak = np.maximum.accumulate(eq_arr)
    dd = (eq_arr - peak) / peak * 100
    max_dd = abs(dd.min())
    
    print("="*50)
    print(" V23 PURE AI BACKTEST (OUT-OF-SAMPLE)")
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
    run_fast_backtest()
