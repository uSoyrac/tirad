"""
bist_engine.py — BIST (Borsa İstanbul) Spot Motor
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Kripto motoru ile paralel çalışır, BIST'e özgü kuralları uygular:

  • Kaldıraç: 1x (Spot — kaldıraçlı BIST mevcut değil)
  • Tavan/Taban: %10 günlük limit (devre kesici) → özel FVG gibi
  • Seans Saatleri: 10:00–18:00 İstanbul (UTC+3) → hafta içi
  • Hafta Sonu Gap: Cuma 18:00 – Pazartesi 10:00 arası gap = FVG
  • Veri Kaynağı: yfinance (THYAO.IS, ASELS.IS, GARAN.IS ...)
  • Para Birimi: TRY (Türk Lirası)
  • İşlem Boyutu: Nominal × lot büyüklüğü (100 hisse/lot)

Desteklenen hisseler için watchlist:
  BIST_100 endeksinden önemli likit hisseler.

Kullanım:
  from bist_engine import analyze_bist, scan_bist_watchlist
  result = analyze_bist("THYAO.IS")
"""

import logging
import math
import warnings
from datetime import datetime, timedelta, time as dtime
from typing import Optional, List

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")
logger = logging.getLogger("bist_engine")

# ══════════════════════════════════════════════════════════════════════
#  YAPILANDIRMA
# ══════════════════════════════════════════════════════════════════════

BIST_TIMEZONE_OFFSET = 3    # UTC+3 (İstanbul)
SESSION_OPEN  = dtime(10, 0)
SESSION_CLOSE = dtime(18, 0)
CIRCUIT_BREAKER_PCT = 0.10  # %10 tavan/taban
LOT_SIZE   = 100            # 1 lot = 100 hisse
MIN_VOLUME = 50_000         # Minimum günlük hacim (TRY)

# BIST-100'den en likit / volatil hisseler
BIST_WATCHLIST = [
    "THYAO.IS",   # Türk Hava Yolları
    "ASELS.IS",   # Aselsan
    "GARAN.IS",   # Garanti Bankası
    "SASA.IS",    # Sasa Polyester
    "KCHOL.IS",   # Koç Holding
    "TUPRS.IS",   # Tüpraş
    "EREGL.IS",   # Ereğli Demir
    "BIMAS.IS",   # BİM Mağazalar
    "AKBNK.IS",   # Akbank
    "YKBNK.IS",   # Yapı Kredi
    "FROTO.IS",   # Ford Otosan
    "TOASO.IS",   # Tofaş
    "VESTL.IS",   # Vestel
    "PGSUS.IS",   # Pegasus
    "SAHOL.IS",   # Sabancı Holding
    "KONTR.IS",   # Kontrolmatik
    "KOZAL.IS",   # Koza Altın
    "EKGYO.IS",   # Emlak Konut
    "TAVHL.IS",   # TAV Havalimanları
    "SISE.IS",    # Şişecam
]


# ══════════════════════════════════════════════════════════════════════
#  VERİ ÇEKME
# ══════════════════════════════════════════════════════════════════════

def fetch_bist_data(symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """
    yfinance ile BIST verisi çeker.
    symbol: "THYAO.IS" formatında.
    Döner: OHLCV DataFrame veya boş DataFrame.
    """
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()

        df.index = pd.to_datetime(df.index).tz_localize(None)
        df.columns = df.columns.str.lower()
        df = df[["open", "high", "low", "close", "volume"]].dropna()

        # Minimum hacim filtresi
        if df["volume"].mean() < MIN_VOLUME:
            logger.debug(f"{symbol}: Düşük hacim filtresi")
            return pd.DataFrame()

        return df.astype(float)
    except Exception as e:
        logger.warning(f"BIST veri çekme hatası ({symbol}): {e}")
        return pd.DataFrame()


# ══════════════════════════════════════════════════════════════════════
#  BIST'E ÖZGÜ GÖSTERGELER
# ══════════════════════════════════════════════════════════════════════

def bist_circuit_breaker(df: pd.DataFrame) -> dict:
    """
    Tavan/Taban Analizi.

    BIST kuralı:
      • Tavan (Upper Limit): Önceki gün kapanışın %10 üstü
      • Taban (Lower Limit): Önceki gün kapanışın %10 altı
      • Tavan/Tabana yakın fiyat → işlem kısıtlanabilir

    Sinyal:
      • Fiyat tavana %2'den yakın → satış sinyali (artık yükselme yok)
      • Fiyat tabana %2'den yakın → alım sinyali (dip reversal)
      • Fiyat tavan/tabanda → FVG benzeri: ertesi gün gap beklenir
    """
    if len(df) < 2:
        return {"at_circuit": False, "near_upper": False, "near_lower": False,
                "circuit_score": 0.0}

    prev_close = float(df["close"].iloc[-2])
    last_close = float(df["close"].iloc[-1])
    last_high  = float(df["high"].iloc[-1])

    upper_limit = prev_close * (1 + CIRCUIT_BREAKER_PCT)
    lower_limit = prev_close * (1 - CIRCUIT_BREAKER_PCT)

    at_upper   = last_high >= upper_limit * 0.995
    at_lower   = float(df["low"].iloc[-1]) <= lower_limit * 1.005
    near_upper = last_close >= upper_limit * 0.98  # %2 yakın
    near_lower = last_close <= lower_limit * 1.02

    at_circuit = at_upper or at_lower
    circuit_score = 0.0

    if near_lower:
        circuit_score = 2.5  # Tabana yakın = alım fırsatı
    elif near_upper:
        circuit_score = -2.0  # Tavana yakın = satış sinyali
    elif at_lower:
        circuit_score = 3.0  # Taban = güçlü reversal beklentisi
    elif at_upper:
        circuit_score = -1.5  # Tavan = momentum durabilir

    return {
        "upper_limit":    round(upper_limit, 2),
        "lower_limit":    round(lower_limit, 2),
        "at_upper":       at_upper,
        "at_lower":       at_lower,
        "near_upper":     near_upper,
        "near_lower":     near_lower,
        "at_circuit":     at_circuit,
        "circuit_score":  round(circuit_score, 2),
    }


def bist_weekend_gap(df: pd.DataFrame) -> dict:
    """
    Hafta Sonu Gap Analizi.

    BIST Cuma 18:00'de kapanır, Pazartesi 10:00'de açılır.
    Hafta sonu gap = FVG gibi davranır:
      • Pozitif gap (Pazartesi açılış > Cuma kapanış) → boğa FVG
      • Negatif gap (Pazartesi açılış < Cuma kapanış) → ayı FVG
      • Gap genellikle 1-3 seans içinde dolmaya çalışır (gap-fill trade)

    Not: Yfinance günlük veri kullandığımız için hafta sonu fark
    index'teki cumartesi/pazar yokluğundan çıkar.
    """
    if len(df) < 5:
        return {"gap_detected": False, "gap_type": "NONE", "gap_size_pct": 0,
                "gap_score": 0.0}

    # Son Pazartesi'yi bul (haftanın ilk işlem günü)
    # yfinance ile: Pazartesi önceki gün Cuma
    gaps = []
    for i in range(1, min(10, len(df))):
        curr_open  = float(df["open"].iloc[-i])
        prev_close = float(df["close"].iloc[-i - 1])
        curr_date  = df.index[-i]

        gap_pct = (curr_open - prev_close) / prev_close * 100

        # Büyük gap kontrolü (>0.5%)
        if abs(gap_pct) > 0.5:
            gaps.append({
                "date":     str(curr_date)[:10],
                "gap_pct":  round(gap_pct, 2),
                "type":     "BULL" if gap_pct > 0 else "BEAR",
                "bars_ago": i,
            })

    if not gaps:
        return {"gap_detected": False, "gap_type": "NONE", "gap_size_pct": 0,
                "gap_score": 0.0}

    latest_gap = gaps[0]
    gap_score = 0.0

    # Gap-fill trade: gap yönü ile devam veya dönüş?
    # Son kapanış gap seviyesine döndü mü?
    if latest_gap["type"] == "BULL":
        gap_score = 1.0
    elif latest_gap["type"] == "BEAR":
        gap_score = -1.0

    return {
        "gap_detected":  True,
        "gap_type":      latest_gap["type"],
        "gap_size_pct":  latest_gap["gap_pct"],
        "gap_date":      latest_gap["date"],
        "all_gaps":      gaps[:3],
        "gap_score":     round(gap_score, 2),
    }


def bist_session_check() -> dict:
    """
    BIST seans saatlerini kontrol eder (UTC+3).
    İşlem zamanı değilse sinyal daha az güvenilir.
    """
    now_utc   = datetime.utcnow()
    now_ist   = now_utc + timedelta(hours=BIST_TIMEZONE_OFFSET)
    now_time  = now_ist.time()
    weekday   = now_ist.weekday()  # 0=Pazartesi, 6=Pazar

    is_weekday = weekday < 5  # Pazartesi-Cuma
    in_session = is_weekday and SESSION_OPEN <= now_time <= SESSION_CLOSE

    return {
        "now_istanbul":  now_ist.strftime("%H:%M"),
        "is_weekday":    is_weekday,
        "in_session":    in_session,
        "session_open":  SESSION_OPEN.strftime("%H:%M"),
        "session_close": SESSION_CLOSE.strftime("%H:%M"),
    }


# ══════════════════════════════════════════════════════════════════════
#  SMC ANALİZİ (BIST UYARLAMASI)
# ══════════════════════════════════════════════════════════════════════

def bist_smc_score(df: pd.DataFrame) -> dict:
    """
    BIST için uyarlanmış SMC analizi.
    live_scan.py motorunu çağırır ama BIST'e özgü ayarlarla.

    Farklılıklar:
      • is_bist=True → BIST modu (farklı OB eşikleri, hacim normalizasyon)
      • Kaldıraç 1x (her zaman)
      • SL mesafesi: %3-8 (BIST daha volatil spot, daha geniş SL)
      • TP hedefleri: TP1=%8, TP2=%18, TP3=%35 (kripto'dan farklı)
    """
    try:
        from live_scan import analyze
        result = analyze(df.index[-1] if hasattr(df.index[-1], "strftime") else "BIST",
                         is_bist=True, df_override=df)
        return result or {}
    except Exception as e:
        logger.debug(f"BIST SMC analizi hatası: {e}")
        return {}


def bist_classic_indicators(df: pd.DataFrame) -> dict:
    """
    BIST için klasik teknik analiz.
    EMA, RSI, MACD — kripto ile aynı mantık.
    """
    if len(df) < 55:
        return {}

    close = df["close"]

    def ema(s, p): return s.ewm(span=p, adjust=False).mean()

    e8  = float(ema(close, 8).iloc[-1])
    e21 = float(ema(close, 21).iloc[-1])
    e55 = float(ema(close, 55).iloc[-1])
    e200= float(ema(close, 200).iloc[-1]) if len(df) >= 200 else e55

    # RSI
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rsi   = float((100 - 100 / (1 + gain / loss.replace(0, np.nan))).iloc[-1])

    # MACD
    ema12 = ema(close, 12); ema26 = ema(close, 26)
    macd  = ema12 - ema26
    sig   = ema(macd, 9)
    hist  = macd - sig

    last_price = float(close.iloc[-1])

    ema_bull = e8 > e21 > e55
    ema_bear = e8 < e21 < e55
    above_200 = last_price > e200
    macd_bull = float(macd.iloc[-1]) > float(sig.iloc[-1])
    macd_hist = float(hist.iloc[-1])

    # Puanlama
    score = 0.0
    if ema_bull:  score += 2.5
    elif ema_bear: score -= 2.5
    if above_200: score += 1.0
    else:         score -= 0.5
    if macd_bull: score += 1.5
    if rsi < 35:  score += 1.5  # Aşırı satım
    elif rsi > 70: score -= 1.5  # Aşırı alım
    if macd_hist > 0: score += 0.5

    return {
        "e8": e8, "e21": e21, "e55": e55, "e200": e200,
        "rsi": round(rsi, 1),
        "macd_hist": round(macd_hist, 4),
        "ema_bull": ema_bull,
        "ema_bear": ema_bear,
        "above_200": above_200,
        "macd_bull": macd_bull,
        "score": round(score, 2),
    }


# ══════════════════════════════════════════════════════════════════════
#  BIST POZİSYON BOYUTLANDIRMA (SPOT, 1x)
# ══════════════════════════════════════════════════════════════════════

def bist_position_size(
    capital_try:  float,
    entry_price:  float,
    sl_price:     float,
    risk_pct:     float = 0.02,
    lot_size:     int   = LOT_SIZE,
) -> dict:
    """
    BIST spot işlem için pozisyon boyutu hesaplar.

    Spot → 1x kaldıraç → lot bazında hesap.
    Risk = sermayenin %risk_pct'i kadar kayıp kabul edilir.
    SL = entry - SL mesafesi (long için)
    TP1/TP2/TP3 = BIST için daha geniş (volatilite fazla)

    TRY cinsinden hesap.
    """
    if entry_price <= 0 or sl_price <= 0:
        return {"valid": False, "reason": "Geçersiz fiyat"}

    sl_dist = abs(entry_price - sl_price) / entry_price
    if sl_dist < 0.02 or sl_dist > 0.12:
        return {"valid": False, "reason": f"SL mesafesi uygunsuz: {sl_dist:.1%}"}

    direction = "LONG" if entry_price > sl_price else "SHORT"
    risk_try  = capital_try * risk_pct
    max_loss_per_share = abs(entry_price - sl_price)
    shares_raw = risk_try / max_loss_per_share
    lots       = max(1, int(shares_raw / lot_size))
    shares     = lots * lot_size
    total_cost = shares * entry_price

    # Yeterli sermaye var mı?
    if total_cost > capital_try * 0.95:
        lots   = max(1, int(capital_try * 0.95 / (entry_price * lot_size)))
        shares = lots * lot_size
        total_cost = shares * entry_price

    # TP seviyeleri (BIST için daha geniş)
    TP1_PCT = 0.08; TP2_PCT = 0.18; TP3_PCT = 0.35
    if direction == "LONG":
        tp1 = entry_price * (1 + TP1_PCT)
        tp2 = entry_price * (1 + TP2_PCT)
        tp3 = entry_price * (1 + TP3_PCT)
    else:
        tp1 = entry_price * (1 - TP1_PCT)
        tp2 = entry_price * (1 - TP2_PCT)
        tp3 = entry_price * (1 - TP3_PCT)

    return {
        "valid":       True,
        "direction":   direction,
        "lots":        lots,
        "shares":      shares,
        "total_cost":  round(total_cost, 2),
        "risk_try":    round(risk_try, 2),
        "sl_pct":      round(sl_dist * 100, 2),
        "tp1":         round(tp1, 2),
        "tp2":         round(tp2, 2),
        "tp3":         round(tp3, 2),
        "leverage":    1,  # Her zaman 1x BIST spot
    }


# ══════════════════════════════════════════════════════════════════════
#  ANA ANALİZ FONKSİYONU
# ══════════════════════════════════════════════════════════════════════

def analyze_bist(symbol: str) -> Optional[dict]:
    """
    Tek bir BIST hissesi için tam analiz.

    Döner: {
        symbol, composite_score, trend, entry, sl, tp1..tp3,
        circuit, gap, session, classic, ...
    }
    """
    df = fetch_bist_data(symbol, period="2y", interval="1d")
    if df.empty or len(df) < 60:
        logger.debug(f"{symbol}: Yetersiz veri")
        return None

    # Klasik indikatörler
    cl = bist_classic_indicators(df)
    if not cl:
        return None

    # Devre kesici
    cb = bist_circuit_breaker(df)

    # Hafta sonu gap
    gap = bist_weekend_gap(df)

    # Seans bilgisi
    sess = bist_session_check()

    # Fiyat seviyeleri
    last_close  = float(df["close"].iloc[-1])
    last_volume = float(df["volume"].iloc[-1])
    avg_volume  = float(df["volume"].tail(20).mean())

    # Basit SMC giriş/SL hesabı (kripto motorunu çağır)
    # BIST için basit EMA tabanlı yön + ATR tabanlı SL
    atr = float((df["high"] - df["low"]).rolling(14).mean().iloc[-1])
    sl_buffer = atr * 1.5

    trend = "NEUTRAL"
    if cl["ema_bull"]:  trend = "BULLISH"
    elif cl["ema_bear"]: trend = "BEARISH"

    entry = last_close
    sl    = (entry - sl_buffer) if trend == "BULLISH" else (entry + sl_buffer)
    sl_pct = abs(entry - sl) / entry

    # SL çok yakın/uzak kontrolü
    if sl_pct < 0.02: sl = entry * (0.96 if trend == "BULLISH" else 1.04)
    if sl_pct > 0.10: sl = entry * (0.92 if trend == "BULLISH" else 1.08)

    # TP seviyeleri
    tp1 = entry * (1.08 if trend == "BULLISH" else 0.92)
    tp2 = entry * (1.18 if trend == "BULLISH" else 0.82)
    tp3 = entry * (1.35 if trend == "BULLISH" else 0.65)

    # Bileşik skor
    raw_score = cl["score"]
    raw_score += cb["circuit_score"]
    raw_score += gap["gap_score"]

    # Hacim konfirmasyonu
    volume_above_avg = last_volume > avg_volume * 1.2
    if volume_above_avg and trend == "BULLISH":  raw_score += 1.0
    if volume_above_avg and trend == "BEARISH":  raw_score -= 1.0

    # 0-10 normalize (max ≈ 12)
    composite = round(min(10.0, max(0.0, (raw_score + 6) / 12 * 10)), 2)

    return {
        "symbol":     symbol,
        "composite":  composite,
        "trend":      trend,
        "entry":      round(entry, 2),
        "sl":         round(sl, 2),
        "tp1":        round(tp1, 2),
        "tp2":        round(tp2, 2),
        "tp3":        round(tp3, 2),
        "last_close": round(last_close, 2),
        "volume":     int(last_volume),
        "vol_avg20":  int(avg_volume),
        "atr":        round(atr, 4),
        "classic":    cl,
        "circuit":    cb,
        "gap":        gap,
        "session":    sess,
        "is_bist":    True,
        "leverage":   1,
    }


# ══════════════════════════════════════════════════════════════════════
#  WATCHLIST TARAMA
# ══════════════════════════════════════════════════════════════════════

def scan_bist_watchlist(
    watchlist: List[str] = None,
    min_score: float = 5.5,
    direction_filter: str = "ALL",  # "BULLISH" / "BEARISH" / "ALL"
) -> List[dict]:
    """
    BIST watchlist'ini tarar ve sinyal üretenleri döner.
    Sıralama: composite_score'a göre azalan.
    """
    if watchlist is None:
        watchlist = BIST_WATCHLIST

    import time
    signals = []

    for symbol in watchlist:
        try:
            result = analyze_bist(symbol)
            if result is None:
                continue
            if result["composite"] >= min_score:
                if direction_filter == "ALL" or result["trend"] == direction_filter:
                    signals.append(result)
            time.sleep(0.5)  # yfinance rate limit
        except Exception as e:
            logger.debug(f"BIST tarama hatası ({symbol}): {e}")

    return sorted(signals, key=lambda x: x["composite"], reverse=True)


# ══════════════════════════════════════════════════════════════════════
#  TERMINAL ÇIKTISI
# ══════════════════════════════════════════════════════════════════════

def print_bist_signal(result: dict):
    """BIST sinyal çıktısı."""
    try:
        from live_scan import ok, bad, warn, nfo, dim, B, R
    except ImportError:
        B=R=""
        def ok(s): return s
        def bad(s): return s
        def warn(s): return s
        def nfo(s): return s
        def dim(s): return s

    sym    = result["symbol"].replace(".IS", "")
    score  = result["composite"]
    trend  = result["trend"]
    entry  = result["entry"]
    sl     = result["sl"]
    tp1    = result["tp1"]
    tp2    = result["tp2"]
    rsi    = result["classic"].get("rsi", 0)
    cb     = result["circuit"]
    gap    = result["gap"]
    sess   = result["session"]

    score_c = ok if score >= 7 else (warn if score >= 5 else dim)
    trend_c = ok if trend == "BULLISH" else (bad if trend == "BEARISH" else dim)
    sl_pct  = abs(entry - sl) / entry * 100

    print(f"\n  ┌{'─'*60}┐")
    print(f"  │  {B}{sym:8}{R}  {score_c(f'{score:.1f}/10')}  {trend_c(trend)}")
    print(f"  │  Giriş: {nfo(f'{entry:.2f} TRY')}  SL: {bad(f'{sl:.2f}')}"
          f"  ({sl_pct:.1f}%)  [1x SPOT]")
    print(f"  │  TP1: {ok(f'{tp1:.2f}')}  TP2: {ok(f'{tp2:.2f}')}")
    print(f"  │  RSI: {rsi:.0f}  "
          f"{'[TAVAN YAKINI ⚠]' if cb['near_upper'] else ''}"
          f"{'[TABAN YAKINI ✓]' if cb['near_lower'] else ''}")
    if gap["gap_detected"]:
        print(f"  │  Gap: {gap['gap_type']} {gap['gap_size_pct']:+.1f}%  ({gap.get('gap_date','')})")
    print(f"  │  Seans: {'✅ Açık' if sess['in_session'] else '⏰ Kapalı'}  ({sess['now_istanbul']})")
    print(f"  └{'─'*60}┘")


if __name__ == "__main__":
    print("BIST Tarama başlıyor...")
    session = bist_session_check()
    print(f"Seans: {session}")

    results = scan_bist_watchlist(
        watchlist=BIST_WATCHLIST[:5],
        min_score=4.0
    )

    if results:
        print(f"\n{len(results)} sinyal bulundu:\n")
        for r in results:
            print_bist_signal(r)
    else:
        print("Sinyal bulunamadı.")
