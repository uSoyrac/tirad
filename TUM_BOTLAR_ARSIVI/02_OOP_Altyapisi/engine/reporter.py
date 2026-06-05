"""
bot/engine/reporter.py — Terminal Çıktı Formatlayıcı
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SignalResult → okunabilir terminal bloğu.
Renk kodları mevcut değilse graceful degradation.
"""

from __future__ import annotations

from typing import List

from bot.engine.base import Action, SignalResult, Trend

# ── Renk sabitleri ─────────────────────────────────────────────────────
try:
    from live_scan import ok, bad, warn, nfo, dim, B, R, GR, RD, YL, DM, CY
except ImportError:
    R = B = GR = RD = YL = DM = CY = ""
    def ok(s):   return s
    def bad(s):  return s
    def warn(s): return s
    def nfo(s):  return s
    def dim(s):  return s


# ══════════════════════════════════════════════════════════════════════
#  TEK SİNYAL RAPORU
# ══════════════════════════════════════════════════════════════════════

def print_signal(result: SignalResult) -> None:
    """
    Tek sinyal için zengin terminal çıktısı.

    Args:
        result: SignalEngine.analyze() çıktısı.
    """
    score    = result.composite
    trend    = result.direction
    action   = result.action.value

    score_c  = ok   if score >= 7.0 else (warn if score >= 5.5 else dim)
    trend_c  = ok   if trend == "LONG"   else bad
    action_c = ok   if "BUY" in action   else (bad if "SELL" in action else dim)

    bar = _mini_bar(score)
    smc_s = f"{result.smc_score:.1f}"
    adv_s = f"{result.adv_score:.1f}"

    print(f"\n  ╔{'═' * 64}╗")
    print(
        f"  ║  {B}{result.symbol:<12}{R}  {score_c(f'{score:.1f}/10')}  "
        f"{trend_c(trend):<8}  {bar}"
    )
    print(
        f"  ║  SMC: {nfo(smc_s)}  Confluence: {nfo(adv_s)}  "
        f"Onay: {nfo(str(result.confirmations))} gösterge"
    )
    print(f"  ╠{'═' * 64}╣")

    # Fiyat seviyeleri
    entry_s = f"{result.entry_price:,.4f}"
    sl_s    = f"{result.sl_price:,.4f}"
    tp1_s   = f"{result.tp1_price:,.4f}"
    tp2_s   = f"{result.tp2_price:,.4f}"
    tp3_s   = f"{result.tp3_price:,.4f}"

    print(f"  ║  Giriş : {nfo(entry_s)}    SL: {bad(sl_s)}")
    print(f"  ║  TP1   : {ok(tp1_s)}   TP2: {ok(tp2_s)}   TP3: {ok(tp3_s)}")
    print(f"  ╠{'═' * 64}╣")

    # Confluence detayları
    if result.confluence:
        cs = result.confluence
        det = cs.details

        ib_bk   = det.get("ib",  {}).get("ib_breakout",    "?")
        adr_sg  = det.get("adr", {}).get("adr_signal",     "?")
        adr_pu  = det.get("adr", {}).get("adr_pct_used",    0)
        poc_t   = det.get("poc", {}).get("confluence_type", "?")
        oi_t    = det.get("oi",  {}).get("oi_trend",        "?")
        fr_sg   = det.get("fr",  {}).get("fr_signal",       "?")
        fr_val  = det.get("fr",  {}).get("fr_pct",           0)
        vwap_p  = det.get("vwap",    {}).get("band_position",   "?")
        wyck_p  = det.get("wyckoff", {}).get("wyckoff_phase",   "?")
        sess_s  = det.get("session", {}).get("current_session", "?")
        in_kz   = det.get("session", {}).get("in_kill_zone",    False)

        ib_c   = ok if ib_bk == "BULL"   else (bad  if ib_bk == "BEAR"   else dim)
        adr_c  = ok if adr_sg == "ROOM"  else (warn if adr_sg == "NEUTRAL" else bad)
        poc_c  = ok if "BULL" in poc_t   else (bad  if "BEAR"  in poc_t   else dim)
        oi_c   = ok if "BULL" in oi_t    else (bad  if "BEAR"  in oi_t    else dim)
        vwap_c = ok if "LOW"  in vwap_p  else (bad  if "HIGH"  in vwap_p  else dim)

        fr_val_s = f"{fr_val:+.4f}%"
        adr_pu_s = f"{adr_pu:.0f}%"

        print(f"  ║  IB Kırılma  : {ib_c(ib_bk):<10}  ADR: {adr_c(adr_sg)} ({adr_pu_s})")
        print(f"  ║  POC Conf.   : {poc_c(poc_t):<14}  OI: {oi_c(oi_t)}")
        print(f"  ║  Funding     : {fr_val_s}  {dim(fr_sg[:22])}")
        print(f"  ║  VWAP Bant   : {vwap_c(vwap_p):<16}  Wyckoff: {nfo(wyck_p[:18])}")

        sess_label = f"{nfo(sess_s)}"
        kz_label   = f"  {'🎯 Kill Zone' if in_kz else ''}"
        print(f"  ║  Seans       : {sess_label}{kz_label}")

    # Uyarılar
    if result.filter_warnings:
        print(f"  ╠{'═' * 64}╣")
        for w in result.filter_warnings:
            print(f"  ║  ⚠  {warn(w[:60])}")

    # Karar
    print(f"  ╠{'═' * 64}╣")
    print(
        f"  ║  KARAR: {action_c(f'{action:<14}')}  "
        f"Seans: {nfo(result.session)}"
    )

    if result.funding_rate is not None:
        fr_disp = f"{result.funding_rate * 100:+.4f}%"
        print(f"  ║  Funding Rate: {nfo(fr_disp)}")

    print(f"  ║  {dim(result.timestamp[:19] + ' UTC')}")
    print(f"  ╚{'═' * 64}╝\n")


# ══════════════════════════════════════════════════════════════════════
#  ÇOKLU SINYAL ÖZETİ
# ══════════════════════════════════════════════════════════════════════

def print_scan_summary(results: List[SignalResult]) -> None:
    """
    Tarama sonucu özet tablosu.

    Args:
        results: Skora göre sıralanmış SignalResult listesi.
    """
    if not results:
        print(f"\n  {warn('Sinyal bulunamadı.')}\n")
        return

    header_sym    = "Sembol"
    header_score  = "Skor"
    header_dir    = "Yön"
    header_action = "Karar"
    header_conf   = "Onay"
    header_sess   = "Seans"

    print(f"\n  {'─' * 68}")
    print(
        f"  {B}{header_sym:<14}{header_score:>6}  {header_dir:<8}"
        f"{header_action:<14}{header_conf:>5}  {header_sess}{R}"
    )
    print(f"  {'─' * 68}")

    for r in results:
        score_s  = f"{r.composite:.1f}"
        dir_c    = ok  if r.direction == "LONG" else bad
        act_c    = ok  if "BUY" in r.action.value else bad
        sc       = ok  if r.composite >= 7.0 else (warn if r.composite >= 5.5 else dim)

        print(
            f"  {B}{r.symbol:<14}{R}{sc(f'{score_s:>6}')}  "
            f"{dir_c(f'{r.direction:<8}')}"
            f"{act_c(f'{r.action.value:<14}')}"
            f"{nfo(str(r.confirmations)):>5}  "
            f"{dim(r.session)}"
        )

    print(f"  {'─' * 68}")
    print(f"  Toplam: {B}{len(results)}{R} sinyal\n")


# ──────────────────────────────────────────────────────────────────────
def _mini_bar(v: float, mx: float = 10.0, width: int = 8) -> str:
    """ASCII mini progress bar."""
    filled = max(0, min(width, int(v / mx * width)))
    bar    = f"{GR}{'█' * filled}{DM}{'░' * (width - filled)}{R}"
    return bar
