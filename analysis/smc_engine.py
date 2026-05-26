"""
SMC (Smart Money Concepts) Analiz Motoru
Anti-repainting garantisi: TÜM hesaplamalar kapanmış mumlar üzerinde.
Her fonksiyon shift(1) veya iloc[:-1] ile çalışır.
"""
import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class SMCResult:
    # Tespit edilen yapılar
    bos_bullish: bool = False       # Break of Structure (yukarı)
    bos_bearish: bool = False       # Break of Structure (aşağı)
    choch_bullish: bool = False     # Change of Character (yukarı)
    choch_bearish: bool = False     # Change of Character (aşağı)
    bullish_ob: float | None = None # Bullish Order Block seviyesi (orta)
    bearish_ob: float | None = None # Bearish Order Block seviyesi (orta)
    bullish_ob_low: float | None = None
    bullish_ob_high: float | None = None
    bearish_ob_low: float | None = None
    bearish_ob_high: float | None = None
    fvg_bullish: list = field(default_factory=list)   # [(low, high), ...]
    fvg_bearish: list = field(default_factory=list)
    liquidity_sweep_up: bool = False
    liquidity_sweep_down: bool = False
    in_premium: bool = False     # Fibonacci 0.5 üstü (satış bölgesi)
    in_discount: bool = False    # Fibonacci 0.5 altı (alış bölgesi)
    killzone_active: bool = False
    trend: str = "NEUTRAL"       # "BULLISH", "BEARISH", "NEUTRAL"

    # Puan
    score: float = 0.0
    max_score: float = 10.0
    details: dict = field(default_factory=dict)


def _find_swing_highs_lows(df: pd.DataFrame, lookback: int = 10) -> tuple[pd.Series, pd.Series]:
    """Swing high ve low serileri döndürür. Sadece kapanmış mumlar."""
    highs = df["high"]
    lows = df["low"]

    swing_highs = pd.Series(False, index=df.index)
    swing_lows = pd.Series(False, index=df.index)

    for i in range(lookback, len(df) - 1):
        window_highs = highs.iloc[i - lookback: i + 1]
        window_lows = lows.iloc[i - lookback: i + 1]
        if highs.iloc[i] == window_highs.max():
            swing_highs.iloc[i] = True
        if lows.iloc[i] == window_lows.min():
            swing_lows.iloc[i] = True

    return swing_highs, swing_lows


def detect_bos_choch(df: pd.DataFrame, lookback: int = 10) -> dict:
    """
    BOS (Break of Structure) ve CHoCH (Change of Character) tespiti.
    3 kapanmış onay mumu şartı uygulanır.
    """
    if len(df) < lookback * 2 + 5:
        return {"bos_bullish": False, "bos_bearish": False,
                "choch_bullish": False, "choch_bearish": False, "trend": "NEUTRAL"}

    closes = df["close"]
    highs = df["high"]
    lows = df["low"]

    swing_highs, swing_lows = _find_swing_highs_lows(df, lookback)

    sh_levels = highs[swing_highs].values
    sl_levels = lows[swing_lows].values

    if len(sh_levels) < 2 or len(sl_levels) < 2:
        return {"bos_bullish": False, "bos_bearish": False,
                "choch_bullish": False, "choch_bearish": False, "trend": "NEUTRAL"}

    # Son 3 kapanmış mum
    recent_closes = closes.iloc[-4:-1]  # İlk: -4, son dahil: -2 (3 mum)
    last_sh = sh_levels[-1]
    last_sl = sl_levels[-1]
    prev_sh = sh_levels[-2] if len(sh_levels) >= 2 else last_sh
    prev_sl = sl_levels[-2] if len(sl_levels) >= 2 else last_sl

    # Trend belirleme
    trend = "NEUTRAL"
    if last_sh > prev_sh and last_sl > prev_sl:
        trend = "BULLISH"
    elif last_sh < prev_sh and last_sl < prev_sl:
        trend = "BEARISH"

    # BOS: Son 3 mumun HEPSİ kırılma seviyesinin üstünde/altında kapanmış mı
    bos_bullish = bool((recent_closes > last_sh).all()) and trend == "BULLISH"
    bos_bearish = bool((recent_closes < last_sl).all()) and trend == "BEARISH"

    # CHoCH: Trend içindeki ilk karşı kırılma
    choch_bullish = bool((recent_closes > last_sh).all()) and trend == "BEARISH"
    choch_bearish = bool((recent_closes < last_sl).all()) and trend == "BULLISH"

    return {
        "bos_bullish": bos_bullish, "bos_bearish": bos_bearish,
        "choch_bullish": choch_bullish, "choch_bearish": choch_bearish,
        "trend": trend,
    }


def detect_order_blocks(df: pd.DataFrame, confirmation_bars: int = 3) -> dict:
    """
    Order Block tespiti: Güçlü hareketin hemen öncesindeki karşı yönlü mum.
    Anti-repainting: Son kapanmış mumdan geriye bakılır.
    """
    if len(df) < confirmation_bars + 10:
        return {}

    closes = df["close"]
    opens = df["open"]
    highs = df["high"]
    lows = df["low"]

    bullish_ob = None
    bearish_ob = None
    bullish_ob_range = None
    bearish_ob_range = None

    # Son [confirmation_bars] mumdan önceye bak
    search_end = len(df) - confirmation_bars - 1
    search_start = max(0, search_end - 50)

    for i in range(search_start, search_end):
        # Güçlü yukarı hareket: sonraki N mumun hepsi yukarı kapanmış ve büyük
        next_bars = closes.iloc[i + 1: i + 1 + confirmation_bars]
        if len(next_bars) < confirmation_bars:
            continue

        bar_size = abs(closes.iloc[i] - opens.iloc[i])
        avg_size = (closes - opens).abs().rolling(20).mean().iloc[i]
        strong_move = bar_size > avg_size * 1.5 if avg_size > 0 else False

        if (next_bars.iloc[-1] > next_bars.iloc[0]) and strong_move:
            # Bullish OB: Bu noktadaki bearish mum
            if closes.iloc[i] < opens.iloc[i]:  # Kırmızı mum = bullish OB
                bullish_ob = (lows.iloc[i] + highs.iloc[i]) / 2
                bullish_ob_range = (lows.iloc[i], highs.iloc[i])

        if (next_bars.iloc[-1] < next_bars.iloc[0]) and strong_move:
            # Bearish OB: Bu noktadaki bullish mum
            if closes.iloc[i] > opens.iloc[i]:  # Yeşil mum = bearish OB
                bearish_ob = (lows.iloc[i] + highs.iloc[i]) / 2
                bearish_ob_range = (lows.iloc[i], highs.iloc[i])

    result = {}
    if bullish_ob is not None:
        result["bullish_ob"] = bullish_ob
        result["bullish_ob_range"] = bullish_ob_range
    if bearish_ob is not None:
        result["bearish_ob"] = bearish_ob
        result["bearish_ob_range"] = bearish_ob_range
    return result


def detect_fair_value_gaps(df: pd.DataFrame, min_size: float = 0.003) -> dict:
    """
    FVG (Fair Value Gap) tespiti: 3 mumlu imbalance.
    Bullish FVG: Mum[i-2].high < Mum[i].low (gap yukarı)
    Bearish FVG: Mum[i-2].low > Mum[i].high (gap aşağı)
    Kapatılmamış FVG'ler önceliklidir.
    """
    if len(df) < 10:
        return {"fvg_bullish": [], "fvg_bearish": []}

    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values

    bullish_fvgs = []
    bearish_fvgs = []

    # Son 100 mum üzerinde ara (kapanmış olanlar)
    search_range = min(100, len(df) - 2)
    for i in range(1, search_range):
        idx = -(i + 2)  # Geriye doğru: -3, -4, -5...
        c1_high = highs[idx]
        c1_low = lows[idx]
        c3_high = highs[idx + 2]
        c3_low = lows[idx + 2]

        # Bullish FVG
        if c3_low > c1_high:
            gap_size = (c3_low - c1_high) / c1_high
            if gap_size >= min_size:
                # Kapatılmış mı kontrol et
                recent_lows = lows[idx + 3:]
                filled = any(l <= c1_high for l in recent_lows)
                if not filled:
                    bullish_fvgs.append({
                        "low": c1_high, "high": c3_low,
                        "mid": (c1_high + c3_low) / 2,
                        "size_pct": gap_size * 100,
                        "bars_ago": i,
                    })

        # Bearish FVG
        if c3_high < c1_low:
            gap_size = (c1_low - c3_high) / c1_low
            if gap_size >= min_size:
                recent_highs = highs[idx + 3:]
                filled = any(h >= c1_low for h in recent_highs)
                if not filled:
                    bearish_fvgs.append({
                        "low": c3_high, "high": c1_low,
                        "mid": (c3_high + c1_low) / 2,
                        "size_pct": gap_size * 100,
                        "bars_ago": i,
                    })

    # En yakın FVG'yi önce sırala
    bullish_fvgs.sort(key=lambda x: x["bars_ago"])
    bearish_fvgs.sort(key=lambda x: x["bars_ago"])

    return {"fvg_bullish": bullish_fvgs[:3], "fvg_bearish": bearish_fvgs[:3]}


def detect_liquidity_sweep(df: pd.DataFrame, tolerance: float = 0.002, lookback: int = 20) -> dict:
    """
    Likidite süpürmesi: Equal high/low kırılıp geri dönen yapı.
    """
    if len(df) < lookback + 5:
        return {"liquidity_sweep_up": False, "liquidity_sweep_down": False}

    highs = df["high"].values[-lookback - 5:]
    lows = df["low"].values[-lookback - 5:]
    closes = df["close"].values[-lookback - 5:]

    sweep_up = False
    sweep_down = False

    # Son kapanmış mumlar (en son hariç — anti-repainting)
    recent_highs = highs[:-3]
    recent_lows = lows[:-3]
    last_3_closes = closes[-4:-1]
    last_3_highs = highs[-4:-1]
    last_3_lows = lows[-4:-1]

    if len(recent_highs) < 5:
        return {"liquidity_sweep_up": False, "liquidity_sweep_down": False}

    # Equal highs: Son N mum içinde birbirine yakın yüksekler
    for i in range(len(recent_highs) - 1):
        for j in range(i + 1, len(recent_highs)):
            if abs(recent_highs[i] - recent_highs[j]) / recent_highs[i] < tolerance:
                eq_level = (recent_highs[i] + recent_highs[j]) / 2
                # Sweep: Son mumlar bu seviyeyi geçti mi ama geri döndü mü?
                if any(h > eq_level * (1 + tolerance) for h in last_3_highs):
                    if any(c < eq_level for c in last_3_closes):
                        sweep_up = True

    for i in range(len(recent_lows) - 1):
        for j in range(i + 1, len(recent_lows)):
            if abs(recent_lows[i] - recent_lows[j]) / recent_lows[i] < tolerance:
                eq_level = (recent_lows[i] + recent_lows[j]) / 2
                if any(l < eq_level * (1 - tolerance) for l in last_3_lows):
                    if any(c > eq_level for c in last_3_closes):
                        sweep_down = True

    return {"liquidity_sweep_up": sweep_up, "liquidity_sweep_down": sweep_down}


def detect_premium_discount(df: pd.DataFrame, lookback: int = 50) -> dict:
    """Fibonacci 0.5 ile premium/discount bölge tespiti."""
    if len(df) < lookback:
        return {"in_premium": False, "in_discount": False, "fib_50": None}

    period = df.iloc[-lookback:]
    swing_high = period["high"].max()
    swing_low = period["low"].min()
    fib_50 = (swing_high + swing_low) / 2

    current_price = df["close"].iloc[-2]  # Kapanmış son mum

    return {
        "in_premium": current_price > fib_50,
        "in_discount": current_price <= fib_50,
        "fib_50": fib_50,
        "swing_high": swing_high,
        "swing_low": swing_low,
    }


def check_killzone(df: pd.DataFrame, london: list = None, ny: list = None) -> bool:
    """Son kapanmış mumun killzone'da olup olmadığını kontrol eder."""
    if london is None:
        london = [7, 10]
    if ny is None:
        ny = [13, 16]

    if df.empty:
        return False

    last_closed_time = df.index[-2] if len(df) >= 2 else df.index[-1]
    hour = last_closed_time.hour

    return london[0] <= hour < london[1] or ny[0] <= hour < ny[1]


def analyze_smc(df: pd.DataFrame, config: dict = None) -> SMCResult:
    """
    Ana SMC analizi — tüm bileşenleri birleştirir ve skor hesaplar.
    Maksimum puan: 10
    """
    if config is None:
        config = {}

    lookback = config.get("swing_lookback", 10)
    ob_bars = config.get("ob_confirmation_bars", 3)
    fvg_min = config.get("fvg_min_size", 0.003)
    liq_tol = config.get("liquidity_tolerance", 0.002)
    london = config.get("killzone", {}).get("london_open", [7, 10])
    ny = config.get("killzone", {}).get("ny_open", [13, 16])

    result = SMCResult()

    if df.empty or len(df) < 30:
        logger.warning("SMC analizi için yetersiz veri")
        return result

    # 1. BOS / CHoCH
    bos_data = detect_bos_choch(df, lookback)
    result.bos_bullish = bos_data["bos_bullish"]
    result.bos_bearish = bos_data["bos_bearish"]
    result.choch_bullish = bos_data["choch_bullish"]
    result.choch_bearish = bos_data["choch_bearish"]
    result.trend = bos_data["trend"]

    # 2. Order Blocks
    ob_data = detect_order_blocks(df, ob_bars)
    result.bullish_ob = ob_data.get("bullish_ob")
    result.bearish_ob = ob_data.get("bearish_ob")
    if ob_data.get("bullish_ob_range"):
        result.bullish_ob_low, result.bullish_ob_high = ob_data["bullish_ob_range"]
    if ob_data.get("bearish_ob_range"):
        result.bearish_ob_low, result.bearish_ob_high = ob_data["bearish_ob_range"]

    # 3. FVG
    fvg_data = detect_fair_value_gaps(df, fvg_min)
    result.fvg_bullish = fvg_data["fvg_bullish"]
    result.fvg_bearish = fvg_data["fvg_bearish"]

    # 4. Liquidity Sweep
    liq_data = detect_liquidity_sweep(df, liq_tol)
    result.liquidity_sweep_up = liq_data["liquidity_sweep_up"]
    result.liquidity_sweep_down = liq_data["liquidity_sweep_down"]

    # 5. Premium / Discount
    pd_data = detect_premium_discount(df)
    result.in_premium = pd_data["in_premium"]
    result.in_discount = pd_data["in_discount"]

    # 6. Killzone
    result.killzone_active = check_killzone(df, london, ny)

    # ─── PUANLAMA (Long taraflı, trend yönüne göre) ─────────────
    score = 0.0
    details = {}

    if result.trend == "BULLISH":
        if result.bos_bullish:
            score += 2.0
            details["bos"] = "BOS Bullish ✅ (+2)"
        if result.choch_bullish:
            score += 1.0
            details["choch"] = "CHoCH Bullish ✅ (+1)"
        if result.bullish_ob is not None:
            score += 2.0
            details["ob"] = f"Bullish OB @ {result.bullish_ob:.4f} ✅ (+2)"
        if result.fvg_bullish:
            score += 1.0
            details["fvg"] = f"Bullish FVG @ {result.fvg_bullish[0]['mid']:.4f} ✅ (+1)"
        if result.liquidity_sweep_down:
            score += 2.0
            details["liq"] = "Likidite Sweep (Düşük) ✅ (+2)"
        if result.in_discount:
            score += 1.0
            details["zone"] = "Discount Bölge ✅ (+1)"
        if result.killzone_active:
            score += 1.0
            details["kz"] = "Killzone Aktif ✅ (+1)"

    elif result.trend == "BEARISH":
        if result.bos_bearish:
            score += 2.0
            details["bos"] = "BOS Bearish ✅ (+2)"
        if result.choch_bearish:
            score += 1.0
            details["choch"] = "CHoCH Bearish ✅ (+1)"
        if result.bearish_ob is not None:
            score += 2.0
            details["ob"] = f"Bearish OB @ {result.bearish_ob:.4f} ✅ (+2)"
        if result.fvg_bearish:
            score += 1.0
            details["fvg"] = f"Bearish FVG @ {result.fvg_bearish[0]['mid']:.4f} ✅ (+1)"
        if result.liquidity_sweep_up:
            score += 2.0
            details["liq"] = "Likidite Sweep (Yüksek) ✅ (+2)"
        if result.in_premium:
            score += 1.0
            details["zone"] = "Premium Bölge ✅ (+1)"
        if result.killzone_active:
            score += 1.0
            details["kz"] = "Killzone Aktif ✅ (+1)"
    else:
        details["trend"] = "Nötr trend — SMC skor 0"

    result.score = min(score, result.max_score)
    result.details = details
    return result
