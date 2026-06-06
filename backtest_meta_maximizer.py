import json
import logging
from datetime import datetime
import pandas as pd

from bot.engine.meta_regime import MetaRegimeAnalyzer
from bot.engine.maximizer import DynamicMaximizer
from bot.engine.signal_engine import SignalEngine
from live_scan import ohlcv

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("meta_backtest")

def run_meta_backtest():
    print("=" * 60)
    print("🧠 META-REJİM & MOMENTUM MAKSİMİZASYONU BACKTESTİ")
    print("=" * 60)
    
    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]
    
    engine = SignalEngine(min_score=5.5, mode="STANDARD")
    
    total_static_pnl = 0
    total_dynamic_pnl = 0
    
    results = []
    
    for symbol in symbols:
        print(f"\n[*] {symbol} Analiz Ediliyor...")
        try:
            df = ohlcv(symbol, "4h", lim=500)
            if df.empty or len(df) < 100:
                continue
                
            # Adım 1: Meta-Rejim Tespiti (Son 200 mumu tarayalım)
            # Gerçek bir backtest için her mumda yürütmeliyiz ama simülasyon için:
            # Son 100 mum üzerinde bir loop kuralım.
            
            for i in range(100, len(df)):
                window = df.iloc[:i]
                
                # Sadece GAS olmayan fazlarda ve SMC skoru yüksekse işleme gir
                meta = MetaRegimeAnalyzer.analyze(window)
                if meta['phase'] == "GAS":
                    continue # Toksik piyasada işlem yasak
                    
                # SMC analizi için SignalEngine'in mantığını manuel taklit edelim
                # Çünkü SignalEngine.analyze en son muma bakar. Biz window veriyoruz.
                ms = engine._structure  # Lazy load bypass
                from bot.engine.market_structure import MarketStructureAnalyzer
                sa = MarketStructureAnalyzer(symbol)
                ms_res = sa.analyze(window)
                
                if ms_res.composite_score < 5.5:
                    continue
                    
                # Momentum Ignition (Ateşleme Rejimi) varsa trend beklemeden dal.
                if meta['ignition']:
                    entry_dir = meta['ignition_dir']
                else:
                    if ms_res.trend.name == "NEUTRAL": continue
                    entry_dir = "LONG" if ms_res.trend.name == "BULLISH" else "SHORT"
                
                entry_price = window['close'].iloc[-1]
                initial_sl = ms_res.sl_price
                if initial_sl <= 0 or abs(entry_price - initial_sl) < 1e-8:
                    continue
                    
                # İşlem yakalandı!
                # Şimdi ileriye dönük mumları tarayarak Statik vs Dinamik çıkışı karşılaştır.
                
                # --- STATİK ÇIKIŞ (Sabit 3R TP) ---
                risk = abs(entry_price - initial_sl)
                tp_static = entry_price + (risk * 3.0) if entry_dir == "LONG" else entry_price - (risk * 3.0)
                
                static_pnl = 0
                static_exit = None
                
                # --- DİNAMİK ÇIKIŞ (Maximizer) ---
                current_dynamic_sl = initial_sl
                dynamic_pnl = 0
                dynamic_exit = None
                
                for j in range(i, len(df)):
                    future_window = df.iloc[:j+1]
                    current_candle = df.iloc[j]
                    
                    # 1. Statik Kontrol
                    if not static_exit:
                        if entry_dir == "LONG":
                            if current_candle['low'] <= initial_sl:
                                static_pnl = -1.0 # 1R Kayıp
                                static_exit = "SL"
                            elif current_candle['high'] >= tp_static:
                                static_pnl = 3.0 # 3R Kazanç
                                static_exit = "TP3"
                        else:
                            if current_candle['high'] >= initial_sl:
                                static_pnl = -1.0
                                static_exit = "SL"
                            elif current_candle['low'] <= tp_static:
                                static_pnl = 3.0
                                static_exit = "TP3"
                                
                    # 2. Dinamik Kontrol (Maximizer)
                    if not dynamic_exit:
                        # Önce stop patladı mı?
                        if entry_dir == "LONG" and current_candle['low'] <= current_dynamic_sl:
                            dynamic_pnl = (current_dynamic_sl - entry_price) / risk
                            dynamic_exit = "TRAIL_HIT"
                        elif entry_dir == "SHORT" and current_candle['high'] >= current_dynamic_sl:
                            dynamic_pnl = (entry_price - current_dynamic_sl) / risk
                            dynamic_exit = "TRAIL_HIT"
                        else:
                            # Maximizer karar versin
                            max_res = DynamicMaximizer.calculate_exit(future_window, entry_price, entry_dir, current_dynamic_sl)
                            if max_res['action'] == "EXIT":
                                exit_p = max_res['new_sl'] # Panic exit price
                                dynamic_pnl = (exit_p - entry_price) / risk if entry_dir == "LONG" else (entry_price - exit_p) / risk
                                dynamic_exit = max_res['reason']
                            elif max_res['action'] == "UPDATE":
                                current_dynamic_sl = max_res['new_sl']
                                
                    if static_exit and dynamic_exit:
                        break # İki strateji de bu işlemden çıktı
                
                if static_exit and dynamic_exit:
                    results.append({
                        "symbol": symbol,
                        "dir": entry_dir,
                        "static_pnl_R": static_pnl,
                        "dynamic_pnl_R": dynamic_pnl,
                        "dynamic_reason": dynamic_exit,
                        "ignition": meta['ignition']
                    })
                    total_static_pnl += static_pnl
                    total_dynamic_pnl += dynamic_pnl
                    
                    # Log only significant differences
                    if dynamic_pnl > static_pnl + 1.0:
                        print(f"[WIN] {symbol} {entry_dir} | Statik: {static_pnl:.1f}R | Dinamik: {dynamic_pnl:.1f}R ({dynamic_exit})")
                    
        except Exception as e:
            print(f"Hata {symbol}: {e}")
            
    print("\n" + "=" * 60)
    print("📊 KÜMÜLATİF BACKTEST SONUÇLARI (R Çarpanı)")
    print("=" * 60)
    print(f"Toplam İşlem Sayısı: {len(results)}")
    print(f"Sabit Hedefli (Statik) PnL : {total_static_pnl:.2f} R")
    print(f"Dinamik Sörf (Maximizer) PnL: {total_dynamic_pnl:.2f} R")
    print("=" * 60)
    
    if total_dynamic_pnl > total_static_pnl:
        print("\n🏆 Dinamik Maximizer, Sabit Hedefleri PARÇALADI!")
        print("Yerçekimi Kementi ve Dalga Kırılması çıkışları, trendleri son damlasına kadar sömürdü.")
    else:
        print("\nSabit hedefler daha iyi sonuç verdi (Testere piyasası ağırlıklı dönem).")

if __name__ == "__main__":
    run_meta_backtest()
