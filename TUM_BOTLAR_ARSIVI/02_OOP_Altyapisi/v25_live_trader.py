import ccxt
import pandas as pd
import numpy as np
import xgboost as xgb
import json
import os
import time
from datetime import datetime
import sys

# Add root directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import feature engineer
from bot.engine.feature_engineer_v25 import engineer_features_v25

SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
TIMEFRAME = '1h'
LIMIT = 200 # feature_engineer için yeterli geçmiş (EMA200 kullanıyoruz)

LEDGER_FILE = 'paper_ledger.json'

class V25LiveTrader:
    def __init__(self):
        self.exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'future'}})
        self.model = xgb.XGBClassifier()
        self.model.load_model("bot/engine/v25_xgb_model.json")
        with open("bot/engine/v25_xgb_meta.json", "r") as f:
            self.meta = json.load(f)
        self.features = self.meta["features"]
        self.init_ledger()
        
    def init_ledger(self):
        if not os.path.exists(LEDGER_FILE):
            ledger = {
                "balance": 10000.0,
                "open_positions": [],
                "trade_history": []
            }
            with open(LEDGER_FILE, 'w') as f:
                json.dump(ledger, f, indent=4)
                
    def load_ledger(self):
        with open(LEDGER_FILE, 'r') as f:
            return json.load(f)
            
    def save_ledger(self, ledger):
        with open(LEDGER_FILE, 'w') as f:
            json.dump(ledger, f, indent=4)
            
    def fetch_data(self, symbol):
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=LIMIT)
            df = pd.DataFrame(ohlcv, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
            df['ts'] = pd.to_datetime(df['ts'], unit='ms')
            df.set_index('ts', inplace=True)
            return df
        except Exception as e:
            print(f"Error fetching {symbol}: {e}")
            return None

    def manage_positions(self, symbol, current_price, current_high, current_low):
        ledger = self.load_ledger()
        still_open = []
        
        for pos in ledger["open_positions"]:
            if pos["symbol"] != symbol:
                still_open.append(pos)
                continue
                
            # SL or TP check
            hit_tp = current_high >= pos["tp_price"]
            hit_sl = current_low <= pos["sl_price"]
            
            if hit_tp or hit_sl:
                exit_price = pos["tp_price"] if hit_tp else pos["sl_price"]
                pnl_pct = (exit_price - pos["entry_price"]) / pos["entry_price"]
                
                # Komisyon & Slippage
                commission = 0.0004 # 0.04% maker/taker avg
                slippage = 0.0005 # 0.05%
                net_pnl_pct = pnl_pct - commission - slippage
                
                pnl_usd = pos["position_size"] * net_pnl_pct
                ledger["balance"] += pnl_usd
                
                status = "WIN 🟢" if hit_tp else "LOSS 🔴"
                print(f"[{status}] {symbol} pozisyonu kapandı! PnL: ${pnl_usd:.2f} | Kasa: ${ledger['balance']:.2f}")
                
                pos["exit_price"] = exit_price
                pos["pnl_usd"] = pnl_usd
                pos["status"] = "CLOSED"
                ledger["trade_history"].append(pos)
            else:
                still_open.append(pos)
                
        ledger["open_positions"] = still_open
        self.save_ledger(ledger)

    def scan_market(self):
        print(f"\n[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] V25 Deep Quant Piyasa Taraması Başlıyor...")
        ledger = self.load_ledger()
        
        for symbol in SYMBOLS:
            df = self.fetch_data(symbol)
            if df is None or len(df) < 100: continue
            
            # Güncel fiyatları pozisyon yönetimine gönder
            last_bar = df.iloc[-1]
            self.manage_positions(symbol, last_bar['close'], last_bar['high'], last_bar['low'])
            
            # Sinyal Üretimi
            try:
                df_feats = engineer_features_v25(df)
                if len(df_feats) == 0: continue
                
                last_feat = df_feats.iloc[-2] # En son kapanmış mum
                current_price = df.iloc[-2]['close']
                atr_val = (last_feat['atr_14_pct'] / 100) * current_price
                
                # Zaten açık pozisyon varsa bu coinde tekrar girme
                has_open = any(p["symbol"] == symbol for p in self.load_ledger()["open_positions"])
                if has_open:
                    continue
                    
                X = pd.DataFrame([last_feat])[self.features]
                
                # Olasılık Tahmini
                prob = self.model.predict_proba(X)[0][1]
                
                if prob >= 0.44:
                    print(f"✨ V25 SİNYAL ALINDI: {symbol} | Kazanma Olasılığı: %{prob*100:.1f}")
                    self.execute_trade(symbol, current_price, atr_val, prob)
                
            except Exception as e:
                print(f"Model Error on {symbol}: {e}")

    def execute_trade(self, symbol, entry_price, atr_val, prob):
        ledger = self.load_ledger()
        risk_per_trade = 0.02
        
        risk_amount = ledger["balance"] * risk_per_trade
        sl_dist = atr_val * 1.5
        tp_dist = atr_val * 2.5
        
        sl_price = entry_price - sl_dist
        tp_price = entry_price + tp_dist
        
        # Kaldıraçlı pozisyon büyüklüğü (sl_pct = sl_dist / entry_price)
        sl_pct = sl_dist / entry_price
        position_size = risk_amount / sl_pct # Dolar bazında gerçek büyüklük
        
        if position_size > ledger["balance"] * 5: # Max 5x leverage
            position_size = ledger["balance"] * 5
            
        new_pos = {
            "symbol": symbol,
            "entry_time": datetime.utcnow().isoformat(),
            "entry_price": entry_price,
            "tp_price": tp_price,
            "sl_price": sl_price,
            "position_size": position_size,
            "risk_usd": risk_amount,
            "win_prob": float(prob)
        }
        
        ledger["open_positions"].append(new_pos)
        self.save_ledger(ledger)
        print(f"🚀 [PAPER TRADE] {symbol} LONG Açıldı! Giriş: {entry_price:.4f} | Hedef: {tp_price:.4f} | Risk: ${risk_amount:.2f}")

    def run(self):
        print("V25 Live Trader (Paper Mode) Başlatıldı. Sinyal bekleniyor...")
        while True:
            # Sadece her saatin tam başında (xx:00) çalış
            now = datetime.utcnow()
            if now.minute == 0 and now.second < 10:
                self.scan_market()
                time.sleep(60) # Aynı dakikada 2 kere çalışmasını engelle
            else:
                # Test amaçlı doğrudan 1 kere çalıştıralım
                self.scan_market()
                break # Canlıya almadan önce dry-run (tek seferlik çalışma)

if __name__ == "__main__":
    trader = V25LiveTrader()
    trader.run()
