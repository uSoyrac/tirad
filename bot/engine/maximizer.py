import pandas as pd
import numpy as np
import ta

class DynamicMaximizer:
    """
    Yerçekimi Kementi (Orbital Decay) ve Sörf Dalga Kırılması (Wave Break)
    mantıklarıyla dinamik Trailing Stop (Çıkış Noktası) hesaplar.
    """
    
    @staticmethod
    def calculate_exit(df: pd.DataFrame, entry_price: float, direction: str, current_sl: float) -> dict:
        """
        Ultimate Sentez (Balistik Çıkış):
        İvme (Acceleration) tükenene kadar fiyatı takip eder. İvme terse döndüğünde 
        (mermi tepeye ulaştığında) kementi acımasızca daraltıp karı kilitler.
        """
        if df.empty or len(df) < 50:
            return {"action": "HOLD", "new_sl": current_sl, "reason": "Yetersiz Veri"}
            
        df = df.copy()
        
        # Son kapanan mumu alıyoruz
        close = df['close'].iloc[-2]
        
        # Göstergeler
        df['atr'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range()
        df['velocity'] = df['close'].diff()
        df['accel'] = df['velocity'].diff()
        
        atr = df['atr'].iloc[-2]
        accel = df['accel'].iloc[-2]
        
        proposed_sl = current_sl
        is_exhausted = False
        
        # Balistik Çıkış (Acceleration Decay)
        if direction == "LONG":
            if (close > entry_price) and (accel < 0):
                # İvme düştü, mermi tepeye vardı. Kementi sıkılaştır (1 ATR)
                proposed_sl = close - (atr * 1.0)
                is_exhausted = True
        else:
            if (close < entry_price) and (accel > 0):
                # İvme düştü, kementi sıkılaştır (1 ATR)
                proposed_sl = close + (atr * 1.0)
                is_exhausted = True
                
        # Trailing stop sadece kârı koruyacak yönde ilerler (geri alınmaz)
        if direction == "LONG":
            final_sl = max(current_sl, proposed_sl)
        else:
            final_sl = min(current_sl, proposed_sl)
            
        if final_sl != current_sl:
            if is_exhausted:
                return {"action": "UPDATE", "new_sl": final_sl, "reason": "Balistik İvme Tükendi -> Kement Daraldı"}
            else:
                return {"action": "UPDATE", "new_sl": final_sl, "reason": "Kement Daraldı"}
                
        return {"action": "HOLD", "new_sl": current_sl, "reason": "Trend İvmesi Korunuyor"}
