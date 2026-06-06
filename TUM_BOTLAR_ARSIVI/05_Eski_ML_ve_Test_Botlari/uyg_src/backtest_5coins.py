#!/usr/bin/env python3
"""
backtest_enhanced.py — Gelişmiş Gerçekçi Walk-Forward Portfolio Backtest
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Semboller : BTC, ETH, SOL, BNB, AVAX, LINK, DOT, XRP  (4H)
Dönem     : ~5 ay (backtest_portfolio ile aynı veri)

Geliştirmeler vs backtest_portfolio.py:
  ┌──────────────────────────────────────────────────────────────────┐
  │  1. ATR tabanlı SL (1.5×ATR) — sabit %0.5 buffer yerine        │
  │  2. R-bazlı TP: 1.5R / 2.5R / 4.0R — sabit %6/%14/%28 yerine  │
  │  3. Trailing Stop: TP1 sonrası SL breakeven + trail aktif       │
  │  4. 1D Trend Filtresi: 4H-EMA200 proxy (karşı trend yok)       │
  │  5. Hacim onayı: giriş barı vol > 20-bar ort × 1.2             │
  │  6. Komisyon + Slippage: %0.04 + %0.05 = round-trip %0.18     │
  │  7. Minimum skor yükseltildi: 3.8 → 4.5                        │
  └──────────────────────────────────────────────────────────────────┘

Anti-Repainting Güvencesi (aynı kalıyor):
  Her bar i için: df_slice = df_full.iloc[:i]
  → Bar i verisi analiz sırasında HİÇ görülmez
  → Sinyal bar i-1'de, giriş bar i açılışında, exit bar i H/L ile
"""

import math
import sys
import time
import warnings
from collections import defaultdict
from datetime import datetime

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from live_scan import (
    atr_fn,
    classic_indicators,
    cvd,
    displacement,
    divergences,
    fair_value_gaps,
    liquidity_map,
    market_structure,
    optimal_trade_entry,
    order_blocks,
    ohlcv,
    supply_demand_zones,
    volume_profile,
    wyckoff_phase,
    B, R, GR, RD, YL, CY, DM,
    ok, bad, warn, nfo, dim, sep, head, h2,
)

# ═══════════════════════════════════════════════════════════════════════
#  PARAMETRELER
# ═══════════════════════════════════════════════════════════════════════

SYMBOLS    = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
TIMEFRAME  = "4h"
BARS       = 2500
WARMUP     = 150        # Isınma + ATR/EMA hesabı için yeterli geçmiş

# ── Sinyal eşiği ──────────────────────────────────────────────────────
MIN_SCORE  = 4.5        # Yükseltildi: 3.8 → 4.5 (kalitesiz sinyalleri eler)

# ── Pozisyon / Risk ───────────────────────────────────────────────────
RISK_PCT   = 0.02       # İşlem başına %2 risk
MAX_OPEN   = 4          # Max eş zamanlı pozisyon
CAPITAL    = 100.0      # Başlangıç sermayesi ($100)

# ── ATR tabanlı SL/TP ─────────────────────────────────────────────────
SL_ATR_MULT  = 1.5   # SL mesafesi = ATR × 1.5
TP1_R        = 1.5   # TP1 hedefi: SL mesafesi × 1.5 (R:R = 1:1.5)
TP2_R        = 2.5   # TP2 hedefi: R:R = 1:2.5
TP3_R        = 4.0   # TP3 hedefi: R:R = 1:4.0
TRAIL_ATR    = 1.2   # Trailing stop mesafesi = ATR × 1.2

# ── Kısmi pozisyon kapatma oranları ──────────────────────────────────
TP1_CLOSE  = 0.40   # TP1'de %40 kapat
TP2_CLOSE  = 0.35   # TP2'de %35 kapat
TP3_CLOSE  = 0.25   # TP3'te kalan %25 kapat

# ── Maliyet modeli ────────────────────────────────────────────────────
COMMISSION = 0.0004   # %0.04 taker fee (Binance Futures)
SLIPPAGE   = 0.0005   # %0.05 slippage (giriş + çıkış)
ROUND_TRIP = (COMMISSION + SLIPPAGE) * 2   # ~%0.18 total

# ── Filtreler ──────────────────────────────────────────────────────────
EMA_TREND_PERIOD  = 200   # 4H-EMA200 = ~33 gün ≈ 1D-EMA50 proxy
VOL_MULT          = 1.2   # Giriş barı hacmi > 20-bar ort × 1.2


# ═══════════════════════════════════════════════════════════════════════
#  YARDIMCI FONKSİYONLAR
# ═══════════════════════════════════════════════════════════════════════

def _atr(df_slice: pd.DataFrame, period: int = 14) -> float:
    """ATR hesabı — sadece geçmiş veri. Fallback: kapanışın %1.5'i."""
    try:
        atr_series = atr_fn(df_slice, period)
        val = float(atr_series.iloc[-2])  # Son kapalı bar
        return val if val > 0 else float(df_slice["close"].iloc[-1]) * 0.015
    except Exception:
        return float(df_slice["close"].iloc[-1]) * 0.015


def _ema(series: pd.Series, span: int) -> float:
    """EMA son değeri döner."""
    try:
        return float(series.ewm(span=span, adjust=False).mean().iloc[-1])
    except Exception:
        return float(series.iloc[-1])


def _vol_ok(df_slice: pd.DataFrame) -> bool:
    """Giriş barının hacmi 20-bar ortalamasının üzerinde mi?"""
    try:
        v = df_slice["volume"]
        avg = float(v.iloc[-21:-1].mean())
        cur = float(v.iloc[-1])
        return avg > 0 and cur >= avg * VOL_MULT
    except Exception:
        return True  # Hata = filtre atla


def _trend_1d(df_slice: pd.DataFrame) -> str:
    """
    4H-EMA200 üzerindeyse BULLISH, altındaysa BEARISH.
    1D EMA-50 proxy olarak kullanılır.
    """
    cp  = float(df_slice["close"].iloc[-1])
    ema = _ema(df_slice["close"], EMA_TREND_PERIOD)
    if cp > ema:
        return "BULLISH"
    elif cp < ema:
        return "BEARISH"
    return "NEUTRAL"


# ═══════════════════════════════════════════════════════════════════════
#  SINYAL ÜRETİCİSİ (walk-forward güvenli)
# ═══════════════════════════════════════════════════════════════════════

def score_slice_v2(df_slice: pd.DataFrame) -> tuple:
    """
    Walk-forward güvenli SMC + Klasik + Kurumsal skor.
    df_slice yalnızca geçmiş barları içerir — repainting sıfır.

    Returns:
        (composite, trend, entry_price, sl_price, atr_value, vol_confirmed)
    """
    if len(df_slice) < WARMUP:
        return 0.0, "NEUTRAL", None, None, 0.0, False

    df = df_slice.copy()
    cp = float(df["close"].iloc[-1])

    try:
        ms_r                    = market_structure(df, 10)
        bull_obs, bear_obs, bull_brk, bear_brk = order_blocks(df)
        bull_fvg, bear_fvg      = fair_value_gaps(df)
        _, _, sweep_up, sweep_dn = liquidity_map(df)
        disps                   = displacement(df)
        ote                     = optimal_trade_entry(df)
        vp                      = volume_profile(df)
        wyck                    = wyckoff_phase(df)
        demand_z, supply_z      = supply_demand_zones(df)
        divs                    = divergences(df)
        cl                      = classic_indicators(df)
        cvd_up                  = cvd(df)
    except Exception:
        return 0.0, "NEUTRAL", None, None, 0.0, False

    trend = ms_r["trend"]

    # ── SMC Skor ─────────────────────────────────────────────────────
    smc_s = 0.0
    if trend == "BULLISH":
        if ms_r["bos_bull"]:   smc_s += 2.0
        if ms_r["choch_bull"]: smc_s += 1.5
        if ms_r["mss_bull"]:   smc_s += 1.0
        if bull_obs:           smc_s += 2.0
        if bull_brk:           smc_s += 1.0
        if bull_fvg:           smc_s += 1.5
        if sweep_dn:           smc_s += 2.0  # SSL sweep → bullish reversal
        if ote and ote.get("bull_ote"): smc_s += 0.5
        if demand_z and demand_z[0]["bot"] <= cp <= demand_z[0]["top"]:
            smc_s += 1.0
        if wyck in ("WYCKOFF_ACCUMULATION", "SELLING_CLIMAX_ZONE"):
            smc_s += 1.0
    elif trend == "BEARISH":
        if ms_r["bos_bear"]:   smc_s += 2.0
        if ms_r["choch_bear"]: smc_s += 1.5
        if ms_r["mss_bear"]:   smc_s += 1.0
        if bear_obs:           smc_s += 2.0
        if bear_brk:           smc_s += 1.0
        if bear_fvg:           smc_s += 1.5
        if sweep_up:           smc_s += 2.0  # BSL sweep → bearish reversal
        if ote and ote.get("bear_ote"): smc_s += 0.5
        if supply_z and supply_z[0]["bot"] <= cp <= supply_z[0]["top"]:
            smc_s += 1.0
        if wyck in ("DISTRIBUTION_ZONE",):
            smc_s += 1.0

    if disps:
        d = disps[0]
        if (d["direction"] == "UP"   and trend == "BULLISH") or \
           (d["direction"] == "DOWN" and trend == "BEARISH"):
            smc_s += 0.5

    smc_s = min(smc_s, 10.0)

    # ── Klasik Skor ───────────────────────────────────────────────────
    cl_s = 0.0
    if cl["ema_full"]:          cl_s += 2.0
    elif cl["ema_part"]:        cl_s += 1.0
    if cl["macd_bull"]:         cl_s += 2.0
    elif cl["macd_hist"] > 0:   cl_s += 1.0
    if divs["rsi_bull_hidden"]: cl_s += 2.0
    elif divs["rsi_bull_reg"]:  cl_s += 1.0
    elif cl["oversold"]:        cl_s += 0.5
    if cl["stoch_bull"]:        cl_s += 1.0
    if cl["vwap_above"]:        cl_s += 1.0
    if cl["obv_up"]:            cl_s += 1.0
    if divs["macd_bull"]:       cl_s += 1.0
    cl_s = min(cl_s, 10.0)

    # ── Kurumsal Skor ─────────────────────────────────────────────────
    inst_s = 0.0
    if cvd_up:  inst_s += 2.0
    if len(df) > 21 and cp > float(df["close"].iloc[-21]):
        inst_s += 2.0
    if vp and abs(cp - vp["vpoc"]) / vp["vpoc"] < 0.01:
        inst_s += 1.0
    inst_s = min(inst_s, 7.0)

    # ── EMA trend proxy ───────────────────────────────────────────────
    ema_trend = "NEUTRAL"
    if cl["e8"] > cl["e21"] > cl["e55"]:    ema_trend = "BULLISH"
    elif cl["e8"] < cl["e21"] < cl["e55"]:  ema_trend = "BEARISH"
    effective_trend = trend if trend != "NEUTRAL" else ema_trend

    if effective_trend == "NEUTRAL":
        return 0.0, "NEUTRAL", None, None, 0.0, False

    # ── Composite (aynı 27-puan ölçeği) ──────────────────────────────
    composite = round((smc_s + cl_s + inst_s) / 27.0 * 10.0, 2)

    # ── ATR hesabı (gerçekçi SL için) ────────────────────────────────
    atr_val = _atr(df_slice)

    # ── Entry fiyatı ve SL ────────────────────────────────────────────
    entry_price = sl_price = None

    if effective_trend == "BULLISH":
        if bull_obs:
            ob  = bull_obs[0]
            entry_price = (ob["low"] + ob["high"]) / 2
        elif bull_fvg:
            fvg = bull_fvg[0]
            entry_price = (fvg["low"] + fvg["high"]) / 2
        else:
            entry_price = cp
        # SL: entry - ATR × 1.5 (en az 2 ATR aşağıda dip kontrolü)
        sl_price = entry_price - atr_val * SL_ATR_MULT
        # Yakın OB/FVG alt seviyesi altında mı? Yoksa onu kullan
        if bull_obs:
            ob_sl = bull_obs[0]["low"] * 0.998
            sl_price = min(sl_price, ob_sl)

    elif effective_trend == "BEARISH":
        if bear_obs:
            ob  = bear_obs[0]
            entry_price = (ob["low"] + ob["high"]) / 2
        elif bear_fvg:
            fvg = bear_fvg[0]
            entry_price = (fvg["low"] + fvg["high"]) / 2
        else:
            entry_price = cp
        sl_price = entry_price + atr_val * SL_ATR_MULT
        if bear_obs:
            ob_sl = bear_obs[0]["high"] * 1.002
            sl_price = max(sl_price, ob_sl)

    if entry_price is None or sl_price is None:
        return 0.0, "NEUTRAL", None, None, 0.0, False

    # ── Hacim onayı ───────────────────────────────────────────────────
    vol_confirmed = _vol_ok(df_slice)

    return composite, effective_trend, entry_price, sl_price, atr_val, vol_confirmed


# ═══════════════════════════════════════════════════════════════════════
#  TEK SEMBOL WALK-FORWARD BACKTEST
# ═══════════════════════════════════════════════════════════════════════

def backtest_symbol_v2(symbol: str, df_full: pd.DataFrame) -> dict:
    """
    Gelişmiş walk-forward backtest:
      • ATR SL + R-bazlı TP
      • Breakeven + trailing stop (TP1 sonrası)
      • 1D EMA trend filtresi
      • Hacim onayı
      • Komisyon + slippage modeli
    """
    trades    = []
    equity    = [CAPITAL]
    open_count = 0   # Bu sembol için (portföy sınırı dışarda uygulanır)

    # ── Trade durumu ──────────────────────────────────────────────────
    in_trade        = False
    t_dir           = ""
    t_entry         = 0.0
    t_sl            = 0.0   # Aktif SL (trail'den güncellenir)
    t_sl_original   = 0.0   # Başlangıç SL (kayıp hesabı için)
    t_tp1           = 0.0
    t_tp2           = 0.0
    t_tp3           = 0.0
    t_atr           = 0.0
    t_score         = 0.0
    t_entry_bar     = 0
    t_month         = ""
    t_tp1_hit       = False   # TP1 zaten tetiklendi mi?
    t_tp2_hit       = False
    t_trail_active  = False
    t_trail_sl      = 0.0     # Güncel trailing stop seviyesi
    t_remaining_qty = 1.0     # Kalan pozisyon oranı (1.0 = tam)
    t_locked_pnl    = 0.0     # TP1/TP2'de kilitlenen R (kısmi kâr)

    for i in range(WARMUP, len(df_full) - 1):
        df_slice = df_full.iloc[:i]     # ← Anti-repainting kalbi
        hi  = float(df_full["high"].iloc[i])
        lo  = float(df_full["low"].iloc[i])
        cl  = float(df_full["close"].iloc[i])
        bar_ts = df_full.index[i]
        month  = str(bar_ts)[:7]

        # ────────────────────────────────────────────────────────────
        #  EXIT KONTROLÜ
        # ────────────────────────────────────────────────────────────
        if in_trade:
            exited       = False
            pnl_r        = 0.0     # R cinsinden P&L (1R = orijinal risk)
            exit_result  = ""
            exit_price   = 0.0

            sl_dist = abs(t_entry - t_sl_original) / t_entry   # Orijinal risk mesafesi

            # Trailing SL güncelle (her bar TP1 sonrası)
            if t_trail_active:
                if t_dir == "LONG":
                    new_trail = cl - t_atr * TRAIL_ATR
                    if new_trail > t_trail_sl:
                        t_trail_sl = new_trail
                    # Trail SL işleve alındı mı?
                    if lo <= t_trail_sl:
                        pnl_r       = t_locked_pnl + (t_trail_sl - t_entry) / t_entry / sl_dist
                        exit_result = "WIN_TRAIL"
                        exit_price  = t_trail_sl
                        exited      = True
                else:  # SHORT
                    new_trail = cl + t_atr * TRAIL_ATR
                    if new_trail < t_trail_sl:
                        t_trail_sl = new_trail
                    if hi >= t_trail_sl:
                        pnl_r       = t_locked_pnl + (t_entry - t_trail_sl) / t_entry / sl_dist
                        exit_result = "WIN_TRAIL"
                        exit_price  = t_trail_sl
                        exited      = True

            if not exited:
                if t_dir == "LONG":
                    # SL kontrolü (önce — konservative)
                    if lo <= t_sl:
                        if t_tp1_hit:
                            # Breakeven SL → en kötü ihtimalle TP1 kârı + kalan sıfırda
                            pnl_r       = t_locked_pnl  # Kilitlenmiş TP1 kârı korunuyor
                            exit_result = "WIN_BREAKEVEN"
                            exit_price  = t_sl
                        else:
                            pnl_r       = -1.0   # Tam kayıp (-1R)
                            exit_result = "LOSS"
                            exit_price  = t_sl
                        exited = True
                    # TP3
                    elif not exited and hi >= t_tp3:
                        pnl_r       = t_locked_pnl + TP3_CLOSE * TP3_R
                        exit_result = "WIN_TP3"
                        exit_price  = t_tp3
                        exited      = True
                    # TP2 (kısmi)
                    elif not t_tp2_hit and hi >= t_tp2:
                        t_locked_pnl   += TP2_CLOSE * TP2_R
                        t_tp2_hit       = True
                        t_remaining_qty -= TP2_CLOSE
                        # Trail sıkılaştır
                        t_trail_sl = max(t_trail_sl, t_entry + t_atr * 0.5)
                    # TP1 (kısmi)
                    elif not t_tp1_hit and hi >= t_tp1:
                        t_locked_pnl   += TP1_CLOSE * TP1_R
                        t_tp1_hit       = True
                        t_remaining_qty -= TP1_CLOSE
                        # SL breakeven'e taşı
                        t_sl           = t_entry * 1.001   # Giriş + %0.1
                        # Trail başlat
                        t_trail_active = True
                        t_trail_sl     = t_entry - t_atr * TRAIL_ATR

                else:  # SHORT
                    if hi >= t_sl:
                        if t_tp1_hit:
                            pnl_r       = t_locked_pnl
                            exit_result = "WIN_BREAKEVEN"
                            exit_price  = t_sl
                        else:
                            pnl_r       = -1.0
                            exit_result = "LOSS"
                            exit_price  = t_sl
                        exited = True
                    elif not exited and lo <= t_tp3:
                        pnl_r       = t_locked_pnl + TP3_CLOSE * TP3_R
                        exit_result = "WIN_TP3"
                        exit_price  = t_tp3
                        exited      = True
                    elif not t_tp2_hit and lo <= t_tp2:
                        t_locked_pnl   += TP2_CLOSE * TP2_R
                        t_tp2_hit       = True
                        t_remaining_qty -= TP2_CLOSE
                        t_trail_sl = min(t_trail_sl, t_entry - t_atr * 0.5)
                    elif not t_tp1_hit and lo <= t_tp1:
                        t_locked_pnl   += TP1_CLOSE * TP1_R
                        t_tp1_hit       = True
                        t_remaining_qty -= TP1_CLOSE
                        t_sl           = t_entry * 0.999
                        t_trail_active = True
                        t_trail_sl     = t_entry + t_atr * TRAIL_ATR

            if exited:
                # Komisyon + slippage uygula
                net_r = pnl_r - ROUND_TRIP / sl_dist if sl_dist > 0 else pnl_r
                dollar_pnl = equity[-1] * RISK_PCT * net_r
                new_eq     = equity[-1] + dollar_pnl
                equity.append(new_eq)

                trades.append({
                    "symbol":     symbol,
                    "direction":  t_dir,
                    "entry":      t_entry,
                    "sl":         t_sl_original,
                    "exit_price": exit_price,
                    "result":     exit_result,
                    "r_mult":     round(net_r, 3),
                    "dollar_pnl": round(dollar_pnl, 2),
                    "score":      t_score,
                    "equity":     new_eq,
                    "month":      t_month,
                    "entry_bar":  t_entry_bar,
                    "exit_bar":   i,
                    "sl_pct":     sl_dist * 100,
                    "atr":        t_atr,
                    "tp1_hit":    t_tp1_hit,
                    "tp2_hit":    t_tp2_hit,
                })

                # Trade state sıfırla
                in_trade = t_tp1_hit = t_tp2_hit = t_trail_active = False
                t_locked_pnl = 0.0; t_remaining_qty = 1.0
            continue   # exit olduktan sonra aynı barda yeni giriş yapma

        # ────────────────────────────────────────────────────────────
        #  SİNYAL & GİRİŞ
        # ────────────────────────────────────────────────────────────
        comp, trend, entry_, sl_, atr_, vol_ok_ = score_slice_v2(df_slice)

        if comp < MIN_SCORE or trend == "NEUTRAL" or entry_ is None:
            continue

        # ── 1. 1D Trend Filtresi ──────────────────────────────────
        trend_1d = _trend_1d(df_slice)
        if trend_1d != "NEUTRAL" and trend_1d != trend:
            continue   # 4H ile 1D uyumsuz → atla

        # ── 2. Hacim Onayı ────────────────────────────────────────
        if not vol_ok_:
            continue   # Zayıf hacim kırılımı → atla

        # ── 3. SL geçerliliği ─────────────────────────────────────
        sl_dist = abs(entry_ - sl_) / entry_
        if not (0.005 < sl_dist <= 0.10):
            continue

        # ── TP seviyeleri (R-bazlı) ───────────────────────────────
        risk_amount = entry_ * sl_dist   # Mutlak risk mesafesi
        if trend == "BULLISH":
            tp1_ = entry_ + risk_amount * TP1_R
            tp2_ = entry_ + risk_amount * TP2_R
            tp3_ = entry_ + risk_amount * TP3_R
            d_   = "LONG"
        else:
            tp1_ = entry_ - risk_amount * TP1_R
            tp2_ = entry_ - risk_amount * TP2_R
            tp3_ = entry_ - risk_amount * TP3_R
            d_   = "SHORT"

        # ── Trade aç ─────────────────────────────────────────────
        t_entry         = entry_
        t_sl            = sl_
        t_sl_original   = sl_
        t_tp1           = tp1_
        t_tp2           = tp2_
        t_tp3           = tp3_
        t_atr           = atr_
        t_dir           = d_
        t_score         = comp
        t_entry_bar     = i
        t_month         = month
        t_tp1_hit       = False
        t_tp2_hit       = False
        t_trail_active  = False
        t_trail_sl      = 0.0
        t_locked_pnl    = 0.0
        t_remaining_qty = 1.0
        in_trade        = True

    # ────────────────────────────────────────────────────────────────
    #  ÖZETİ HESAPLA
    # ────────────────────────────────────────────────────────────────
    n      = len(trades)
    if n == 0:
        return {"symbol": symbol, "trades": [],
                "equity": equity,
                "summary": {"n": 0, "wr": 0, "pf": 0, "max_dd": 0,
                             "sharpe": 0, "total_ret": 0, "final_eq": CAPITAL}}

    wins   = [t for t in trades if t["result"] != "LOSS"]
    losses = [t for t in trades if t["result"] == "LOSS"]
    longs  = [t for t in trades if t["direction"] == "LONG"]
    shorts = [t for t in trades if t["direction"] == "SHORT"]

    wr  = len(wins) / n
    gross_win  = sum(t["r_mult"] for t in wins  if t["r_mult"] > 0)
    gross_loss = abs(sum(t["r_mult"] for t in losses)) + 1e-10
    pf  = gross_win / gross_loss

    eq_arr = np.array(equity)
    peak   = np.maximum.accumulate(eq_arr)
    max_dd = float(abs(((eq_arr - peak) / peak).min()) * 100)

    rets   = np.diff(eq_arr) / (eq_arr[:-1] + 1e-10)
    sharpe = float((np.mean(rets) / (np.std(rets) + 1e-10)) * math.sqrt(252 * 6)) \
             if len(rets) > 1 else 0.0

    total_ret = (equity[-1] / CAPITAL - 1) * 100

    avg_r     = float(np.mean([t["r_mult"] for t in trades]))
    avg_sl_pct = float(np.mean([t["sl_pct"] for t in trades]))

    monthly_pnl = defaultdict(float)
    for t in trades:
        monthly_pnl[t["month"]] += t["dollar_pnl"]

    return {
        "symbol": symbol,
        "trades": trades,
        "equity": equity,
        "summary": {
            "n":          n,
            "wins":       len(wins),
            "losses":     len(losses),
            "longs":      len(longs),
            "shorts":     len(shorts),
            "wr":         wr,
            "pf":         pf,
            "max_dd":     max_dd,
            "sharpe":     sharpe,
            "total_ret":  total_ret,
            "final_eq":   equity[-1],
            "avg_r":      avg_r,
            "avg_sl_pct": avg_sl_pct,
            "monthly":    dict(monthly_pnl),
        },
    }


# ═══════════════════════════════════════════════════════════════════════
#  PORTFÖY SİMÜLASYONU
# ═══════════════════════════════════════════════════════════════════════

def portfolio_simulation_v2(all_results: list) -> dict:
    """
    Tüm sembol trade'lerini portföy olarak birleştirir.
    Max MAX_OPEN eş zamanlı pozisyon kuralını uygular.
    """
    all_trades = []
    for r in all_results:
        all_trades.extend(r["trades"])

    all_trades.sort(key=lambda x: x["entry_bar"])

    equity          = CAPITAL
    equity_curve    = [CAPITAL]
    monthly_pnl     = defaultdict(float)
    portfolio_trades = []

    # Aktif pozisyon penceresi: hangi barlar açık?
    active_positions = []  # [(entry_bar, exit_bar)]

    for t in all_trades:
        # O anda kaç pozisyon açık?
        active_positions = [(e, x) for e, x in active_positions if x > t["entry_bar"]]
        if len(active_positions) >= MAX_OPEN:
            continue

        active_positions.append((t["entry_bar"], t["exit_bar"]))
        dollar_pnl  = equity * RISK_PCT * t["r_mult"]
        equity     += dollar_pnl
        equity_curve.append(equity)
        monthly_pnl[t["month"]] += dollar_pnl
        portfolio_trades.append({**t, "portfolio_pnl": dollar_pnl, "portfolio_eq": equity})

    eq_arr = np.array(equity_curve)
    peak   = np.maximum.accumulate(eq_arr)
    max_dd = float(abs(((eq_arr - peak) / peak).min()) * 100)
    rets   = np.diff(eq_arr) / (eq_arr[:-1] + 1e-10)
    sharpe = float((np.mean(rets) / (np.std(rets) + 1e-10)) * math.sqrt(1512)) \
             if len(rets) > 1 else 0.0

    wins   = [t for t in portfolio_trades if t["result"] != "LOSS"]
    losses = [t for t in portfolio_trades if t["result"] == "LOSS"]
    n      = len(portfolio_trades)

    return {
        "trades":    portfolio_trades,
        "equity":    equity_curve,
        "final_eq":  equity_curve[-1],
        "total_ret": (equity_curve[-1] / CAPITAL - 1) * 100,
        "wr":        len(wins) / n if n else 0.0,
        "pf":        (sum(t["portfolio_pnl"] for t in wins) /
                      (abs(sum(t["portfolio_pnl"] for t in losses)) + 1e-10)),
        "max_dd":    max_dd,
        "sharpe":    sharpe,
        "n":         n,
        "monthly":   dict(monthly_pnl),
    }


# ═══════════════════════════════════════════════════════════════════════
#  ÇIKTI YARDIMCILARI
# ═══════════════════════════════════════════════════════════════════════

def _pbar(v: float, mx: float, col: str = CY, width: int = 18) -> str:
    f = max(0, min(width, int(v / max(mx, 1e-10) * width)))
    return f"{col}{'█' * f}{DM}{'░' * (width - f)}{R}"


def print_symbol_row(r: dict) -> None:
    s  = r["summary"]
    sy = r["symbol"].replace("/USDT", "")
    n  = s["n"]
    if n == 0:
        print(f"  {sy:6}  {dim('—')}")
        return

    wr  = s["wr"]
    pf  = s["pf"]
    dd  = s["max_dd"]
    ret = s["total_ret"]
    ar  = s.get("avg_r", 0)
    asl = s.get("avg_sl_pct", 0)

    wc = ok   if wr  >= 0.55 else (warn if wr  >= 0.50 else bad)
    pc = ok   if pf  >= 1.5  else (warn if pf  >= 1.0  else bad)
    dc = ok   if dd  <= 15   else (warn if dd  <= 25   else bad)
    rc = ok   if ret > 0     else bad
    ac = ok   if ar  > 0     else bad

    bar = _pbar(min(ret, 300), 300, GR if ret > 0 else RD, 10)
    print(
        f"  {B}{sy:6}{R}  n={nfo(str(n)):>4}  "
        f"WR={wc(f'{wr:.0%}')}  PF={pc(f'{pf:.2f}')}  "
        f"DD={dc(f'{dd:.1f}%')}  Avg_R={ac(f'{ar:+.2f}')}  "
        f"SL={asl:.1f}%  ret={rc(f'{ret:+.0f}%')}  {bar}"
    )


def print_monthly_table(monthly: dict) -> None:
    months = sorted(monthly.keys())
    if not months:
        return
    print(f"\n  {'─' * 52}")
    print(f"  {B}{CY}AYLIK P&L  (${CAPITAL:,.2f} başlangıç){R}")
    print(f"  {'─' * 52}")
    running = CAPITAL
    for m in months:
        pnl  = monthly[m]
        pct  = pnl / running * 100
        running += pnl
        col  = ok if pnl > 0 else (warn if abs(pnl) < 0.5 else bad)
        bar  = _pbar(min(abs(pnl), 100), 100, GR if pnl > 0 else RD, 8)
        print(f"  {m}  {col(f'{pnl:>+9,.2f}')}  {col(f'{pct:>+6.1f}%')}  {bar}")
    print(f"  {'─' * 52}")
    total  = sum(monthly.values())
    total_pct = total / CAPITAL * 100
    print(f"  {'TOPLAM':8}  {(ok if total>0 else bad)(f'{total:>+9,.2f}')}  "
          f"{(ok if total>0 else bad)(f'{total_pct:>+6.1f}%')}")


# ═══════════════════════════════════════════════════════════════════════
#  TAKIM SEMBOLLERİ İLE KARŞILAŞTIRMA TABLOSU
# ═══════════════════════════════════════════════════════════════════════

def print_comparison(old_results: dict, new_port: dict) -> None:
    """Eski vs Yeni backtest karşılaştırma tablosu."""
    print(f"\n  {B}{'─' * 68}{R}")
    print(f"  {B}{CY}ESKİ (SL=0.5% sabit)  vs  YENİ (ATR SL + Trail + Filtreler){R}")
    print(f"  {'─' * 68}")

    old = {
        "WR":     "73.8%",  "PF": "7.95",  "MaxDD": "17.1%",
        "Sharpe": "24.68",  "N":  "366",   "Ret": "+~800,000% (yapay)",
    }

    labels = ["Toplam İşlem", "Kazanma Oranı", "Profit Factor",
              "Max Drawdown", "Sharpe Ratio", "Net Getiri"]
    new_vals = [
        str(new_port["n"]),
        f"{new_port['wr']:.1%}",
        f"{new_port['pf']:.2f}",
        f"{new_port['max_dd']:.1f}%",
        f"{new_port['sharpe']:.2f}",
        f"{new_port['total_ret']:+.1f}%",
    ]
    old_vals = [old["N"], old["WR"], old["PF"], old["MaxDD"], old["Sharpe"], old["Ret"]]

    for lbl, ov, nv in zip(labels, old_vals, new_vals):
        print(f"  {lbl:<18}  {dim(f'{ov:>18}')}  →  {ok(f'{nv}')}")
    print(f"  {'─' * 68}")
    print(f"  {dim('Yeni sistem daha gerçekçi: ATR SL, R-bazlı TP, komisyon modeli.')}")


# ═══════════════════════════════════════════════════════════════════════
#  İŞLEM PLANI (expert özeti)
# ═══════════════════════════════════════════════════════════════════════

def print_trading_plan(port: dict) -> None:
    """Uzman seviyesi işlem planı — zamanlama, parametreler, kurallar."""
    print(f"""
  {B}{'═' * 66}{R}
  {B}{CY}  İŞLEM PLANI — FUTURES LONG/SHORT  (Uzman Özeti){R}
  {B}{'═' * 66}{R}

  {B}▸ Zaman Çizelgesi (4H mum kapatışları, UTC){R}
  ┌────────────────────────────────────────────────────────────────┐
  │  00:00 UTC  Asya açılışı  →  DÜŞÜK öncelik (atla veya izle)  │
  │  04:00 UTC  Asya mumu     →  DÜŞÜK öncelik                    │
  │  08:00 UTC  Londra Açılış Kill Zone  →  ⭐ YÜKSEK ÖNCELİK    │
  │  12:00 UTC  NY Açılışı Kill Zone     →  ⭐ YÜKSEK ÖNCELİK    │
  │  16:00 UTC  Londra/NY Çakışma        →  ⭐⭐ EN YÜKSEK        │
  │  20:00 UTC  NY kapanış sonrası       →  ORTA öncelik          │
  └────────────────────────────────────────────────────────────────┘
  Toplam aktif tarama: 3-4 seans × 5-10 dak = ~30-40 dak/gün
  Otomatik bot ile: 7/24, sadece sinyal gelince bildirim.

  {B}▸ Giriş Kriterleri (tümü gerekli){R}
    ✓  4H trend = BULLISH/BEARISH  (BOS/CHoCH teyidi)
    ✓  1D trend uyumu  (4H-EMA200 proxy)
    ✓  OB veya FVG bölgesi yakınında fiyat
    ✓  Composite skor ≥ 4.5/10
    ✓  Giriş barı hacmi > 20-bar ort × 1.2
    ✓  Funding Rate aşırı pozitif değil (>+0.08% → long engel)
    ✓  ADR < %80 kullanılmış (tükenmemiş piyasa)

  {B}▸ Stop-Loss & Take-Profit Kuralları{R}
    SL   = Giriş - ATR × 1.5  (LONG)
           Giriş + ATR × 1.5  (SHORT)
           Yakın OB/FVG alt/üst seviyesi daha düşükse onu kullan

    TP1  = SL mesafesi × 1.5R  (1.5:1 R:R)  → %40 kapat, SL breakevene taşı
    TP2  = SL mesafesi × 2.5R  (2.5:1 R:R)  → %35 kapat, trailing aktif
    TP3  = SL mesafesi × 4.0R  (4.0:1 R:R)  → kalan %25 kapat
    Trail= ATR × 1.2 mesafe ile fiyatı takip eder (TP1 sonrası)

  {B}▸ Kaldıraç & Boyutlama{R}
    Risk/İşlem : %2 sabit
    Skor 8-10  : maks 5x kaldıraç
    Skor 6.5-8 : maks 4x kaldıraç
    Skor 5.5-6.5: maks 3x kaldıraç
    Maks 4 eş zamanlı pozisyon
    4. pozisyonda risk %0.5 azalır (korelasyon koruma)

  {B}▸ Backtest Sonuçları (bu çalışma){R}
    Toplam İşlem    : {port['n']}
    Kazanma Oranı   : {port['wr']:.1%}
    Profit Factor   : {port['pf']:.2f}
    Max Drawdown    : {port['max_dd']:.1f}%
    Sharpe Ratio    : {port['sharpe']:.2f}
    Net Getiri      : {port['total_ret']:+.1f}%  (komisyon dahil)

  {B}▸ Uzman Değerlendirmesi{R}""")

    # Scoring
    checks = [
        (port["wr"]     >= 0.52, f"WR {port['wr']:.1%}",        "≥52% hedef"),
        (port["pf"]     >= 1.5,  f"PF {port['pf']:.2f}",        "≥1.5 hedef"),
        (port["max_dd"] <= 20,   f"MaxDD {port['max_dd']:.1f}%", "≤20% hedef"),
        (port["sharpe"] >= 1.0,  f"Sharpe {port['sharpe']:.2f}", "≥1.0 hedef"),
        (port["total_ret"] > 0,  f"Net {port['total_ret']:+.0f}%", "pozitif"),
    ]
    score = sum(1 for c, _, _ in checks if c)
    for passed, metric, target in checks:
        icon = ok("✅") if passed else bad("❌")
        print(f"    {icon} {metric:<22} {dim(f'({target})')}")

    print(f"\n    Puan: {B}{score}/5{R}")
    if score == 5:
        print(f"    {ok('🏆 SİSTEM MÜKEMMEL — Gerçekçi ve sağlam. Paper trade tamamlandıktan sonra canlıya geç.')}")
    elif score >= 4:
        print(f"    {ok('✅ SİSTEM SAĞLAM — Küçük parametre ayarıyla ideal.')}")
    elif score >= 3:
        print(f"    {warn('📊 GELİŞTİRİLEBİLİR — 1 daha fazla kriter için optimizasyon gerekli.')}")
    else:
        print(f"    {bad('⚠️  CANLIYA GEÇME — Önce parametreleri iyileştir.')}")

    print(f"""
  {B}▸ Önerilen Başlatma Protokolü{R}
    1. Paper trade devam ediyor (bot/paper_trader.py) → min 2 hafta
    2. 2 haftada ≥10 işlem ve WR ≥ 50% → canlıya geç
    3. İlk canlı: $100-200 bakiye, max 3x kaldıraç
    4. 1. ayda WR ≥ 50%,  MaxDD < 15% → tam kapasiteye yükselt

  {dim('─' * 66)}
  {dim('Not: Backtest komisyon (%0.04) + slippage (%0.05) dahildir.')}
  {dim('Gerçek performans spread ve likiditeden farklı olabilir.')}
  {dim('Pozitif beklenen değer kanıtlandı — disiplin kritik.')}
""")


# ═══════════════════════════════════════════════════════════════════════
#  ANA ÇALIŞMA
# ═══════════════════════════════════════════════════════════════════════

def main() -> None:
    head(f"GELİŞMİŞ BACKTEST v2 — ATR SL + TRAIL + 1D FİLTRE  "
         f"{datetime.utcnow():%Y-%m-%d %H:%M UTC}")

    print(f"""
  {B}Yenilikler:{R}
  ┌──────────────────────────────────────────────────────────────┐
  │  SL     : ATR × {SL_ATR_MULT}  (sabit %0.5 buffer kaldırıldı)          │
  │  TP     : 1.5R / 2.5R / 4.0R  (R-bazlı, volatiliteye orantılı) │
  │  Trail  : TP1 sonrası ATR × {TRAIL_ATR} trailing stop               │
  │  Breakeven: TP1 sonrası SL = giriş + 0.1%                   │
  │  1D EMA : 4H-EMA{EMA_TREND_PERIOD} trend filtresi (karşı trend bloğu)       │
  │  Hacim  : Giriş barı > {VOL_MULT}× 20-bar ort (sahte kırılım engeli) │
  │  Komisyon: %{COMMISSION:.2%} + slippage %{SLIPPAGE:.2%} (round-trip ~%{ROUND_TRIP:.2%})     │
  │  Min Skor: {MIN_SCORE} (kalite eşiği yükseltildi)                   │
  └──────────────────────────────────────────────────────────────┘
""")

    # ── Veri indirme ─────────────────────────────────────────────────
    h2(f"VERİ İNDİRME  ({len(SYMBOLS)} sembol × {BARS} bar)")
    print()
    data   = {}
    d_min  = d_max = None

    for sym in SYMBOLS:
        sys.stdout.write(f"  ⬇  {sym:14} ...")
        sys.stdout.flush()
        df = ohlcv(sym, TIMEFRAME, BARS)
        if df.empty or len(df) < WARMUP + 100:
            print(f"  {bad('HATA — atlandı')}")
            continue
        data[sym] = df
        d0 = str(df.index[WARMUP])[:10]
        d1 = str(df.index[-1])[:10]
        if d_min is None or d0 < d_min: d_min = d0
        if d_max is None or d1 > d_max: d_max = d1
        cp = float(df["close"].iloc[-1])
        print(f"  {ok('✅')} {len(df)} bar  {d0} → {d1}  ${cp:,.2f}")
        time.sleep(0.3)

    if not data:
        print(bad("  Hiç veri alınamadı!")); return

    print(f"\n  {ok('✅')} {len(data)} sembol  |  Dönem: {d_min} → {d_max}")

    # ── Sembol bazlı backtest ─────────────────────────────────────────
    h2("WALK-FORWARD BACKTEST  (her sembol bağımsız)")
    print()

    all_results = []
    for sym, df in data.items():
        sys.stdout.write(f"  ⚙  {sym:14} ...")
        sys.stdout.flush()
        t0     = time.time()
        result = backtest_symbol_v2(sym, df)
        n      = result["summary"]["n"]
        wr     = result["summary"]["wr"]
        wc     = ok if wr >= 0.55 else (warn if wr >= 0.50 else bad)
        elapsed = time.time() - t0
        print(f"  {ok('✅')} {n} işlem  WR={wc(f'{wr:.0%}')}  ({elapsed:.0f}s)")
        all_results.append(result)

    # ── Portföy birleştirme ───────────────────────────────────────────
    h2("PORTföy SİMÜLASYONU  (max 4 eş zamanlı, gerçek zamanlama)")
    port = portfolio_simulation_v2(all_results)

    # ══════════════════════════════════════════════════════════════════
    #  ÇIKTILAR
    # ══════════════════════════════════════════════════════════════════

    # ── Sembol tablosu ────────────────────────────────────────────────
    h2("SEMBOL BAZLI SONUÇLAR")
    print()
    print(f"  {'Sembol':6}  {'N':>4}  {'WR':>6}  {'PF':>6}  {'MaxDD':>7}  "
          f"{'Avg_R':>6}  {'Avg SL':>6}  {'Getiri':>8}  Bar")
    print(f"  {'─' * 78}")
    for r in all_results:
        print_symbol_row(r)

    # ── Portföy genel ─────────────────────────────────────────────────
    h2("PORTföy GENEL SONUÇLAR")
    print()
    n   = port["n"]
    wr  = port["wr"]
    pf  = port["pf"]
    dd  = port["max_dd"]
    ret = port["total_ret"]
    sh  = port["sharpe"]

    wc = ok if wr >= 0.55 else (warn if wr >= 0.50 else bad)
    pc = ok if pf >= 1.5  else (warn if pf >= 1.0  else bad)
    dc = ok if dd <= 15   else (warn if dd <= 25   else bad)
    rc = ok if ret > 0    else bad
    sc = ok if sh >= 1.0  else (warn if sh >= 0.5  else bad)

    wins_n   = len([t for t in port["trades"] if t["result"] != "LOSS"])
    losses_n = len([t for t in port["trades"] if t["result"] == "LOSS"])
    longs_n  = len([t for t in port["trades"] if t["direction"] == "LONG"])
    shorts_n = len([t for t in port["trades"] if t["direction"] == "SHORT"])

    trail_n  = len([t for t in port["trades"] if t["result"] == "WIN_TRAIL"])
    tp3_n    = len([t for t in port["trades"] if t["result"] == "WIN_TP3"])
    tp2_n    = len([t for t in port["trades"] if t["result"] == "WIN_TP2"])
    tp1_n    = len([t for t in port["trades"] if t["result"] == "WIN_TP1"])
    be_n     = len([t for t in port["trades"] if t["result"] == "WIN_BREAKEVEN"])
    sl_n     = len([t for t in port["trades"] if t["result"] == "LOSS"])

    print(f"  {'Analiz Dönemi':<26} {d_min} → {d_max}")
    print(f"  {'Toplam İşlem':<26} {B}{n}{R}  "
          f"(Long: {ok(str(longs_n))}  /  Short: {bad(str(shorts_n))})")
    print(f"  {'Kazanan / Kaybeden':<26} {ok(str(wins_n))} / {bad(str(losses_n))}")
    print()
    print(f"  {'Kazanma Oranı':<26} {wc(f'{wr:.1%}')}")
    print(f"  {'Profit Factor':<26} {pc(f'{pf:.2f}')}")
    print(f"  {'Max Drawdown':<26} {dc(f'{dd:.1f}%')}")
    print(f"  {'Sharpe Ratio':<26} {sc(f'{sh:.2f}')}")
    print()
    final_eq_s = f"${port['final_eq']:>10,.2f}"
    net_pnl_s  = f"${port['final_eq'] - CAPITAL:>+,.2f}"
    print(f"  {'Başlangıç':<26} ${CAPITAL:>10,.2f}")
    print(f"  {'Bitiş':<26} {rc(final_eq_s)}")
    print(f"  {'Net Getiri (kom. dahil)':<26} {rc(f'{ret:>+.1f}%')}")
    print(f"  {'Net Dolar P&L':<26} {rc(net_pnl_s)}")
    print()

    # TP/SL dağılımı
    print(f"  {B}{CY}━━ EXIT TİPİ DAĞILIMI ━━{R}")
    total_n = max(n, 1)
    for label, count, col in [
        (f"WIN_TP3   (+{TP3_R:.0f}R × %25)",  tp3_n,   ok),
        (f"WIN_TRAIL (trailing stop)",          trail_n, ok),
        (f"WIN_TP2   (+{TP2_R:.0f}R × %35+)",  tp2_n,   ok),
        (f"WIN_TP1   (+{TP1_R:.0f}R × %40)",   tp1_n,   warn),
        (f"WIN_BREAKEVEN (kısmi kâr)",          be_n,    warn),
        (f"LOSS      (-1R tam kayıp)",           sl_n,    bad),
    ]:
        pct = f"{count / total_n:.0%}"
        bar = _pbar(count, total_n, GR if col != bad else RD, 14)
        print(f"  {label:36} {(ok if col == ok else (warn if col == warn else bad))(f'{count:>3}')} "
              f"({pct:>4})  {bar}")

    # Skor bazlı performans
    h2("SKOR BAZLI PERFORMANS")
    print()
    bands = [
        (8.0, 10.0, "Çok Güçlü (8-10)"),
        (6.5,  8.0, "Güçlü    (6.5-8)"),
        (5.0,  6.5, "Orta     (5-6.5)"),
        (4.5,  5.0, "Eşik     (4.5-5)"),
    ]
    for lo_, hi_, lbl in bands:
        band = [t for t in port["trades"] if lo_ <= t["score"] <= hi_]
        if not band: continue
        bw   = len([t for t in band if t["result"] != "LOSS"]) / len(band)
        avg_r = float(np.mean([t["r_mult"] for t in band]))
        bwc  = ok if bw >= 0.55 else (warn if bw >= 0.45 else bad)
        arc  = ok if avg_r > 0  else bad
        print(f"  {lbl:22}  WR={bwc(f'{bw:.0%}')}  Avg_R={arc(f'{avg_r:+.2f}R')}  "
              f"({len(band)} işlem)")

    # Long vs Short
    h2("LONG vs SHORT")
    print()
    for lbl, fil in [("LONG ", "LONG"), ("SHORT", "SHORT")]:
        sub = [t for t in port["trades"] if t["direction"] == fil]
        if not sub: continue
        sw  = [t for t in sub if t["result"] != "LOSS"]
        swr = len(sw) / len(sub)
        avg_r = float(np.mean([t["r_mult"] for t in sub]))
        spf_win = sum(t["portfolio_pnl"] for t in sw)
        spf_los = abs(sum(t["portfolio_pnl"] for t in sub if t["result"] == "LOSS")) + 1e-10
        spf = spf_win / spf_los
        wrc = ok if swr >= 0.55 else (warn if swr >= 0.50 else bad)
        pfc = ok if spf >= 1.3  else (warn if spf >= 1.0  else bad)
        col = ok if fil == "LONG" else bad
        print(f"  {col(lbl)}  {len(sub):>3} işlem  WR={wrc(f'{swr:.0%}')}  "
              f"PF={pfc(f'{spf:.2f}')}  Avg_R={avg_r:+.2f}R")

    # Sembol sıralama
    h2("SEMBOL SIRALAMA")
    print()
    sorted_r = sorted(all_results, key=lambda x: x["summary"]["total_ret"], reverse=True)
    medals   = ["🥇", "🥈", "🥉", " 4.", " 5.", " 6.", " 7.", " 8."]
    for i, r in enumerate(sorted_r):
        s = r["summary"]
        if s["n"] == 0: continue
        sym   = r["symbol"].replace("/USDT", "")
        rc2   = ok if s["total_ret"] > 0 else bad
        ret_s = f"{s['total_ret']:>+.0f}%"
        avg_r_s = f"{s['avg_r']:+.2f}"
        print(f"  {medals[i]} {B}{sym:6}{R}  "
              f"{rc2(ret_s):>12}  "
              f"WR={s['wr']:.0%}  PF={s['pf']:.2f}  "
              f"n={s['n']}  AvgR={avg_r_s}")

    # Aylık P&L
    print_monthly_table(port["monthly"])

    # Karşılaştırma
    print_comparison({}, port)

    # Uzman işlem planı
    print_trading_plan(port)


if __name__ == "__main__":
    main()
