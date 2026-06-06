import pandas as pd
import numpy as np

class MetaRegimeAnalyzer:
    """
    Termodinamik ve Bilgi Teorisi tabanlı piyasa fazı (Regime) analizörü.
    Piyasayı Solid (Yatay), Liquid (Trend) ve Gas (Toksik/İşlem Yapma) olarak ayırır.
    Ayrıca Kinetik Şok (Momentum Ignition) patlamalarını tespit eder.
    """
    
    @staticmethod
    def analyze(df: pd.DataFrame) -> dict:
        if df.empty or len(df) < 30:
            return {"phase": "SOLID", "ignition": False, "reason": "Yetersiz Veri"}
            
        df = df.copy()
        
        # ── 1. KİNETİK ŞOK (MOMENTUM IGNITION) ──
        # Kinetik Enerji = Hacim * (Fiyat Değişimi)^2
        df['velocity'] = df['close'].diff()
        df['kinetic_energy'] = df['volume'] * (df['velocity']**2)
        
        df['ke_mean_10'] = df['kinetic_energy'].rolling(10).mean()
        df['ke_std_10'] = df['kinetic_energy'].rolling(10).std()
        
        ke_current = df['kinetic_energy'].iloc[-2]
        ke_mean = df['ke_mean_10'].iloc[-2]
        ke_std = df['ke_std_10'].iloc[-2]
        
        is_ignition = ke_current > (ke_mean + 3 * ke_std) and ke_current > 0
        
        # Yön tespiti
        vel_current = df['velocity'].iloc[-2]
        ignition_dir = "LONG" if vel_current > 0 else "SHORT" if vel_current < 0 else None
        
        # ── 2. TERMODİNAMİK FAZ (META-REGIME) ──
        # Sıcaklık (Varyans/Kaos) ve Akış (Net Yön)
        df['temperature'] = df['close'].rolling(20).std()
        df['flow'] = abs(df['close'] - df['close'].shift(20))
        
        # Toksisite (Wick boyutu / Gövde)
        df['wick_size'] = (df['high'] - np.maximum(df['close'], df['open'])) + (np.minimum(df['close'], df['open']) - df['low'])
        df['body_size'] = abs(df['close'] - df['open']) + 1e-8
        df['toxicity'] = (df['wick_size'] / df['body_size']).rolling(10).mean()
        
        # Eşikler
        temp_current = df['temperature'].iloc[-2]
        temp_mean = df['temperature'].mean() # Tarihsel ortalama
        
        flow_current = df['flow'].iloc[-2]
        flow_mean = df['flow'].mean()
        
        tox_current = df['toxicity'].iloc[-2]
        
        phase = "SOLID" # Varsayılan: Yatay / Avlanma
        reason = "Düşük Akış, Düşük Sıcaklık"
        
        # Gaz Fazı: Çok yüksek sıcaklık + düşük akış VEYA aşırı toksik fitiller
        if (temp_current > temp_mean * 1.5 and flow_current < flow_mean) or tox_current > 3.0:
            phase = "GAS"
            reason = "Toksik/Kaotik Piyasa (İşlem Yapma)"
        # Sıvı Fazı: Yüksek akış
        elif flow_current > flow_mean * 1.2:
            phase = "LIQUID"
            reason = "Net Yönelimli Trend"
            
        return {
            "phase": phase,
            "phase_reason": reason,
            "ignition": is_ignition,
            "ignition_dir": ignition_dir,
            "metrics": {
                "kinetic_energy": ke_current,
                "temperature": temp_current,
                "flow": flow_current,
                "toxicity": tox_current
            }
        }
