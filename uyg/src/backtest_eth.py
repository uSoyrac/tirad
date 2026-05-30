#!/usr/bin/env python3
"""
ETH/USDT — Tam SMC/ICT Walk-Forward Backtest
live_scan.py motorunu kullanır; her bar için df.iloc[:i] ile analiz eder.
Anti-repainting garantili: geleceği görmeyen walk-forward.
"""
import warnings; warnings.filterwarnings("ignore")
import sys, time, math
from datetime import datetime
import numpy as np
import pandas as pd

# ── live_scan fonksiyonlarını import et ─────────────────────
from live_scan import (
    ohlcv,
    market_structure, order_blocks, fair_value_gaps,
    liquidity_map, displacement, optimal_trade_entry,
    volume_profile, wyckoff_phase, supply_demand_zones,
    divergences, classic_indicators, cvd,
    R,B,U,GR,RD,YL,CY,MG,DM,BL,
    ok,bad,warn,nfo,mag,dim,sep,head,h2
)

# ─── Renk kısayolları ─────────────────────────────────────────
def pbar(v, mx, col=CY):
    f=int(v/mx*24); e=24-f
    return f"{col}{'█'*f}{DM}{'░'*e}{R} {B}{v:.1f}/{mx}{R}"

# ═══════════════════════════════════════════════════════════════
#  PARAMETRE
# ═══════════════════════════════════════════════════════════════
SYMBOL      = "ETH/USDT"
TIMEFRAME   = "4h"
BARS        = 800        # Kaç bar indirilsin
MIN_SCORE   = 3.8        # Sinyal için min composite skor (MTF yok → ~27 puan max)
RISK_PCT    = 0.02       # İşlem başına %2 risk
SL_BUFFER   = 0.005      # OB altı/üstü buffer
TP1_PCT     = 0.06       # TP1 hedefi (%6)
TP2_PCT     = 0.14       # TP2 hedefi (%14)
TP3_PCT     = 0.28       # TP3 hedefi (%28)
TP1_CLOSE   = 0.40       # TP1'de kapat %40
TP2_CLOSE   = 0.35
TP3_CLOSE   = 0.25
CAPITAL     = 10_000.0
WARMUP      = 120        # İlk N bar ısınma (SMC için yeterli geçmiş)

# ═══════════════════════════════════════════════════════════════
#  SINYAL FONKSİYONU — live_scan motorunu çağırır
# ═══════════════════════════════════════════════════════════════

def score_slice(df_slice):
    """
    df_slice üzerinde tam SMC+Classic+Inst+MTF analizi.
    Döner: (composite_score 0-10, trend, entry_low, entry_high, sl)
    """
    if len(df_slice) < 80:
        return 0, "NEUTRAL", None, None, None

    df = df_slice.copy()

    try:
        ms          = market_structure(df, 10)
        bull_obs, bear_obs, bull_brk, bear_brk = order_blocks(df)
        bull_fvg, bear_fvg = fair_value_gaps(df)
        bsl, ssl, sweep_up, sweep_down = liquidity_map(df)
        disps       = displacement(df)
        ote         = optimal_trade_entry(df)
        vp          = volume_profile(df)
        wyck        = wyckoff_phase(df)
        demand_z, supply_z = supply_demand_zones(df)
        divs        = divergences(df)
        cl          = classic_indicators(df)
        cvd_up      = cvd(df)
    except Exception:
        return 0, "NEUTRAL", None, None, None

    trend = ms["trend"]
    cp    = float(df["close"].iloc[-1])

    # ── SMC Puanlama ────────────────────────────────────────
    smc_s = 0
    if trend == "BULLISH":
        if ms["bos_bull"]:   smc_s += 2
        if ms["choch_bull"]: smc_s += 1
        if ms["mss_bull"]:   smc_s += 1
        if bull_obs:
            ob = bull_obs[0]
            smc_s += 2
        if bull_brk:         smc_s += 1
        if bull_fvg:         smc_s += 1
        if sweep_down:       smc_s += 2
        if ote and ote["bull_ote"]: smc_s += 1
        if demand_z:
            d = demand_z[0]
            if d["bot"] <= cp <= d["top"]: smc_s += 1
        if wyck in ("WYCKOFF_ACCUMULATION", "SELLING_CLIMAX_ZONE"): smc_s += 1
    elif trend == "BEARISH":
        if ms["bos_bear"]:   smc_s += 2
        if ms["choch_bear"]: smc_s += 1
        if ms["mss_bear"]:   smc_s += 1
        if bear_obs:         smc_s += 2
        if bear_brk:         smc_s += 1
        if bear_fvg:         smc_s += 1
        if sweep_up:         smc_s += 2
        if ote and ote["bear_ote"]: smc_s += 1
        if supply_z:
            s = supply_z[0]
            if s["bot"] <= cp <= s["top"]: smc_s += 1
        if wyck in ("DISTRIBUTION_ZONE",): smc_s += 1

    if disps:
        d = disps[0]
        if (d["direction"] == "UP" and trend == "BULLISH") or \
           (d["direction"] == "DOWN" and trend == "BEARISH"):
            smc_s += 0.5
    smc_s = min(smc_s, 10.0)

    # ── Klasik Puanlama ─────────────────────────────────────
    cl_s = 0
    if cl["ema_full"]:        cl_s += 2
    elif cl["ema_part"]:      cl_s += 1
    if cl["macd_bull"]:       cl_s += 2
    elif cl["macd_hist"] > 0: cl_s += 1
    if divs["rsi_bull_hidden"]: cl_s += 2
    elif divs["rsi_bull_reg"]:  cl_s += 1
    elif cl["oversold"]:        cl_s += 0.5
    if cl["stoch_bull"]:      cl_s += 1
    if cl["bb_squeeze"] and cl["bb_above"]: cl_s += 1
    if cl["vwap_above"]:      cl_s += 1
    if cl["obv_up"]:          cl_s += 1
    if divs["macd_bull"]:     cl_s += 1
    cl_s = min(cl_s, 10.0)

    # ── Kurumsal Puanlama ────────────────────────────────────
    inst_s = 0
    if cvd_up:                inst_s += 2
    price_up = float(df["close"].iloc[-1]) > float(df["close"].iloc[-21]) if len(df) > 21 else False
    if price_up:              inst_s += 2
    if vp:
        near_vpoc = abs(cp - vp["vpoc"]) / vp["vpoc"] < 0.01
        if near_vpoc:         inst_s += 1
    inst_s = min(inst_s, 7.0)

    # ── MTF skoru burada sadece 4H (tek TF backtest) ─────────
    mtf_s = 0  # Backtest'te multi-TF yok (hız için)

    # ── Yönü EMA'dan da türet (SMC NEUTRAL olsa bile) ─────────
    # Backtest'te MTF yok — EMA yönü trend proxy olarak kullan
    ema_trend = "NEUTRAL"
    if cl["e8"] > cl["e21"] > cl["e55"]:
        ema_trend = "BULLISH"
    elif cl["e8"] < cl["e21"] < cl["e55"]:
        ema_trend = "BEARISH"

    # Etkili trend: SMC net ise onu kullan, NEUTRAL ise EMA'yı kullan
    effective_trend = trend if trend != "NEUTRAL" else ema_trend

    # ── Denominatör backtest için 27 (MTF=0 çünkü tek TF) ────
    raw       = smc_s + cl_s + inst_s   # MTF = 0
    composite = round((raw / 27) * 10, 2)

    # ── Entry/SL hesabı ──────────────────────────────────────
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
        if not entry_low:    # Fallback: fiyatın kendisi entry
            cp2 = float(df["close"].iloc[-1])
            entry_low = cp2 * 0.998; entry_high = cp2 * 1.002
            sl = cp2 * (1 - SL_BUFFER * 3)
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
            cp2 = float(df["close"].iloc[-1])
            entry_low = cp2 * 0.998; entry_high = cp2 * 1.002
            sl = cp2 * (1 + SL_BUFFER * 3)

    return composite, effective_trend, entry_low, entry_high, sl


# ═══════════════════════════════════════════════════════════════
#  WALK-FORWARD BACKTEST
# ═══════════════════════════════════════════════════════════════

def run_eth_backtest():
    head(f"ETH/USDT WALK-FORWARD BACKTEST  {datetime.utcnow():%Y-%m-%d %H:%M UTC}")

    # ── Veri indir ────────────────────────────────────────────
    h2("VERİ İNDİRME")
    print(f"  {nfo(SYMBOL)} {TIMEFRAME}  {BARS} bar  ...")
    df_full = ohlcv(SYMBOL, TIMEFRAME, BARS)
    if df_full.empty:
        print(bad("  ❌ Veri alınamadı — Binance bağlantısını kontrol et")); return

    print(f"  {ok('✅')} {len(df_full)} bar alındı: "
          f"{df_full.index[0]:%Y-%m-%d} → {df_full.index[-1]:%Y-%m-%d}")
    print(f"  Fiyat aralığı: ${df_full['low'].min():,.0f} – ${df_full['high'].max():,.0f}")

    # ── Walk-forward tarama ───────────────────────────────────
    h2("WALK-FORWARD ANALİZ")
    print(f"  Her bar için df.iloc[:i] analizi (anti-repainting)...")
    print()

    trades     = []
    equity     = [CAPITAL]
    in_trade   = False
    t_entry    = t_sl = t_tp1 = t_tp2 = t_tp3 = 0
    t_dir      = ""
    t_score    = 0
    t_entry_bar= 0
    bar_signals = []    # (bar_i, score, trend)

    total_bars = len(df_full) - WARMUP
    last_pct   = -1

    for i in range(WARMUP, len(df_full) - 1):
        # İlerleme çubuğu
        pct = int((i - WARMUP) / total_bars * 100)
        if pct != last_pct and pct % 10 == 0:
            sys.stdout.write(f"\r  Bar {i}/{len(df_full)-1}  [{pct}%] ...")
            sys.stdout.flush()
            last_pct = pct

        df_slice = df_full.iloc[:i]   # Kapanmış mumlar — geleceği görmez
        hi  = float(df_full["high"].iloc[i])
        lo  = float(df_full["low"].iloc[i])
        cl_ = float(df_full["close"].iloc[i])

        # ── Açık pozisyon varsa exit kontrolü ────────────────
        if in_trade:
            exited = False
            pnl    = 0.0
            result = ""

            if t_dir == "LONG":
                if lo <= t_sl:
                    pnl    = (t_sl - t_entry) / t_entry
                    result = "LOSS"
                    exited = True
                elif hi >= t_tp3:
                    pnl    = TP1_CLOSE*TP1_PCT + TP2_CLOSE*TP2_PCT + TP3_CLOSE*TP3_PCT
                    result = "WIN_3"
                    exited = True
                elif hi >= t_tp2:
                    pnl    = TP1_CLOSE*TP1_PCT + TP2_CLOSE*TP2_PCT
                    result = "WIN_2"
                    exited = True
                elif hi >= t_tp1:
                    pnl    = TP1_CLOSE*TP1_PCT
                    result = "WIN_1"
                    exited = True

            else:  # SHORT
                if hi >= t_sl:
                    pnl    = -(t_sl - t_entry) / t_entry
                    result = "LOSS"
                    exited = True
                elif lo <= t_tp3:
                    pnl    = TP1_CLOSE*TP1_PCT + TP2_CLOSE*TP2_PCT + TP3_CLOSE*TP3_PCT
                    result = "WIN_3"
                    exited = True
                elif lo <= t_tp2:
                    pnl    = TP1_CLOSE*TP1_PCT + TP2_CLOSE*TP2_PCT
                    result = "WIN_2"
                    exited = True
                elif lo <= t_tp1:
                    pnl    = TP1_CLOSE*TP1_PCT
                    result = "WIN_1"
                    exited = True

            if exited:
                dollar_pnl = equity[-1] * RISK_PCT * (pnl / (abs(t_entry - t_sl) / t_entry + 1e-10))
                # Basit: pnl direkt R değeri olarak hesapla
                sl_dist = abs(t_entry - t_sl) / t_entry
                r_mult  = pnl / (sl_dist + 1e-10) if sl_dist > 0 else 0
                dollar_pnl = equity[-1] * RISK_PCT * r_mult
                new_eq  = equity[-1] + dollar_pnl
                equity.append(new_eq)

                trades.append({
                    "entry_bar": t_entry_bar,
                    "exit_bar":  i,
                    "direction": t_dir,
                    "entry":     t_entry,
                    "sl":        t_sl,
                    "tp1":       t_tp1,
                    "exit_price":t_tp1 if "WIN" in result else t_sl,
                    "pnl_pct":   pnl,
                    "r_mult":    r_mult,
                    "dollar_pnl":dollar_pnl,
                    "result":    result,
                    "score":     t_score,
                    "equity":    new_eq,
                })
                in_trade = False
            continue   # Pozisyon açıkken yeni sinyal bakma

        # ── Yeni sinyal üret ─────────────────────────────────
        comp, trend, e_low, e_high, sl_ = score_slice(df_slice)

        if comp >= MIN_SCORE and trend != "NEUTRAL" and e_low and sl_:
            entry_ = (e_low + e_high) / 2
            sl_dist = abs(entry_ - sl_) / entry_
            if sl_dist <= 0.08:   # Max %8 SL
                if trend == "BULLISH":
                    tp1_ = entry_ * (1 + TP1_PCT)
                    tp2_ = entry_ * (1 + TP2_PCT)
                    tp3_ = entry_ * (1 + TP3_PCT)
                else:
                    tp1_ = entry_ * (1 - TP1_PCT)
                    tp2_ = entry_ * (1 - TP2_PCT)
                    tp3_ = entry_ * (1 - TP3_PCT)

                t_entry = entry_; t_sl = sl_
                t_tp1 = tp1_; t_tp2 = tp2_; t_tp3 = tp3_
                t_dir = "LONG" if trend == "BULLISH" else "SHORT"
                t_score = comp; t_entry_bar = i
                in_trade = True
                bar_signals.append((i, comp, trend))

    print(f"\r  {ok('✅')} {len(df_full)-WARMUP} bar analiz edildi, {len(trades)} işlem bulundu")

    # ═══════════════════════════════════════════════════════════
    #  SONUÇLAR
    # ═══════════════════════════════════════════════════════════
    h2("BACKTEST SONUÇLARI")
    print()

    if not trades:
        print(bad(f"  Hiç işlem bulunamadı (min skor {MIN_SCORE} — skor eşiğini düşürmeyi dene)"))
        return

    # ── Temel istatistikler ───────────────────────────────────
    wins   = [t for t in trades if "WIN" in t["result"]]
    losses = [t for t in trades if t["result"] == "LOSS"]
    longs  = [t for t in trades if t["direction"] == "LONG"]
    shorts = [t for t in trades if t["direction"] == "SHORT"]

    win_rate  = len(wins) / len(trades)
    avg_win_r = np.mean([t["r_mult"] for t in wins]) if wins else 0
    avg_los_r = abs(np.mean([t["r_mult"] for t in losses])) if losses else 0
    pf        = (sum(t["r_mult"] for t in wins) /
                 (abs(sum(t["r_mult"] for t in losses)) + 1e-10))

    total_dollar = sum(t["dollar_pnl"] for t in trades)
    final_eq  = equity[-1]

    # Max Drawdown
    eq_arr  = np.array(equity)
    peak    = np.maximum.accumulate(eq_arr)
    dd_arr  = (eq_arr - peak) / peak
    max_dd  = abs(dd_arr.min()) * 100

    # Sharpe
    rets    = np.diff(eq_arr) / eq_arr[:-1] if len(eq_arr) > 1 else [0]
    sharpe  = (np.mean(rets) / (np.std(rets) + 1e-10)) * np.sqrt(252) if len(rets) > 1 else 0

    # Avg holding bars
    avg_bars = np.mean([t["exit_bar"] - t["entry_bar"] for t in trades])
    avg_h_str = f"{avg_bars*4:.0f}s"  # 4H * bar = saat

    # ── Ana tablo ─────────────────────────────────────────────
    w_c = ok if win_rate >= 0.52 else (warn if win_rate >= 0.45 else bad)
    p_c = ok if pf >= 1.3 else (warn if pf >= 1.0 else bad)
    d_c = ok if max_dd <= 15 else (warn if max_dd <= 25 else bad)
    s_c = ok if sharpe >= 1.0 else (warn if sharpe >= 0.5 else bad)

    print(f"  {'─'*60}")
    print(f"  {B}SEMBOL    :{R} {nfo(SYMBOL)}  {TIMEFRAME}  {len(df_full)} bar")
    print(f"  {B}DÖNEM     :{R} {df_full.index[WARMUP]:%Y-%m-%d} → {df_full.index[-1]:%Y-%m-%d}")
    print(f"  {B}MIN SKOR  :{R} {MIN_SCORE}  (sinyal eşiği)")
    print(f"  {'─'*60}")
    print()
    print(f"  {'Toplam İşlem':<22} {B}{len(trades)}{R}")
    print(f"  {'  Long':<22} {ok(str(len(longs)))}")
    print(f"  {'  Short':<22} {bad(str(len(shorts)))}")
    print(f"  {'Kazanma Oranı':<22} {w_c(f'{win_rate:.1%}')}  (hedef: >52%)")
    print(f"  {'  Win / Loss':<22} {ok(str(len(wins)))} / {bad(str(len(losses)))}")
    print()
    print(f"  {'Ort Kazanç (R)':<22} {ok(f'+{avg_win_r:.2f}R')}")
    print(f"  {'Ort Kayıp (R)':<22} {bad(f'-{avg_los_r:.2f}R')}")
    print(f"  {'Profit Factor':<22} {p_c(f'{pf:.2f}')}  (hedef: >1.3)")
    print()
    print(f"  {'Max Drawdown':<22} {d_c(f'%{max_dd:.1f}')}  (hedef: <%20)")
    print(f"  {'Sharpe Ratio':<22} {s_c(f'{sharpe:.2f}')}  (hedef: >1.0)")
    print(f"  {'Ort Pozisyon Süresi':<22} {nfo(avg_h_str)}")
    print()
    total_ret_pct = (final_eq / CAPITAL - 1) * 100
    tr_c = ok if total_ret_pct > 0 else bad
    print(f"  {'Başlangıç Sermaye':<22} ${CAPITAL:,.0f}")
    print(f"  {'Bitiş Sermaye':<22} {tr_c(f'${final_eq:,.0f}')}")
    print(f"  {'Toplam Getiri':<22} {tr_c(f'{total_ret_pct:+.1f}%')}")
    print(f"  {'Net Dolar P&L':<22} {tr_c(f'${total_dollar:+,.0f}')}")
    print()

    # ── Puan çubukları ────────────────────────────────────────
    print(f"  Win Rate     {pbar(win_rate*10, 10, GR if win_rate>=0.52 else YL)}")
    print(f"  Prof Factor  {pbar(min(pf,5), 5, GR if pf>=1.3 else YL)}")
    pnl_bar = min(max(total_ret_pct/2, 0), 10)
    print(f"  Net Getiri   {pbar(pnl_bar, 10, GR if total_ret_pct>0 else RD)}")
    dd_score = max(0, 10 - max_dd/3)
    print(f"  DD Kontrolü  {pbar(dd_score, 10, GR if max_dd<=15 else(YL if max_dd<=25 else RD))}")

    # ── TP dağılımı ───────────────────────────────────────────
    tp1_hits = len([t for t in wins if t["result"] == "WIN_1"])
    tp2_hits = len([t for t in wins if t["result"] == "WIN_2"])
    tp3_hits = len([t for t in wins if t["result"] == "WIN_3"])
    print(f"\n  {B}{CY}━━ TP DAĞILIMI ━━{R}")
    print(f"  TP1 (+%6)    {ok(str(tp1_hits))} işlem")
    print(f"  TP2 (+%14)   {ok(str(tp2_hits))} işlem")
    print(f"  TP3 (+%28)   {ok(str(tp3_hits))} işlem")
    print(f"  SL (-kayıp)  {bad(str(len(losses)))} işlem")

    # ── Skor bazlı istatistik ─────────────────────────────────
    print(f"\n  {B}{CY}━━ SKOR BAZLI WIN RATE ━━{R}")
    score_bands = [(8.0, 10.0, "Güçlü"), (6.5, 8.0, "Orta-Yüksek"),
                   (5.5, 6.5, "Orta")]
    for lo_, hi_, lbl in score_bands:
        band = [t for t in trades if lo_ <= t["score"] <= hi_]
        if not band: continue
        bw = len([t for t in band if "WIN" in t["result"]]) / len(band)
        bw_c = ok if bw >= 0.55 else (warn if bw >= 0.45 else bad)
        print(f"  {lbl:14} ({lo_:.1f}–{hi_:.1f}): {bw_c(f'{bw:.0%}')}  ({len(band)} işlem)")

    # ── Long vs Short ─────────────────────────────────────────
    print(f"\n  {B}{CY}━━ LONG vs SHORT ━━{R}")
    for label, subset, col in [("LONG ", longs, ok), ("SHORT", shorts, bad)]:
        if not subset: continue
        sw   = [t for t in subset if "WIN" in t["result"]]
        swr  = len(sw)/len(subset)
        spf_ = sum(t["r_mult"] for t in sw) / (abs(sum(t["r_mult"] for t in subset if t["result"]=="LOSS"))+1e-10)
        swr_c = ok if swr >= 0.52 else (warn if swr >= 0.45 else bad)
        print(f"  {col(label)}: {len(subset)} işlem  WR={swr_c(f'{swr:.0%}')}  PF={spf_:.2f}")

    # ── Son 10 işlem ──────────────────────────────────────────
    print(f"\n  {B}{CY}━━ SON 10 İŞLEM ━━{R}")
    print(f"  {'Yön':6} {'Giriş':>10} {'Çıkış':>10} {'R':>6} {'$P&L':>8} {'Skor':>5} {'Sonuç'}")
    sep("─")
    for t in trades[-10:]:
        res_c = ok if "WIN" in t["result"] else bad
        dir_c = ok("L") if t["direction"] == "LONG" else bad("S")
        r_s    = f"{t['r_mult']:+.2f}R"
        r_c    = ok if t["r_mult"] > 0 else bad
        dpnl_s = f"${t['dollar_pnl']:+,.0f}"
        dpnl_c = ok(dpnl_s) if t["dollar_pnl"] > 0 else bad(dpnl_s)
        res_s  = t["result"]
        score_s= f"{t['score']:.1f}"
        print(f"  {dir_c}      ${t['entry']:>9,.1f} ${t['exit_price']:>9,.1f} "
              f"{r_c(r_s)}  {dpnl_c}  {score_s}  {res_c(res_s)}")

    # ── Sonuç yorumu ──────────────────────────────────────────
    h2("YORUM")
    print()
    verdict = []
    if win_rate >= 0.55:   verdict.append(ok(f"✅ Win Rate {win_rate:.0%} — hedefin üstünde"))
    elif win_rate >= 0.50: verdict.append(warn(f"⚠️  Win Rate {win_rate:.0%} — sınırda"))
    else:                  verdict.append(bad(f"❌ Win Rate {win_rate:.0%} — hedefin altında"))

    if pf >= 1.5:    verdict.append(ok(f"✅ Profit Factor {pf:.2f} — mükemmel"))
    elif pf >= 1.3:  verdict.append(ok(f"✅ Profit Factor {pf:.2f} — iyi"))
    elif pf >= 1.0:  verdict.append(warn(f"⚠️  Profit Factor {pf:.2f} — breakeven yakını"))
    else:            verdict.append(bad(f"❌ Profit Factor {pf:.2f} — kârsız"))

    if max_dd <= 15:  verdict.append(ok(f"✅ Max DD %{max_dd:.1f} — kontrollü"))
    elif max_dd <= 25:verdict.append(warn(f"⚠️  Max DD %{max_dd:.1f} — dikkat"))
    else:             verdict.append(bad(f"❌ Max DD %{max_dd:.1f} — yüksek risk"))

    if sharpe >= 1.5:  verdict.append(ok(f"✅ Sharpe {sharpe:.2f} — excellent"))
    elif sharpe >= 1.0:verdict.append(ok(f"✅ Sharpe {sharpe:.2f} — iyi"))
    else:              verdict.append(warn(f"⚠️  Sharpe {sharpe:.2f}"))

    for v in verdict:
        print(f"  {v}")

    print()
    overall = (1 if win_rate>=0.52 else 0) + (1 if pf>=1.3 else 0) + \
              (1 if max_dd<=20 else 0) + (1 if sharpe>=1.0 else 0)
    if overall >= 4:
        print(f"  {ok('🏆 SİSTEM GEÇERLİ — Canlı kullanıma uygun (gerçek performans farklı olabilir)')}")
    elif overall >= 3:
        print(f"  {warn('📊 SİSTEM MAKUL — Parametre iyileştirmesi yapılabilir')}")
    elif overall >= 2:
        print(f"  {warn('⚠️  SİSTEM SINIRDA — Dikkatli kullan, daha fazla optimizasyon gerekli')}")
    else:
        print(f"  {bad('❌ SİSTEM YETERSİZ — Bu parametre setiyle kullanma')}")

    print()
    print(f"  {dim('Not: Bu backtest 4H data + SMC/ICT motoru + %2 risk ile walk-forward çalışır.')}")
    print(f"  {dim('MTF (1D/1W/1H) konfirmasyonu backtest hızı için devre dışı bırakıldı.')}")
    print(f"  {dim('Canlı sistemde MTF + sosyal katman eklendiğinde win rate artması beklenir.')}")
    print()


if __name__ == "__main__":
    run_eth_backtest()
