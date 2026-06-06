import pandas as pd
import numpy as np
import ta
from bot.engine.microstructure import MicrostructureAnalyzer

class PredatorEngine:
    """
    Predatör Pususu ve Balistik Menzil stratejilerini yönetir.
    Dipten Avlanma (Emilim Uyumsuzluğu) ve Tepede Çıkış (Menzil Tüketimi) işlemleri.
    """
    
    @staticmethod
    def analyze_entry(df: pd.DataFrame) -> dict:
        """
        Her mumda Predator giriş şartlarını arar.
        """
        # 1. Mikroyapı: Emilim var mı? (Dipten avlanma fırsatı)
        micro = MicrostructureAnalyzer.detect_absorption_divergence(df)
        
        # 2. Sismik Şoklar (Hazırlık evresi var mıydı?)
        seismic = MicrostructureAnalyzer.detect_seismic_shocks(df)
        
        # Eğer Emilim var ve Sismik Şoklarla destekleniyorsa bu kesin pusudur!
        action = "HOLD"
        direction = None
        sl_price = 0.0
        
        if micro["ambush_long"]:
            action = "PREDATOR_LONG"
            direction = "LONG"
            # Hard SL wicks'in %0.1 altı
            sl_price = df['low'].iloc[-2] * 0.999 
        elif micro["ambush_short"]:
            action = "PREDATOR_SHORT"
            direction = "SHORT"
            sl_price = df['high'].iloc[-2] * 1.001
            
        return {
            "action": action,
            "direction": direction,
            "sl_price": sl_price,
            "is_seismic": seismic,
            "climax_vol": micro["climax_volume"]
        }
        
    @staticmethod
    def calculate_ballistic_exit(df: pd.DataFrame, entry_price: float, direction: str, initial_vol: float) -> dict:
        """
        Balistik Menzil (Ballistic Trajectory Limit) hesaplayarak çıkış noktası belirler.
        """
        if len(df) < 20:
            return {"action": "HOLD", "reason": "Veri Yetersiz"}
            
        current = df.iloc[-1]
        
        # Kinetik Hız (Muzzle Velocity)
        velocity = abs(df['close'].diff().iloc[-1])
        kinetic_energy = initial_vol * (velocity ** 2)
        
        # Sürtünme / Order Book (Proxy olarak ATR ve Hacim kullanıyoruz)
        atr = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14).iloc[-1]
        
        # Max Menzil Formülü (Basit modelleme)
        # Kinetik enerji ATR'ye göre ne kadar büyükse, gideceği ATR mesafesi o kadar uzar
        avg_vol = df['volume'].mean()
        energy_ratio = kinetic_energy / (avg_vol * (atr**2) + 1e-8)
        
        # Enerji düştükçe (momentum bittikçe) trailing stop'u kitle
        # İvme (Acceleration) kontrolü
        accel = df['close'].diff().diff().iloc[-1]
        
        if direction == "LONG":
            is_exhausted = (accel < 0) and (energy_ratio < 0.5)
            new_sl = current['close'] - (atr * 0.5) if is_exhausted else current['close'] - (atr * 2.0)
        else:
            is_exhausted = (accel > 0) and (energy_ratio < 0.5)
            new_sl = current['close'] + (atr * 0.5) if is_exhausted else current['close'] + (atr * 2.0)
            
        action = "UPDATE" if is_exhausted else "HOLD"
        reason = "Balistik Yakıt Bitti (Yerçekimi Kazandı)" if is_exhausted else "Uçuş Devam Ediyor"
        
        return {
            "action": action,
            "new_sl": new_sl,
            "reason": reason
        }
