"""Order-flow feature laboratory — velocity (1st deriv) & acceleration (2nd deriv).

Thesis under test (the user's "Orderflow Exhaustion" idea, = institutional HFT logic):
a trend confirmed by RISING flow that is DECELERATING (2nd derivative < 0) is heading
into a fakeout. So for every flow variable we compute level, velocity, acceleration,
and a z-scored "above its own average" range — then ask (in feature_lab.py) whether
those derivatives separate true vs false trend entries OUT-OF-SAMPLE.

Everything is causal (rolling/diff/shift only). Honest data note: we have OHLCV+volume
(full), funding (3 exch, full), OI/LS/taker-ratio (2024-06+). We do NOT have true
CVD/aggTrades, liquidations, order-book, or VPVR history — those are PROXIED from
candles (signed volume, rolling VWAP) and clearly named *_proxy.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..indicators import atr, ema
from .. config import BacktestConfig  # noqa: E402,F401 (kept for type hints / future use)


def _rolling_ols(y: pd.Series, window: int) -> tuple[pd.Series, pd.Series]:
    """Causal rolling OLS of y on a time ramp. Returns (slope, r2) per bar.

    slope = trend strength over the window; r2 = trend CLEANLINESS (1 = perfectly
    linear trend, ~0 = chop). A principled 'real trend vs fakeout' pair.
    """
    from numpy.lib.stride_tricks import sliding_window_view

    yv = y.to_numpy(dtype=float)
    n = len(yv)
    slope = np.full(n, np.nan)
    r2 = np.full(n, np.nan)
    if n >= window:
        r = np.arange(window, dtype=float)
        rc = r - r.mean()
        sxx = (rc**2).sum()
        sw = sliding_window_view(yv, window)            # (n-window+1, window)
        ybar = sw.mean(axis=1)
        sl = (sw * rc).sum(axis=1) / sxx
        ss_tot = ((sw - ybar[:, None]) ** 2).sum(axis=1)
        ss_res = np.clip(ss_tot - sl**2 * sxx, 0.0, None)
        with np.errstate(divide="ignore", invalid="ignore"):
            rr = np.where(ss_tot > 0, 1.0 - ss_res / ss_tot, np.nan)
        slope[window - 1:] = sl
        r2[window - 1:] = rr
    return pd.Series(slope, index=y.index), pd.Series(r2, index=y.index)


def _vel_acc(s: pd.Series, k: int, prefix: str) -> dict:
    """Velocity (k-bar diff), acceleration (diff of velocity), and their z-scores."""
    vel = s.diff(k)
    acc = vel.diff(k)
    out = {f"{prefix}_vel": vel, f"{prefix}_acc": acc}
    m, sd = vel.rolling(20, min_periods=10).mean(), vel.rolling(20, min_periods=10).std()
    out[f"{prefix}_vel_z"] = (vel - m) / sd.replace(0.0, np.nan)
    ma, sda = acc.rolling(20, min_periods=10).mean(), acc.rolling(20, min_periods=10).std()
    out[f"{prefix}_acc_z"] = (acc - ma) / sda.replace(0.0, np.nan)
    # exhaustion flag: level rising but accelerating DOWN (the user's core idea)
    out[f"{prefix}_exhaust"] = ((vel > 0) & (acc < 0)).astype(float)
    return out


def build_orderflow_features(
    df: pd.DataFrame,
    fundings: dict | None = None,
    oi_df: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Return (features DataFrame on df.index, families dict {name: [columns]})."""
    idx = df.index
    close, high, low, openp, vol = (df["close"], df["high"], df["low"], df["open"], df["volume"])
    a = atr(df, 14)
    feats: dict[str, pd.Series] = {}
    fam: dict[str, list] = {}

    # ---- VOLUME (level / velocity / acceleration / range) ----
    vol_sma9 = vol.rolling(9, min_periods=3).mean()
    feats["vol_ratio"] = vol / vol_sma9.replace(0.0, np.nan)
    v = _vel_acc(vol, 4, "vol4")          # 4-bar derivatives (the user's "son 4 birim")
    v |= _vel_acc(vol, 1, "vol1")
    feats.update(v)
    fam["volume"] = ["vol_ratio", *v.keys()]

    # ---- PRICE-ACTION (return velocity = momentum, accel = curvature) ----
    ret = close.pct_change()
    pa = _vel_acc(ret, 1, "ret1")
    pa |= _vel_acc(ret, 4, "ret4")
    body = (close - openp) / (high - low).replace(0.0, np.nan)
    pa["body"] = body
    pa |= {f"body_{k}": v for k, v in _vel_acc(body, 4, "body4").items()}
    feats.update(pa)
    fam["price_action"] = list(pa.keys())

    # ---- CVD PROXY (candle signed-volume; full history) ----
    signed = ((close - openp) / (high - low).replace(0.0, np.nan)).fillna(0.0) * vol
    cvd_run = signed.rolling(24, min_periods=6).sum()   # rolling cumulative delta
    cv = {"cvd_run": cvd_run}
    cv |= _vel_acc(cvd_run, 4, "cvd4")
    # price-up but CVD-down divergence (distribution into strength)
    cv["cvd_div"] = ((ret.rolling(4).sum() > 0) & (cvd_run.diff(4) < 0)).astype(float)
    feats.update(cv)
    fam["cvd_proxy"] = list(cv.keys())

    # ---- VWAP PROXY (rolling, causal) ----
    tp = (high + low + close) / 3.0
    vwap = (tp * vol).rolling(24, min_periods=6).sum() / vol.rolling(24, min_periods=6).sum()
    vw = {"vwap_dist_atr": (close - vwap) / a}
    vw |= _vel_acc(vw["vwap_dist_atr"], 4, "vwapd4")
    feats.update(vw)
    fam["vwap"] = list(vw.keys())

    # ---- VOLATILITY (accel of ATR%) ----
    atr_pct = a / close
    vol_a = {"atr_pct": atr_pct}
    vol_a |= _vel_acc(atr_pct, 4, "atrp4")
    feats.update(vol_a)
    fam["volatility"] = list(vol_a.keys())

    # ---- FUNDING (level / velocity / accel / cross-exchange) ----
    if fundings and "binance" in fundings:
        from ..ml.altfeatures import _funding_on_grid
        f = _funding_on_grid(fundings["binance"], idx)
        fu = {"fund_now": f, "fund_mean_7d": f.rolling(42, min_periods=10).mean()}
        fu |= _vel_acc(f, 4, "fund4")
        others = [_funding_on_grid(fundings[e], idx) for e in ("bybit", "okx") if e in fundings]
        if others:
            fu["fund_xexch"] = f - pd.concat(others, axis=1).mean(axis=1)
        feats.update(fu)
        fam["funding"] = list(fu.keys())

    # ---- OPEN INTEREST / L-S / TAKER (2024-06+; NaN before) ----
    if oi_df is not None and len(oi_df):
        oi = oi_df.reindex(idx).ffill()
        oif = {}
        if "oi" in oi:
            oif["oi_lvl"] = oi["oi"]
            oif |= _vel_acc(oi["oi"], 4, "oi4")
        if "taker_buy_sell_ratio" in oi:
            oif["taker_bs"] = oi["taker_buy_sell_ratio"]
            oif |= _vel_acc(oi["taker_buy_sell_ratio"], 4, "taker4")
        if "toptrader_ls_ratio" in oi:
            oif["tt_ls"] = oi["toptrader_ls_ratio"]
            oif |= _vel_acc(oi["toptrader_ls_ratio"], 4, "ttls4")
        if "ls_ratio" in oi:
            oif["ls"] = oi["ls_ratio"]
        # shift one bar (metric for bar t known by t's decision), then collect
        oif = {k: v.shift(1) for k, v in oif.items()}
        feats.update(oif)
        fam["oi_ls_taker"] = list(oif.keys())

    # ---- REGRESSION (rolling OLS slope + R² trend-cleanliness; multi-window) ----
    reg = {}
    logp = np.log(close.clip(lower=1e-9))
    for w in (12, 24, 48):
        sl, rr = _rolling_ols(logp, w)
        reg[f"reg_slope_{w}"] = sl * 1000.0  # log-price slope, scaled to readable units
        reg[f"reg_r2_{w}"] = rr
    # velocity & acceleration of the 24-bar slope (does the trend's strength accelerate?)
    reg |= _vel_acc(reg["reg_slope_24"], 4, "regslope4")
    # clean-trend flag: strong positive slope AND high R² (linear, not choppy)
    reg["reg_clean_up"] = ((reg["reg_slope_24"] > 0) & (reg["reg_r2_24"] > 0.6)).astype(float)
    feats.update(reg)
    fam["regression"] = list(reg.keys())

    # ---- JERK (3rd derivative) of the main flow series ----
    def _jerk(s, k, name):
        return {name: s.diff(k).diff(k).diff(k)}
    jerk = {}
    jerk |= _jerk(vol, 4, "vol_jerk")
    jerk |= _jerk(ret, 4, "ret_jerk")
    jerk |= _jerk(cvd_run, 4, "cvd_jerk")
    feats.update(jerk)
    fam["jerk"] = list(jerk.keys())

    # ---- EXHAUSTION COMPOSITE (the headline hypothesis) ----
    up = close > ema(close, 20)
    ex = {
        # in an uptrend, volume rising but decelerating = fakeout risk
        "exh_vol": (up & (vol.diff(4) > 0) & (vol.diff(4).diff(4) < 0)).astype(float),
        # trend with CVD deceleration against it
        "exh_cvd": (up & (cvd_run.diff(4) > 0) & (cvd_run.diff(4).diff(4) < 0)).astype(float),
        # momentum still positive but its acceleration turned negative
        "exh_mom": ((ret.rolling(4).sum() > 0) & (ret.diff(1).diff(1).rolling(4).mean() < 0)).astype(float),
    }
    feats.update(ex)
    fam["exhaustion"] = list(ex.keys())

    out = pd.DataFrame(feats, index=idx).replace([np.inf, -np.inf], np.nan)
    return out, fam
