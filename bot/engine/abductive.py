import pandas as pd
import numpy as np
import ta
import logging

logger = logging.getLogger("bot.engine.abductive")

class AbductiveRegimeFilter:
    """
    Çoklu-Rejim (Multi-Regime) Keskin Nişancı Filtresi.
    Piyasa rejimine (Squeeze, Pullback, V-Bottom, Ignition) göre filtreleme yapar.
    Sadece 1 onay bile geçmek için yeterlidir (OR kapısı).
    Hiçbiri onaylamazsa, piyasa testere (chop) kabul edilir ve reddedilir.
    """
    
    @staticmethod
    def evaluate(df: pd.DataFrame, trend_dir: str) -> dict:
        """
        trend_dir: 'BULLISH' or 'BEARISH'
        Returns dict with 'valid': bool and 'reason': str
        """
        if df.empty or len(df) < 50:
            return {"valid": False, "reason": "Yetersiz veri (min 50 mum)"}
            
        try:
            # Sadece kopya üzerinden çalış
            df = df.copy()
            
            # --- 1. Base Indicators ---
            df['ema_50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
            df['ema_20'] = ta.trend.EMAIndicator(df['close'], window=20).ema_indicator()
            df['atr'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range()
            
            # --- 2. CVD Proxy ---
            df['candle_shape'] = (df['close'] - df['open']) / (df['high'] - df['low'] + 1e-8)
            df['vol_delta'] = df['candle_shape'] * df['volume']
            df['cvd_10'] = df['vol_delta'].rolling(window=10).sum()
            
            cvd_bullish = df['cvd_10'].iloc[-2] > 0
            cvd_bearish = df['cvd_10'].iloc[-2] < 0
            
            # --- 3. TTM Squeeze ---
            mult_bb = 2.0
            mult_kc = 1.5
            length = 20
            
            df['basis'] = df['close'].rolling(length).mean()
            df['dev'] = df['close'].rolling(length).std() * mult_bb
            df['bb_upper'] = df['basis'] + df['dev']
            df['bb_lower'] = df['basis'] - df['dev']
            df['kc_upper'] = df['basis'] + df['atr'] * mult_kc
            df['kc_lower'] = df['basis'] - df['atr'] * mult_kc
            df['squeeze_on'] = (df['bb_lower'] > df['kc_lower']) & (df['bb_upper'] < df['kc_upper'])
            df['squeeze_release'] = (~df['squeeze_on']) & df['squeeze_on'].shift(1).rolling(3).max().astype(bool)
            
            squeeze_fired = df['squeeze_release'].iloc[-2]
            
            # --- 4. ADX Regime (Pullbacks) ---
            adx_ind = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
            adx = adx_ind.adx().iloc[-2]
            di_plus = adx_ind.adx_pos().iloc[-2]
            di_minus = adx_ind.adx_neg().iloc[-2]
            
            close = df['close'].iloc[-2]
            low = df['low'].iloc[-2]
            high = df['high'].iloc[-2]
            ema_50 = df['ema_50'].iloc[-2]
            ema_20 = df['ema_20'].iloc[-2]
            rsi_14 = ta.momentum.RSIIndicator(df['close'], window=14).rsi().iloc[-2]
            
            is_strong_uptrend = (adx >= 25) and (di_plus > di_minus) and (close > ema_50)
            is_strong_downtrend = (adx >= 25) and (di_minus > di_plus) and (close < ema_50)
            
            bull_pullback = is_strong_uptrend and (low <= ema_20) and (close > ema_20) and (rsi_14 < 50) and cvd_bullish
            bear_pullback = is_strong_downtrend and (high >= ema_20) and (close < ema_20) and (rsi_14 > 50) and cvd_bearish
            
            # --- 5. V-Bottom/Top Sweep (Capitulation) ---
            bbands_wide = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2.5)
            bbl_wide = bbands_wide.bollinger_lband().iloc[-2]
            bbu_wide = bbands_wide.bollinger_hband().iloc[-2]
            
            vol_ma = df['volume'].rolling(window=20).mean().iloc[-2]
            volume = df['volume'].iloc[-2]
            vol_spike = volume > (vol_ma * 2.0)
            candle_range = high - low
            
            v_bottom_sweep = (low < bbl_wide) and ((close - low) > (candle_range * 0.5)) and vol_spike
            v_top_sweep = (high > bbu_wide) and ((high - close) > (candle_range * 0.5)) and vol_spike
            
            # --- 6. Momentum Ignition ---
            recent_high = df['high'].rolling(10).max().shift(1).iloc[-2]
            recent_low = df['low'].rolling(10).min().shift(1).iloc[-2]
            atr_val = df['atr'].iloc[-2]
            
            ignition_long = (candle_range >= atr_val * 1.5) and (close > recent_high) and ((high - close) < (candle_range * 0.2)) and cvd_bullish
            ignition_short = (candle_range >= atr_val * 1.5) and (close < recent_low) and ((close - low) < (candle_range * 0.2)) and cvd_bearish
            
            # --- KARAR MEKANİZMASI (OR Kapıları) ---
            if trend_dir == 'BULLISH':
                if squeeze_fired and cvd_bullish:
                    return {"valid": True, "reason": "Squeeze Release + CVD Onaylı"}
                if bull_pullback:
                    return {"valid": True, "reason": "ADX Raging Bull Pullback"}
                if v_bottom_sweep:
                    return {"valid": True, "reason": "V-Bottom Liquidation Sweep"}
                if ignition_long:
                    return {"valid": True, "reason": "Momentum Ignition Breakout"}
            
            elif trend_dir == 'BEARISH':
                if squeeze_fired and cvd_bearish:
                    return {"valid": True, "reason": "Squeeze Release + CVD Onaylı"}
                if bear_pullback:
                    return {"valid": True, "reason": "ADX Raging Bear Pullback"}
                if v_top_sweep:
                    return {"valid": True, "reason": "V-Top Liquidation Sweep"}
                if ignition_short:
                    return {"valid": True, "reason": "Momentum Ignition Breakout"}
            
            return {"valid": False, "reason": "Testere Piyasası (Hiçbir Abduktif Rejim Onayı Yok)"}
            
        except Exception as e:
            logger.error(f"Abductive Filter Hatası: {e}")
            return {"valid": False, "reason": f"Hata: {e}"}
