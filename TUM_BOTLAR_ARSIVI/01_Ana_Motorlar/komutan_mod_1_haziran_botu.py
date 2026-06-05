import ccxt
import pandas as pd
import numpy as np
import xgboost as xgb
import os
import time
import json
import ta
import sys
from datetime import datetime

# Import feature engineer
# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from bot.engine.feature_engineer_v25 import engineer_features_v25

class KomutanModLiveTrader:
    def __init__(self):
        print("🤖 KOMUTAN MODU (1 HAZİRAN BOTU) BAŞLATILIYOR...")
        print("🛡️ Gerçekçi, ADX Filtreli, Trailing Stoplu ve Çoklu Koin Korumalı Sistem")
        
        # Connect to Binance
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        
        self.symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT']
        self.timeframe = '1h'
        self.risk_per_trade = 0.02
        
        # Load AI Model
        self.model = xgb.XGBClassifier()
        self.model.load_model(os.path.join("bot", "engine", "v27_xgb_model.json"))
        
        with open(os.path.join("bot", "engine", "v27_xgb_meta.json"), "r") as f:
            meta = json.load(f)
        self.features = meta["features"]
        
        # Load or create Paper Ledger
        self.ledger_file = os.path.join("bot", "komutan_ledger.json")
        self.state = self.load_state()

    def load_state(self):
        if os.path.exists(self.ledger_file):
            with open(self.ledger_file, 'r') as f:
                return json.load(f)
        else:
            return {
                "balance": 10000.0,
                "open_positions": [],
                "trade_history": []
            }
            
    def save_state(self):
        with open(self.ledger_file, 'w') as f:
            json.dump(self.state, f, indent=4)
            
    def fetch_data(self, symbol):
        ohlcv = self.exchange.fetch_ohlcv(symbol, self.timeframe, limit=200)
        df = pd.DataFrame(ohlcv, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
        df['ts'] = pd.to_datetime(df['ts'], unit='ms')
        df.set_index('ts', inplace=True)
        return df

    def scan_market(self):
        candidates = []
        
        for symbol in self.symbols:
            try:
                df = self.fetch_data(symbol)
                
                # ADX Filter
                adx_ind = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
                df['adx_14'] = adx_ind.adx()
                current_adx = df['adx_14'].iloc[-1]
                
                # Deep Quant Features
                df_features = engineer_features_v25(df.copy())
                last_row = df_features.iloc[-1:]
                
                # Drop rows with NaNs in features
                if last_row[self.features].isnull().values.any():
                    continue
                    
                X_live = last_row[self.features]
                prob = self.model.predict_proba(X_live)[0][1]
                
                print(f"🔍 {symbol} | Yapay Zeka: %{prob*100:.1f} | ADX: {current_adx:.1f}")
                
                # Komutan Modu Kuralları: AI > 0.55 VE ADX > 20
                if prob > 0.55 and current_adx > 20:
                    candidates.append({
                        'symbol': symbol,
                        'prob': prob,
                        'adx': current_adx,
                        'close': df['close'].iloc[-1],
                        'atr': (last_row['atr_14_pct'].iloc[0] / 100) * df['close'].iloc[-1],
                        'momentum': last_row['slope_10_pct'].iloc[0]
                    })
                    
            except Exception as e:
                print(f"❌ Veri hatası ({symbol}): {e}")
                
        return candidates

    def manage_positions(self):
        still_open = []
        for pos in self.state['open_positions']:
            try:
                ticker = self.exchange.fetch_ticker(pos['symbol'])
                current_price = ticker['last']
                
                hit_sl = current_price <= pos['sl_price']
                
                if hit_sl:
                    print(f"🔴 [KOMUTAN] {pos['symbol']} STOP LOSS PATLADI! Çıkış: {current_price}")
                    pnl_pct = (current_price - pos['entry_price']) / pos['entry_price']
                    net_pnl_pct = pnl_pct - (0.0004 * 2) - 0.0005 # Commission & Slippage
                    pnl_usd = pos['position_size'] * net_pnl_pct
                    
                    self.state['balance'] += pnl_usd
                    pos['exit_price'] = current_price
                    pos['pnl_usd'] = pnl_usd
                    self.state['trade_history'].append(pos)
                else:
                    # Trailing Stop Management
                    if current_price >= pos['breakeven_target']:
                        if not pos.get('is_breakeven_hit', False):
                            print(f"🛡️ [KOMUTAN] {pos['symbol']} BAŞA BAŞA ULAŞTI! Trailing Stop Aktif.")
                            pos['is_breakeven_hit'] = True
                            
                    if pos.get('is_breakeven_hit', False):
                        potential_sl = current_price - (2.0 * pos['atr_val'])
                        if potential_sl > pos['sl_price']:
                            pos['sl_price'] = potential_sl
                            print(f"📈 [KOMUTAN] {pos['symbol']} Trailing Stop Yükseltildi: {pos['sl_price']:.4f}")
                            
                    still_open.append(pos)
                    
            except Exception as e:
                print(f"❌ Pozisyon yönetim hatası ({pos['symbol']}): {e}")
                still_open.append(pos)
                
        self.state['open_positions'] = still_open
        self.save_state()

    def run(self):
        print(f"💰 Güncel Kasa (Paper): ${self.state['balance']:.2f}")
        self.manage_positions()
        
        candidates = self.scan_market()
        
        # CROSS-SECTIONAL ALPHA: Momentum'u en yüksek olan tek koini seç
        if candidates:
            candidates.sort(key=lambda x: x['momentum'], reverse=True)
            best_coin = candidates[0]
            
            # Aynı coinde pozisyon yoksa ve kasa limiti uygunsa gir
            if not any(p['symbol'] == best_coin['symbol'] for p in self.state['open_positions']):
                if sum(p['position_size'] for p in self.state['open_positions']) <= self.state['balance'] * 5:
                    
                    entry = best_coin['close']
                    atr = best_coin['atr']
                    sl = entry - (1.5 * atr)
                    breakeven = entry + (2.0 * atr)
                    
                    risk_usd = self.state['balance'] * self.risk_per_trade
                    sl_pct = (entry - sl) / entry
                    pos_size = risk_usd / sl_pct
                    
                    new_pos = {
                        'symbol': best_coin['symbol'],
                        'entry_price': entry,
                        'sl_price': sl,
                        'breakeven_target': breakeven,
                        'atr_val': atr,
                        'position_size': pos_size,
                        'entry_time': datetime.now().isoformat(),
                        'is_breakeven_hit': False
                    }
                    
                    print(f"🚀 [KOMUTAN] SİNYAL ONAYLANDI! EN GÜÇLÜ KOİN: {best_coin['symbol']}")
                    print(f"   -> Giriş: {entry} | Hedef: Sınırsız (Trailing) | İlk Stop: {sl}")
                    
                    self.state['open_positions'].append(new_pos)
                    self.save_state()
                else:
                    print("⚠️ Marjin limiti dolu, yeni işleme girilmiyor.")
                    
        print("-" * 50)

if __name__ == "__main__":
    bot = KomutanModLiveTrader()
    bot.run()
