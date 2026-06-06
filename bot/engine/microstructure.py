import pandas as pd
import numpy as np

class MicrostructureAnalyzer:
    """
    Piyasanın mikroyapısını (Hacim atımları, OB aşınması, Likidite emilimi) analiz eder.
    Düşük zaman dilimlerinde (15m, 1H) çalışmak üzere tasarlanmıştır.
    """
    
    @staticmethod
    def detect_absorption_divergence(df: pd.DataFrame, window=20) -> dict:
        """
        Dipten Avlanma (Predator's Ambush):
        Fiyat son X mumun en düşük seviyesine iğne atar, devasa bir satış hacmi gelir 
        (Likidasyon şelalesi), ANCAK mum yeşil kapatır veya uzun alt fitil bırakır.
        """
        if len(df) < window + 5:
            return {"ambush_long": False, "ambush_short": False}
            
        current = df.iloc[-2]
        prev_window = df.iloc[-(window+2):-2]
        
        # 1. Hacim Anormalliği (Son mum hacmi, ortalamanın 3 katı mı?)
        vol_mean = prev_window['volume'].mean()
        is_vol_climax = current['volume'] > vol_mean * 2.5
        
        # 2. Emilim (Absorption) - Long Pusu için
        # Fiyat yeni dip yapıyor ama hacimle toplanıp yukarıda kapatıyor (Uzun alt fitil)
        lowest_low = prev_window['low'].min()
        is_sweep_low = current['low'] <= lowest_low
        lower_wick = np.minimum(current['close'], current['open']) - current['low']
        total_range = current['high'] - current['low'] + 1e-8
        
        ambush_long = is_vol_climax and is_sweep_low and (lower_wick / total_range > 0.5) and (current['close'] > current['open'])
        
        # 3. Emilim - Short Pusu için
        highest_high = prev_window['high'].max()
        is_sweep_high = current['high'] >= highest_high
        upper_wick = current['high'] - np.maximum(current['close'], current['open'])
        
        ambush_short = is_vol_climax and is_sweep_high and (upper_wick / total_range > 0.5) and (current['close'] < current['open'])
        
        return {
            "ambush_long": bool(ambush_long),
            "ambush_short": bool(ambush_short),
            "climax_volume": float(current['volume']) if is_vol_climax else 0
        }
        
    @staticmethod
    def detect_seismic_shocks(df: pd.DataFrame, lookback=20) -> bool:
        """
        Sismik Öncü Şoklar: Fiyat varyansı dipteyken hacimde anlık atımlar.
        Akıllı paranın tahtayı yoklaması.
        """
        if len(df) < lookback * 2:
            return False
            
        recent = df.iloc[-lookback-2:-2]
        
        # Fiyat varyansı (Düşük mü?)
        price_std = recent['close'].std()
        historical_std = df['close'].iloc[-lookback*3:-lookback-2].std()
        is_accumulation = price_std < historical_std * 0.5
        
        # Hacim Atımları (Pulses)
        vol_mean = df['volume'].iloc[-lookback*2:-lookback-2].mean()
        vol_std = df['volume'].iloc[-lookback*2:-lookback-2].std()
        
        # Son X mumda ortalamanın 2 std dev üstünde hacim patlaması oldu mu?
        pulses = recent[recent['volume'] > (vol_mean + 2 * vol_std)]
        
        return bool(is_accumulation and len(pulses) >= 2)
