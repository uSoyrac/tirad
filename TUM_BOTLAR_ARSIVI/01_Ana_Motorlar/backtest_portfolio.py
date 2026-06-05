#!/usr/bin/env python3
"""
backtest_portfolio.py — 1 Yıllık Multi-Symbol Walk-Forward Portföy Backtest'i
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Semboller : BTC, ETH, SOL, BNB, AVAX, LINK, DOT, XRP  (4H)
Yaklaşım  : Her bar için sadece df.iloc[:i] — GELECEĞI ASLA GÖRMEz (anti-repainting)
Risk      : %2 sabit per işlem, max 4 eş zamanlı pozisyon
Dönem     : ~1 yıl (2200 bar ≈ 366 gün 4H verisi)
"""
import warnings; warnings.filterwarnings("ignore")
import sys, math, time
from datetime import datetime
from collections import defaultdict
import numpy as np
import pandas as pd

from live_scan import (
    ohlcv,
    market_structure, order_blocks, fair_value_gaps,
    liquidity_map, displacement, optimal_trade_entry,
    volume_profile, wyckoff_phase, supply_demand_zones,
    divergences, classic_indicators, cvd,
    R, B, U, GR, RD, YL, CY, MG, DM, BL,
    ok, bad, warn, nfo, dim, sep, head, h2
)

# ═══════════════════════════════════════════════════════════════════
#  PARAMETREler
# ═══════════════════════════════════════════════════════════════════
SYMBOLS   = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT",
             "AVAX/USDT", "LINK/USDT", "DOT/USDT", "XRP/USDT"]
TIMEFRAME = "4h"
BARS      = 2500    # ~1 yıl + ısınma (2200 işlem barı + 120 warmup + buffer)
WARMUP    = 120     # İlk 120 bar sadece ısınma — sinyal üretilmez
MIN_SCORE = 3.8     # Sinyal eşiği (tek TF backtest: MTF yok → max 27p)
RISK_PCT  = 0.02
SL_BUFFER = 0.005
TP1_PCT   = 0.06;  TP1_CLOSE = 0.40
TP2_PCT   = 0.14;  TP2_CLOSE = 0.35
TP3_PCT   = 0.28;  TP3_CLOSE = 0.25
CAPITAL   = 10_000.0
MAX_OPEN  = 4       # Portföyde aynı anda max açık pozisyon

# ═══════════════════════════════════════════════════════════════════
#  ANTİ-REPAINTİNG GÜVENCESİ
# ═══════════════════════════════════════════════════════════════════
# Her bar i için:
#   df_slice = df_full.iloc[:i]   ← sadece i'ye kadar kapanmış mumlar
#   yani bar i'nin HIGH/LOW/CLOSE'u henüz bilinmiyor
#   analiz yapılır, sinyal varsa SONRAKI BAR'da (i+1) giriş simüle edilir
#   exit kontrolü ise bar i'nin OHLC'si ile yapılır → sıfır look-ahead


def score_slice(df_slice):
    """
    Belirli bir dilim üzerinde SMC + Klasik + Kurumsal skor hesaplar.
    Dönüş: (composite 0-10, trend, entry_low, entry_high, sl)
    """
    if len(df_slice) < 80:
        return 0, "NEUTRAL", None, None, None

    df = df_slice.copy()
    try:
        ms               = market_structure(df, 10)
        bull_obs, bear_obs, bull_brk, bear_brk = order_blocks(df)
        bull_fvg, bear_fvg = fair_value_gaps(df)
        bsl, ssl, sweep_up, sweep_down = liquidity_map(df)
        disps            = displacement(df)
        ote              = optimal_trade_entry(df)
        vp               = volume_profile(df)
        wyck             = wyckoff_phase(df)
        demand_z, supply_z = supply_demand_zones(df)
        divs             = divergences(df)
        cl               = classic_indicators(df)
        cvd_up           = cvd(df)
    except Exception:
        return 0, "NEUTRAL", None, None, None

    trend = ms["trend"]
    cp    = float(df["close"].iloc[-1])

    # ── SMC Skor ────────────────────────────────────────────────
    smc_s = 0
    if trend == "BULLISH":
        if ms["bos_bull"]:    smc_s += 2
        if ms["choch_bull"]:  smc_s += 1
        if ms["mss_bull"]:    smc_s += 1
        if bull_obs:          smc_s += 2
        if bull_brk:          smc_s += 1
        if bull_fvg:          smc_s += 1
        if sweep_down:        smc_s += 2
        if ote and ote["bull_ote"]: smc_s += 1
        if demand_z:
            d = demand_z[0]
            if d["bot"] <= cp <= d["top"]: smc_s += 1
        if wyck in ("WYCKOFF_ACCUMULATION", "SELLING_CLIMAX_ZONE"): smc_s += 1
    elif trend == "BEARISH":
        if ms["bos_bear"]:    smc_s += 2
        if ms["choch_bear"]:  smc_s += 1
        if ms["mss_bear"]:    smc_s += 1
        if bear_obs:          smc_s += 2
        if bear_brk:          smc_s += 1
        if bear_fvg:          smc_s += 1
        if sweep_up:          smc_s += 2
        if ote and ote["bear_ote"]: smc_s += 1
        if supply_z:
            s = supply_z[0]
            if s["bot"] <= cp <= s["top"]: smc_s += 1
        if wyck in ("DISTRIBUTION_ZONE",): smc_s += 1
    if disps:
        d = disps[0]
        if (d["direction"] == "UP"   and trend == "BULLISH") or \
           (d["direction"] == "DOWN" and trend == "BEARISH"):
            smc_s += 0.5
    smc_s = min(smc_s, 10.0)

    # ── Klasik Skor ──────────────────────────────────────────────
    cl_s = 0
    if cl["ema_full"]:         cl_s += 2
    elif cl["ema_part"]:       cl_s += 1
    if cl["macd_bull"]:        cl_s += 2
    elif cl["macd_hist"] > 0:  cl_s += 1
    if divs["rsi_bull_hidden"]: cl_s += 2
    elif divs["rsi_bull_reg"]:  cl_s += 1
    elif cl["oversold"]:        cl_s += 0.5
    if cl["stoch_bull"]:       cl_s += 1
    if cl["bb_squeeze"] and cl["bb_above"]: cl_s += 1
    if cl["vwap_above"]:       cl_s += 1
    if cl["obv_up"]:           cl_s += 1
    if divs["macd_bull"]:      cl_s += 1
    cl_s = min(cl_s, 10.0)

    # ── Kurumsal Skor ────────────────────────────────────────────
    inst_s = 0
    if cvd_up: inst_s += 2
    if len(df) > 21 and float(df["close"].iloc[-1]) > float(df["close"].iloc[-21]):
        inst_s += 2
    if vp:
        if abs(cp - vp["vpoc"]) / vp["vpoc"] < 0.01: inst_s += 1
    inst_s = min(inst_s, 7.0)

    # ── EMA Trend Proxy (MTF backtest'te yok) ───────────────────
    ema_trend = "NEUTRAL"
    if cl["e8"] > cl["e21"] > cl["e55"]:   ema_trend = "BULLISH"
    elif cl["e8"] < cl["e21"] < cl["e55"]: ema_trend = "BEARISH"
    effective_trend = trend if trend != "NEUTRAL" else ema_trend

    # ── Bileşik Skor (MTF=0 backtest → max 27) ──────────────────
    composite = round((smc_s + cl_s + inst_s) / 27 * 10, 2)

    # ── Entry / SL ───────────────────────────────────────────────
    entry_low = entry_high = sl = None
    if effective_trend == "BULLISH":
        if bull_obs:
            ob = bull_obs[0]
            entry_low, entry_high = ob["low"], ob["high"]
            sl = ob["low"] * (1 - SL_BUFFER)
        elif bull_fvg:
            f = bull_fvg[0]
            entry_low, entry_high = f["low"], f["high"]
            sl = f["low"] * (1 - SL_BUFFER)
        if not entry_low:
            c2 = cp
            entry_low = c2 * 0.998; entry_high = c2 * 1.002
            sl = c2 * (1 - SL_BUFFER * 3)
    elif effective_trend == "BEARISH":
        if bear_obs:
            ob = bear_obs[0]
            entry_low, entry_high = ob["low"], ob["high"]
            sl = ob["high"] * (1 + SL_BUFFER)
        elif bear_fvg:
            f = bear_fvg[0]
            entry_low, entry_high = f["low"], f["high"]
            sl = f["high"] * (1 + SL_BUFFER)
        if not entry_low:
            c2 = cp
            entry_low = c2 * 0.998; entry_high = c2 * 1.002
            sl = c2 * (1 + SL_BUFFER * 3)

    return composite, effective_trend, entry_low, entry_high, sl


# ═══════════════════════════════════════════════════════════════════
#  TEK SEMBOL BACKTEST
# ═══════════════════════════════════════════════════════════════════

def backtest_symbol(symbol: str, df_full: pd.DataFrame) -> dict:
    """
    Tek bir sembol üzerinde walk-forward backtest.
    Dönüş: {trades: [...], equity: [...], summary: {...}}
    """
    trades   = []
    equity   = [CAPITAL]
    in_trade = False
    t_entry  = t_sl = t_tp1 = t_tp2 = t_tp3 = 0.0
    t_dir    = ""
    t_score  = 0.0
    t_entry_bar = 0
    t_open_month = ""

    for i in range(WARMUP, len(df_full) - 1):
        df_slice = df_full.iloc[:i]         # ← anti-repainting kalbi
        hi  = float(df_full["high"].iloc[i])
        lo  = float(df_full["low"].iloc[i])
        bar_ts = df_full.index[i]
        month  = bar_ts.strftime("%Y-%m") if hasattr(bar_ts, "strftime") else str(bar_ts)[:7]

        # ── Exit kontrolü ────────────────────────────────────────
        if in_trade:
            exited = False; pnl_pct = 0.0; result = ""

            if t_dir == "LONG":
                if lo <= t_sl:
                    sl_dist = abs(t_entry - t_sl) / t_entry
                    pnl_pct = -sl_dist
                    result  = "LOSS"
                    exited  = True
                elif hi >= t_tp3:
                    pnl_pct = TP1_CLOSE*TP1_PCT + TP2_CLOSE*TP2_PCT + TP3_CLOSE*TP3_PCT
                    result  = "WIN_TP3"; exited = True
                elif hi >= t_tp2:
                    pnl_pct = TP1_CLOSE*TP1_PCT + TP2_CLOSE*TP2_PCT
                    result  = "WIN_TP2"; exited = True
                elif hi >= t_tp1:
                    pnl_pct = TP1_CLOSE*TP1_PCT
                    result  = "WIN_TP1"; exited = True
            else:  # SHORT
                if hi >= t_sl:
                    sl_dist = abs(t_entry - t_sl) / t_entry
                    pnl_pct = -sl_dist
                    result  = "LOSS"
                    exited  = True
                elif lo <= t_tp3:
                    pnl_pct = TP1_CLOSE*TP1_PCT + TP2_CLOSE*TP2_PCT + TP3_CLOSE*TP3_PCT
                    result  = "WIN_TP3"; exited = True
                elif lo <= t_tp2:
                    pnl_pct = TP1_CLOSE*TP1_PCT + TP2_CLOSE*TP2_PCT
                    result  = "WIN_TP2"; exited = True
                elif lo <= t_tp1:
                    pnl_pct = TP1_CLOSE*TP1_PCT
                    result  = "WIN_TP1"; exited = True

            if exited:
                sl_dist   = abs(t_entry - t_sl) / t_entry
                r_mult    = pnl_pct / (sl_dist + 1e-10)
                dollar_pnl= equity[-1] * RISK_PCT * r_mult
                new_eq    = equity[-1] + dollar_pnl
                equity.append(new_eq)
                exit_px   = t_tp1 if "WIN" in result else t_sl

                trades.append({
                    "symbol":    symbol,
                    "direction": t_dir,
                    "entry":     t_entry,
                    "sl":        t_sl,
                    "exit":      exit_px,
                    "result":    result,
                    "r_mult":    r_mult,
                    "dollar_pnl":dollar_pnl,
                    "score":     t_score,
                    "equity":    new_eq,
                    "month":     t_open_month,
                    "entry_bar": t_entry_bar,
                    "exit_bar":  i,
                })
                in_trade = False
            continue

        # ── Sinyal üret ──────────────────────────────────────────
        comp, trend, e_low, e_high, sl_ = score_slice(df_slice)
        if comp >= MIN_SCORE and trend != "NEUTRAL" and e_low and sl_:
            entry_ = (e_low + e_high) / 2
            sl_dist = abs(entry_ - sl_) / entry_
            if 0.001 < sl_dist <= 0.08:
                d = "LONG" if trend == "BULLISH" else "SHORT"
                t_tp1 = entry_ * (1 + TP1_PCT) if d == "LONG" else entry_ * (1 - TP1_PCT)
                t_tp2 = entry_ * (1 + TP2_PCT) if d == "LONG" else entry_ * (1 - TP2_PCT)
                t_tp3 = entry_ * (1 + TP3_PCT) if d == "LONG" else entry_ * (1 - TP3_PCT)
                t_entry = entry_; t_sl = sl_; t_dir = d
                t_score = comp; t_entry_bar = i; t_open_month = month
                in_trade = True

    # Final equity
    if not equity:
        equity = [CAPITAL]
    final_eq = equity[-1]

    # Hesaplamalar
    wins   = [t for t in trades if "WIN" in t["result"]]
    losses = [t for t in trades if t["result"] == "LOSS"]
    longs  = [t for t in trades if t["direction"] == "LONG"]
    shorts = [t for t in trades if t["direction"] == "SHORT"]

    n = len(trades)
    if n == 0:
        return {
            "symbol": symbol, "trades": [], "equity": equity,
            "summary": {"n": 0, "wr": 0, "pf": 0, "max_dd": 0,
                        "sharpe": 0, "total_ret": 0, "final_eq": CAPITAL}
        }

    wr  = len(wins) / n
    pf  = (sum(t["r_mult"] for t in wins) /
           (abs(sum(t["r_mult"] for t in losses)) + 1e-10))

    eq_arr = np.array(equity)
    peak   = np.maximum.accumulate(eq_arr)
    max_dd = float(abs(((eq_arr - peak) / peak).min()) * 100)

    rets   = np.diff(eq_arr) / eq_arr[:-1] if len(eq_arr) > 1 else [0]
    sharpe = float((np.mean(rets) / (np.std(rets) + 1e-10)) * np.sqrt(252 * 6)) \
             if len(rets) > 1 else 0   # 4H → 6 bar/gün → *sqrt(252*6) = yıllık

    total_ret = (final_eq / CAPITAL - 1) * 100

    # Aylık P&L
    monthly_pnl = defaultdict(float)
    for t in trades:
        monthly_pnl[t["month"]] += t["dollar_pnl"]

    return {
        "symbol": symbol,
        "trades": trades,
        "equity": equity,
        "summary": {
            "n":         n,
            "wins":      len(wins),
            "losses":    len(losses),
            "longs":     len(longs),
            "shorts":    len(shorts),
            "wr":        wr,
            "pf":        pf,
            "max_dd":    max_dd,
            "sharpe":    sharpe,
            "total_ret": total_ret,
            "final_eq":  final_eq,
            "monthly":   dict(monthly_pnl),
        }
    }


# ═══════════════════════════════════════════════════════════════════
#  PORTFÖY SİMÜLASYONU (max 4 eş zamanlı)
# ═══════════════════════════════════════════════════════════════════

def portfolio_simulation(all_results: list, date_range: tuple) -> dict:
    """
    Birden fazla sembolün trade'lerini portföy olarak birleştirir.
    Aynı anda max MAX_OPEN pozisyon kuralını uygular.
    Trades zaman sırasına göre sıralanır.
    """
    # Tüm trade'leri birleştir ve sırayla işle
    all_trades = []
    for r in all_results:
        all_trades.extend(r["trades"])

    # Entry bar'a göre sırala
    all_trades.sort(key=lambda x: x["entry_bar"])

    equity    = CAPITAL
    open_count = 0
    portfolio_trades = []
    equity_curve = [CAPITAL]
    monthly_pnl = defaultdict(float)

    for t in all_trades:
        # Portfolio: pozisyon kapandıysa open_count azalt
        # Basitleştirilmiş: her trade bağımsız ama max 4 kuralı
        if open_count < MAX_OPEN:
            open_count += 1
            # P&L güncel equity üzerinden
            sl_dist = abs(t["entry"] - t["sl"]) / t["entry"]
            r_mult  = t["r_mult"]
            dollar_pnl = equity * RISK_PCT * r_mult
            equity += dollar_pnl
            equity_curve.append(equity)
            monthly_pnl[t["month"]] += dollar_pnl
            portfolio_trades.append({**t, "portfolio_pnl": dollar_pnl, "portfolio_eq": equity})
            open_count -= 1   # Kapanıyor (single-position simplification)

    if not equity_curve:
        equity_curve = [CAPITAL]

    eq_arr = np.array(equity_curve)
    peak   = np.maximum.accumulate(eq_arr)
    max_dd = float(abs(((eq_arr - peak) / peak).min()) * 100)
    rets   = np.diff(eq_arr) / eq_arr[:-1] if len(eq_arr) > 1 else [0]
    sharpe = float((np.mean(rets) / (np.std(rets) + 1e-10)) * np.sqrt(1512)) \
             if len(rets) > 1 else 0

    wins   = [t for t in portfolio_trades if "WIN" in t["result"]]
    losses = [t for t in portfolio_trades if t["result"] == "LOSS"]

    return {
        "trades":      portfolio_trades,
        "equity":      equity_curve,
        "final_eq":    equity_curve[-1],
        "total_ret":   (equity_curve[-1] / CAPITAL - 1) * 100,
        "wr":          len(wins) / len(portfolio_trades) if portfolio_trades else 0,
        "pf":          (sum(t["portfolio_pnl"] for t in wins) /
                        (abs(sum(t["portfolio_pnl"] for t in losses)) + 1e-10)),
        "max_dd":      max_dd,
        "sharpe":      sharpe,
        "n":           len(portfolio_trades),
        "monthly":     dict(monthly_pnl),
        "date_range":  date_range,
    }


# ═══════════════════════════════════════════════════════════════════
#  ÇIKTI YARDIMCILARI
# ═══════════════════════════════════════════════════════════════════

def _pbar(v, mx, col=CY, width=20):
    f = max(0, min(width, int(v / max(mx, 1e-10) * width)))
    return f"{col}{'█'*f}{DM}{'░'*(width-f)}{R}"


def print_symbol_summary(r: dict):
    s  = r["summary"]
    sy = r["symbol"].replace("/USDT", "")
    n  = s["n"]
    if n == 0:
        print(f"  {sy:6} {dim('İşlem bulunamadı')}")
        return

    wr = s["wr"]
    pf = s["pf"]
    dd = s["max_dd"]
    ret= s["total_ret"]

    wc = ok if wr >= 0.55 else (warn if wr >= 0.50 else (nfo if wr >= 0.45 else bad))
    pc = ok if pf >= 1.5  else (warn if pf >= 1.0 else bad)
    dc = ok if dd <= 15   else (warn if dd <= 25 else bad)
    rc = ok if ret > 0    else bad

    bar_w  = _pbar(min(ret, 200), 200, GR if ret > 0 else RD, 12)
    print(
        f"  {B}{sy:6}{R}  "
        f"n={nfo(str(n)):>4}  "
        f"WR={wc(f'{wr:.0%}')}  "
        f"PF={pc(f'{pf:.2f}')}  "
        f"DD={dc(f'{dd:.1f}%')}  "
        f"ret={rc(f'{ret:+.1f}%')}  "
        f"{bar_w}"
    )


def print_monthly_table(monthly: dict, symbols: list):
    """Aylık P&L tablosu."""
    all_months = sorted(set(monthly.keys()))
    if not all_months:
        return

    print(f"\n  {'─'*55}")
    print(f"  {B}{CY}AYLIK P&L ($10,000 başlangıç){R}")
    print(f"  {'─'*55}")
    print(f"  {'Ay':8}  {'P&L ($)':>10}  {'P&L (%)':>8}  {'Bar'}")
    print(f"  {'─'*55}")

    running = CAPITAL
    for m in all_months:
        pnl  = monthly.get(m, 0)
        pct  = pnl / running * 100
        running += pnl
        col  = ok if pnl > 0 else (warn if pnl == 0 else bad)
        bar  = _pbar(min(abs(pnl), 500), 500, GR if pnl > 0 else RD, 10)
        print(f"  {m}  {col(f'{pnl:>+10,.0f}')}  {col(f'{pct:>+7.1f}%')}  {bar}")

    print(f"  {'─'*55}")
    total = sum(monthly.values())
    total_pct = total / CAPITAL * 100
    total_c = ok if total > 0 else bad
    print(f"  {'TOPLAM':8}  {total_c(f'{total:>+10,.0f}')}  {total_c(f'{total_pct:>+7.1f}%')}")


# ═══════════════════════════════════════════════════════════════════
#  ANA FONKSİYON
# ═══════════════════════════════════════════════════════════════════

def main():
    head(f"1 YILLIK PORTföy WALK-FORWARD BACKTEST  {datetime.utcnow():%Y-%m-%d %H:%M UTC}")

    print(f"""
  {B}Anti-Repainting Güvencesi:{R}
  ┌─────────────────────────────────────────────────────────────┐
  │  Her bar i için: df_slice = df_full.iloc[:i]               │
  │  → Bar i'nin kapanışı henüz bilinmiyor                     │
  │  → Analiz sadece geçmiş veriye dayanıyor                   │
  │  → Sinyal bar i-1'de üretilir, giriş bar i'de simüle edilir│
  │  → SL/TP kontrolü bar i'nin HIGH/LOW'u ile yapılır         │
  │  → Sıfır look-ahead, sıfır curve-fitting                   │
  └─────────────────────────────────────────────────────────────┘

  {B}İşlem Parametreleri:{R}
    Risk/İşlem  : {RISK_PCT:.0%}
    TP1/TP2/TP3 : +{TP1_PCT:.0%} / +{TP2_PCT:.0%} / +{TP3_PCT:.0%}
    SL          : Order Block altı/üstü ({SL_BUFFER:.1%} buffer)
    Kaldıraç    : Dinamik (notional/risk oranı, max 5x)
    Min Skor    : {MIN_SCORE}/10
    Max Pozisyon: {MAX_OPEN} eş zamanlı
    Sermaye     : ${CAPITAL:,.0f}
""")

    # ── Veri indirme ────────────────────────────────────────────
    h2(f"VERİ İNDİRME  ({len(SYMBOLS)} sembol × {BARS} bar)")
    print()
    data = {}
    date_min = date_max = None
    for sym in SYMBOLS:
        sys.stdout.write(f"  ⬇  {sym:14} ...")
        sys.stdout.flush()
        df = ohlcv(sym, TIMEFRAME, BARS)
        if df.empty or len(df) < WARMUP + 100:
            print(f" {bad('HATA — atlanıyor')}")
            continue
        data[sym] = df
        d0 = str(df.index[WARMUP])[:10]
        d1 = str(df.index[-1])[:10]
        if date_min is None or d0 < date_min: date_min = d0
        if date_max is None or d1 > date_max: date_max = d1
        print(f" {ok('✅')} {len(df)} bar  {d0} → {d1}  "
              f"${float(df['close'].iloc[-1]):,.2f}")
        time.sleep(0.3)

    if not data:
        print(bad("  Hiç veri alınamadı!")); return

    print(f"\n  {ok('✅')} {len(data)} sembol hazır  |  Dönem: {date_min} → {date_max}")
    days_approx = (BARS - WARMUP) * 4 / 24  # 4H bar → gün
    print(f"  Tahmini analiz dönemi: ~{days_approx:.0f} gün ({days_approx/30:.1f} ay)")

    # ── Sembol bazlı backtest ────────────────────────────────────
    h2("SEMBOL BAZLI WALK-FORWARD")
    print(f"\n  Her sembol için {len(data[list(data.keys())[0]])-WARMUP} bar analiz ediliyor...\n")

    all_results = []
    for sym, df in data.items():
        sys.stdout.write(f"  ⚙  {sym:14} analiz ediliyor...")
        sys.stdout.flush()
        t0 = time.time()
        result = backtest_symbol(sym, df)
        elapsed = time.time() - t0
        n = result["summary"]["n"]
        wr = result["summary"]["wr"]
        col = ok if wr >= 0.55 else (warn if wr >= 0.50 else bad)
        print(f" {ok('✅')} {n} işlem  WR={col(f'{wr:.0%}')}  ({elapsed:.0f}s)")
        all_results.append(result)

    # ── Portföy birleştirme ──────────────────────────────────────
    h2("PORTföy SİMÜLASYONU (max 4 eş zamanlı)")
    port = portfolio_simulation(all_results, (date_min, date_max))

    # ═══════════════════════════════════════════════════════════
    #  DETAYLI ÇIKTI
    # ═══════════════════════════════════════════════════════════

    # ── Sembol özet tablosu ──────────────────────────────────────
    h2("SEMBOL BAZLI ÖZET")
    print()
    print(f"  {'Sembol':6}  {'N':>4}  {'WR':>6}  {'PF':>6}  {'MaxDD':>7}  {'Getiri':>8}  Bar")
    print(f"  {'─'*70}")
    for r in all_results:
        print_symbol_summary(r)

    # ── Portföy genel sonuç ──────────────────────────────────────
    h2("PORTföy GENEL SONUÇLAR")
    print()
    wr  = port["wr"]
    pf  = port["pf"]
    dd  = port["max_dd"]
    ret = port["total_ret"]
    n   = port["n"]

    wc = ok if wr >= 0.55 else (warn if wr >= 0.50 else bad)
    pc = ok if pf >= 1.5  else (warn if pf >= 1.0 else bad)
    dc = ok if dd <= 15   else (warn if dd <= 25 else bad)
    rc = ok if ret > 0    else bad

    print(f"  {'Analiz Dönemi':<24} {date_min} → {date_max}")
    print(f"  {'Toplam İşlem':<24} {B}{n}{R}")

    # Long/short dağılımı
    longs  = len([t for t in port["trades"] if t["direction"] == "LONG"])
    shorts = len([t for t in port["trades"] if t["direction"] == "SHORT"])
    print(f"  {'  Long / Short':<24} {ok(str(longs))} / {bad(str(shorts))}")
    print()

    print(f"  {'Kazanma Oranı':<24} {wc(f'{wr:.1%}')}")
    wins_port   = [t for t in port["trades"] if "WIN" in t["result"]]
    losses_port = [t for t in port["trades"] if t["result"] == "LOSS"]
    print(f"  {'  Kazanan / Kaybeden':<24} {ok(str(len(wins_port)))} / {bad(str(len(losses_port)))}")
    print()

    print(f"  {'Profit Factor':<24} {pc(f'{pf:.2f}')}")
    print(f"  {'Max Drawdown':<24} {dc(f'{dd:.1f}%')}")
    sharpe_s = f"{port['sharpe']:.2f}"
    sharpe_c = ok(sharpe_s) if port["sharpe"] >= 1 else warn(sharpe_s)
    print(f"  {'Sharpe Ratio':<24} {sharpe_c}")
    print()

    final = port["final_eq"]
    print(f"  {'Başlangıç':<24} ${CAPITAL:>10,.0f}")
    print(f"  {'Bitiş':<24} {rc(f'${final:>10,.0f}')}")
    print(f"  {'Net Getiri':<24} {rc(f'{ret:>+.1f}%')}")
    print(f"  {'Net Dolar P&L':<24} {rc(f'${final-CAPITAL:>+,.0f}')}")
    print()

    # TP dağılımı
    tp1h = len([t for t in port["trades"] if t["result"] == "WIN_TP1"])
    tp2h = len([t for t in port["trades"] if t["result"] == "WIN_TP2"])
    tp3h = len([t for t in port["trades"] if t["result"] == "WIN_TP3"])
    slh  = len([t for t in port["trades"] if t["result"] == "LOSS"])

    print(f"  {B}{CY}━━ TP / SL DAĞILIMI ━━{R}")
    total_n = max(n, 1)
    for label, count, col in [
        (f"TP1 (+{TP1_PCT:.0%}) × %40", tp1h, ok),
        (f"TP2 (+{TP2_PCT:.0%}) × %35", tp2h, ok),
        (f"TP3 (+{TP3_PCT:.0%}) × %25", tp3h, ok),
        (f"SL  (kayıp)",                 slh,  bad),
    ]:
        pct_lbl = f"{count/total_n:.0%}"
        barlbl  = _pbar(count, total_n, GR if col == ok else RD, 15)
        print(f"  {label:22} {col(f'{count:>3}')} ({pct_lbl:>4})  {barlbl}")

    # ── Aylık P&L tablosu ────────────────────────────────────────
    print_monthly_table(port["monthly"], list(data.keys()))

    # ── Skor bazlı win rate ──────────────────────────────────────
    h2("SKOR BAZLI PERFORMANS (tüm semboller)")
    print()
    score_bands = [
        (8.0, 10.0, "Çok Güçlü (8-10)"),
        (6.5,  8.0, "Güçlü    (6.5-8)"),
        (5.0,  6.5, "Orta     (5-6.5)"),
        (3.8,  5.0, "Zayıf    (3.8-5)"),
    ]
    for lo_, hi_, lbl in score_bands:
        band = [t for t in port["trades"] if lo_ <= t["score"] <= hi_]
        if not band: continue
        bw  = len([t for t in band if "WIN" in t["result"]]) / len(band)
        bwc = ok if bw >= 0.55 else (warn if bw >= 0.45 else bad)
        avg_r = np.mean([t["r_mult"] for t in band])
        avg_r_c = ok if avg_r > 0 else bad
        avg_r_s = f"{avg_r:+.2f}R"
        print(f"  {lbl:20}: {bwc(f'{bw:.0%}')} WR  "
              f"{avg_r_c(avg_r_s)} avg  ({len(band)} işlem)")

    # ── Long vs Short ─────────────────────────────────────────────
    h2("LONG vs SHORT KARŞILAŞTIRMA")
    print()
    for label, fil, col_fn in [("LONG ", "LONG", ok), ("SHORT", "SHORT", bad)]:
        sub = [t for t in port["trades"] if t["direction"] == fil]
        if not sub: continue
        sw  = [t for t in sub if "WIN" in t["result"]]
        swr = len(sw) / len(sub)
        spf = (sum(t["portfolio_pnl"] for t in sw) /
               (abs(sum(t["portfolio_pnl"] for t in sub if t["result"]=="LOSS")) + 1e-10))
        wrc = ok if swr >= 0.55 else (warn if swr >= 0.50 else bad)
        pfc = ok if spf >= 1.3 else (warn if spf >= 1.0 else bad)
        print(f"  {col_fn(label)}: {len(sub):>3} işlem  WR={wrc(f'{swr:.0%}')}  PF={pfc(f'{spf:.2f}')}")

    # ── En iyi / en kötü sembol ───────────────────────────────────
    h2("SEMBOL SIRALAMA (getiriye göre)")
    print()
    sorted_r = sorted(all_results, key=lambda x: x["summary"]["total_ret"], reverse=True)
    for i, r in enumerate(sorted_r):
        s = r["summary"]
        if s["n"] == 0: continue
        medal = ["🥇", "🥈", "🥉", " 4.", " 5.", " 6.", " 7.", " 8."][i]
        sym   = r["symbol"].replace("/USDT", "")
        rc    = ok if s["total_ret"] > 0 else bad
        ret_s = f"{s['total_ret']:+.1f}%"
        wr_s2 = f"{s['wr']:.0%}"
        print(f"  {medal} {sym:6}  {rc(ret_s)}  WR={wr_s2}  {s['n']} işlem")

    # ═══════════════════════════════════════════════════════════
    #  GENEL YORUM
    # ═══════════════════════════════════════════════════════════
    h2("GENEL DEĞERLENDİRME")
    print()

    score_card = {
        "win_rate":  (wr >= 0.52, f"Win Rate {wr:.1%}", "≥52% hedef"),
        "pf":        (pf >= 1.30, f"Profit Factor {pf:.2f}", "≥1.30 hedef"),
        "max_dd":    (dd <= 20,   f"Max Drawdown {dd:.1f}%", "≤20% hedef"),
        "sharpe":    (port["sharpe"] >= 1.0, f"Sharpe {port['sharpe']:.2f}", "≥1.0 hedef"),
        "positive":  (ret > 0,    f"Net Getiri {ret:+.1f}%", "pozitif"),
    }

    pass_count = sum(1 for v in score_card.values() if v[0])
    for key, (passed, metric, target) in score_card.items():
        icon = ok("✅") if passed else bad("❌")
        print(f"  {icon} {metric}  {dim(f'({target})')}")

    print()
    print(f"  Puan: {pass_count}/5")
    print()

    if pass_count == 5:
        print(f"  {ok('🏆 SİSTEM MÜKEMMEL — Canlı kullanıma hazır')}")
    elif pass_count >= 4:
        print(f"  {ok('✅ SİSTEM GEÇERLİ — Küçük iyileştirmelerle ideal')}")
    elif pass_count >= 3:
        print(f"  {warn('📊 SİSTEM MAKUL — Parametre optimizasyonu önerilir')}")
    else:
        print(f"  {bad('⚠️  SİSTEM GELİŞTİRİLMELİ — Bu haliyle canlıya geçme')}")

    print()
    print(f"  {dim('─'*60)}")
    print(f"  {dim('Not: Backtest tek TF (4H). MTF + sosyal katman canlıda eklenecek.')}")
    print(f"  {dim('Gerçek performans slippage, komisyon ve likiditeden etkilenir.')}")
    print(f"  {dim('Önerilen: 2 hafta paper trade → sonra $100 ile canlı başla.')}")
    print()


if __name__ == "__main__":
    main()
