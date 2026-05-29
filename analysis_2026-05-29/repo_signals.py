"""
repo_signals.py
================
Tirad reposundaki live_scan.py içindeki sinyal fonksiyonlarının BİREBİR
(verbatim) kopyası. Amaç: backtest'in gerçekçiliğini test ederken botun
GERÇEK karar mantığını kullanmak — yeniden yazılmış/sadeleştirilmiş değil.

Kopyalanan fonksiyonlar:
  - ema, atr_fn          (live_scan.py:175-184)
  - swing_pivots         (live_scan.py:187-194)
  - market_structure     (live_scan.py:196-246)
  - order_blocks         (live_scan.py:249-296)

Bu sayede "buggy" (rapor metodolojisi) ile "honest" (düzeltilmiş) backtest
TAM OLARAK AYNI sinyalleri kullanır; tek fark işlem doldurma/muhasebe katmanı.
"""
import numpy as np
import pandas as pd


# ─── live_scan.py:175 ───────────────────────────────────────────
def ema(s, p):
    return s.ewm(span=p, adjust=False).mean()


# ─── live_scan.py:181 ───────────────────────────────────────────
def atr_fn(df, p=14):
    h = df["high"]; l = df["low"]; c = df["close"].shift(1)
    tr = pd.concat([h - l, (h - c).abs(), (l - c).abs()], axis=1).max(axis=1)
    return tr.rolling(p).mean()


# ─── live_scan.py:187 ───────────────────────────────────────────
def swing_pivots(df, lb=10):
    sh = pd.Series(False, index=df.index); sl = pd.Series(False, index=df.index)
    for i in range(lb, len(df) - 1):
        wh = df["high"].iloc[i - lb:i + 1]; wl = df["low"].iloc[i - lb:i + 1]
        if df["high"].iloc[i] == wh.max(): sh.iloc[i] = True
        if df["low"].iloc[i] == wl.min(): sl.iloc[i] = True
    return sh, sl


# ─── live_scan.py:196 ───────────────────────────────────────────
def market_structure(df, lb=10):
    sh, sl = swing_pivots(df, lb)
    sh_vals = df["high"][sh]; sl_vals = df["low"][sl]

    if len(sh_vals) < 3 or len(sl_vals) < 3:
        return {"trend": "NEUTRAL", "bos_bull": False, "bos_bear": False,
                "choch_bull": False, "choch_bear": False, "mss_bull": False, "mss_bear": False,
                "hh": False, "hl": False, "lh": False, "ll": False,
                "last_sh": None, "last_sl": None}

    hh = sh_vals.iloc[-1] > sh_vals.iloc[-2]
    hl = sl_vals.iloc[-1] > sl_vals.iloc[-2]
    lh = sh_vals.iloc[-1] < sh_vals.iloc[-2]
    ll = sl_vals.iloc[-1] < sl_vals.iloc[-2]

    trend = "NEUTRAL"
    if hh and hl: trend = "BULLISH"
    elif lh and ll: trend = "BEARISH"

    rc = df["close"].iloc[-4:-1]
    last_sh = float(sh_vals.iloc[-1]); last_sl = float(sl_vals.iloc[-1])

    bos_bull = bool((rc > last_sh).all()) and trend == "BULLISH"
    bos_bear = bool((rc < last_sl).all()) and trend == "BEARISH"

    return {"trend": trend, "bos_bull": bos_bull, "bos_bear": bos_bear,
            "hh": hh, "hl": hl, "lh": lh, "ll": ll,
            "last_sh": last_sh, "last_sl": last_sl}


# ─── live_scan.py:249 ───────────────────────────────────────────
def order_blocks(df, n=3):
    c = df["close"]; o = df["open"]; h = df["high"]; l = df["low"]
    atr = atr_fn(df); blocks = []
    end = len(df) - n - 1; start = max(0, end - 80)
    avg_move = ((c - o).abs()).rolling(20).mean()

    for i in range(start, end):
        nxt = c.iloc[i + 1:i + 1 + n]
        if len(nxt) < n: continue
        bar_sz = abs(c.iloc[i] - o.iloc[i])
        avg = avg_move.iloc[i]
        is_impulse = avg > 0 and bar_sz > avg * 1.3
        if not is_impulse: continue

        # Bullish OB
        if nxt.iloc[-1] > nxt.iloc[0] and c.iloc[i] < o.iloc[i]:
            ob_low = float(l.iloc[i]); ob_high = float(h.iloc[i])
            subsequent = l.iloc[i + n:]
            breaker = any(subsequent < ob_low)
            blocks.append({"type": "bullish", "low": ob_low, "high": ob_high,
                           "mid": (ob_low + ob_high) / 2, "idx": i, "breaker": breaker,
                           "bars_ago": len(df) - i})
        # Bearish OB
        elif nxt.iloc[-1] < nxt.iloc[0] and c.iloc[i] > o.iloc[i]:
            ob_low = float(l.iloc[i]); ob_high = float(h.iloc[i])
            subsequent = h.iloc[i + n:]
            breaker = any(subsequent > ob_high)
            blocks.append({"type": "bearish", "low": ob_low, "high": ob_high,
                           "mid": (ob_low + ob_high) / 2, "idx": i, "breaker": breaker,
                           "bars_ago": len(df) - i})

    valid = [b for b in blocks if not b["breaker"]]
    bull_obs = sorted([b for b in valid if b["type"] == "bullish"], key=lambda x: x["bars_ago"])
    bear_obs = sorted([b for b in valid if b["type"] == "bearish"], key=lambda x: x["bars_ago"])
    return bull_obs[:3], bear_obs[:3]


# ─── S3 sinyali (rapor §3.1): EMA200 trend + taze Order Block ───
def s3_signal(df_slice):
    """
    Rapordaki 'S3 (Trend + Order Block Only)' sinyali — birebir tarif:
        LONG : close > EMA200  AND taze bullish OB var
        SHORT: close < EMA200  AND taze bearish OB var
    Döner: (direction, ob)  ya da (None, None)
    df_slice = SADECE kapanmış mumlar (geleceği görmez).
    """
    if len(df_slice) < 210:
        return None, None
    close = df_slice["close"]
    ema200 = float(ema(close, 200).iloc[-1])
    cp = float(close.iloc[-1])
    bull_obs, bear_obs = order_blocks(df_slice)

    if cp > ema200 and bull_obs:
        return "LONG", bull_obs[0]
    if cp < ema200 and bear_obs:
        return "SHORT", bear_obs[0]
    return None, None
