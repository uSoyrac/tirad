"""
bot/signal_engine.py — Birleştirilmiş Sinyal Motoru v2
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tüm analiz katmanlarını bir araya getirir:

  Katman 1: SMC + ICT (live_scan.py) — temel teknik analiz
  Katman 2: Gelişmiş indikatörler (advanced_indicators.py)
             IB, ADR, POC Confluence, OI, Funding Rate,
             Session, VWAP Bands, Wyckoff Gelişmiş
  Katman 3: Multi-Agent Münazara (agents/debate.py)
             Bull/Bear tartışması → Portföy Müdürü kararı
             Ollama mevcut değilse kural tabanlı fallback

  Nihai skor = SMC skoru (60%) + Gelişmiş skor (25%) + Ajan kararı (15%)

Kullanım:
  from bot.signal_engine import analyze_full
  result = analyze_full("ETH/USDT", social_data=social)
"""

import logging
import time
from typing import Optional

logger = logging.getLogger("bot.signal_engine")


# ══════════════════════════════════════════════════════════════════════
#  TAM ANALİZ
# ══════════════════════════════════════════════════════════════════════

def analyze_full(
    symbol:       str,
    social_data:  Optional[dict] = None,
    use_debate:   bool = True,
    debate_rounds: int = 1,
) -> Optional[dict]:
    """
    Bir sembol için tüm katmanlı analizi çalıştırır.

    Args:
        symbol:        "ETH/USDT" formatında
        social_data:   {mentions, score, label, headlines} — sosyal veri
        use_debate:    True → ajan münazarası çalıştır
        debate_rounds: Münazara tur sayısı

    Döner: dict veya None (analiz başarısızsa)
    """
    from live_scan import ohlcv, analyze
    from bot.advanced_indicators import (
        advanced_composite_score,
        fetch_oi_and_funding,
    )
    from agents.debate import (
        TechnicalReport, SentimentData, run_debate, DebateDecision
    )

    # ── Katman 1: Temel SMC Analizi ───────────────────────────
    try:
        df = ohlcv(symbol, "4h", 400)
        if df.empty or len(df) < 100:
            logger.debug(f"{symbol}: Veri yetersiz")
            return None

        base = analyze(symbol, is_bist=False)
        if not base:
            return None

    except Exception as e:
        logger.warning(f"SMC analiz hatası ({symbol}): {e}")
        return None

    score_smc = base.get("composite", 0)
    trend     = base.get("trend", "NEUTRAL")

    if trend == "NEUTRAL":
        return None

    # ── Katman 2: Gelişmiş İndikatörler ──────────────────────
    try:
        bull_obs  = base.get("bull_obs", [])
        bear_obs  = base.get("bear_obs", [])
        bull_fvg  = base.get("bull_fvg", [])
        bear_fvg  = base.get("bear_fvg", [])

        # OI + Funding Rate verisi
        oi_list, px_list, funding = fetch_oi_and_funding(symbol, limit=8)

        adv = advanced_composite_score(
            df          = df,
            bull_obs    = bull_obs,
            bear_obs    = bear_obs,
            bull_fvg    = bull_fvg,
            bear_fvg    = bear_fvg,
            oi_series   = oi_list,
            px_series   = px_list,
            funding_rate= funding,
            direction   = trend,
        )
        score_adv = adv["advanced_score"]

    except Exception as e:
        logger.debug(f"Gelişmiş analiz hatası ({symbol}): {e}")
        adv       = {}
        score_adv = 0.0
        funding   = None

    # ── Katman 3: Ajan Münazarası ─────────────────────────────
    agent_boost = 0.0
    debate_result = None

    if use_debate:
        try:
            # Teknik rapor oluştur
            tech_report = TechnicalReport(
                symbol          = symbol,
                composite_score = score_smc,
                trend           = trend,
                entry_price     = base.get("entry", 0),
                sl_price        = base.get("sl", 0),
                tp1_price       = base.get("entry", 0) * 1.06 if trend == "BULLISH" else base.get("entry", 0) * 0.94,
                tp2_price       = base.get("entry", 0) * 1.14 if trend == "BULLISH" else base.get("entry", 0) * 0.86,
                tp3_price       = base.get("entry", 0) * 1.28 if trend == "BULLISH" else base.get("entry", 0) * 0.72,
                bos_bull        = base.get("bos_bull", False),
                choch_bull      = base.get("choch_bull", False),
                bos_bear        = base.get("bos_bear", False),
                choch_bear      = base.get("choch_bear", False),
                spring          = adv.get("wyckoff", {}).get("spring_detected", False),
                utad            = adv.get("wyckoff", {}).get("utad_detected", False),
                ib_breakout     = adv.get("ib", {}).get("ib_breakout", "NONE"),
                adr_signal      = adv.get("adr", {}).get("adr_signal", "NEUTRAL"),
                adr_pct_used    = adv.get("adr", {}).get("adr_pct_used", 0),
                poc_confluence  = adv.get("poc", {}).get("confluence_type", "NEUTRAL"),
                oi_trend        = adv.get("oi", {}).get("oi_trend", "UNKNOWN"),
                fr_signal       = adv.get("fr", {}).get("fr_signal", "NEUTRAL"),
                vwap_position   = adv.get("vwap", {}).get("band_position", "UNKNOWN"),
                wyckoff_phase   = adv.get("wyckoff", {}).get("wyckoff_phase", "NEUTRAL"),
                session         = adv.get("session", {}).get("current_session", "UNKNOWN"),
                advanced_score  = score_adv,
            )

            # Duygu verisi
            if social_data:
                sent_data = SentimentData(
                    symbol        = symbol,
                    score         = social_data.get("score", 0.5),
                    label         = social_data.get("label", "NÖTR"),
                    mention_count = social_data.get("mention_count", 0),
                    headlines     = social_data.get("headlines", []),
                )
            else:
                sent_data = SentimentData(symbol=symbol)

            debate_result = run_debate(
                tech        = tech_report,
                sent        = sent_data,
                max_rounds  = debate_rounds,
                use_llm     = True,
            )

            # Münazara kararı skoru etkiler
            action = debate_result.action
            if action == "STRONG_BUY" and trend == "BULLISH":
                agent_boost = 1.5
            elif action == "BUY" and trend == "BULLISH":
                agent_boost = 0.5
            elif action in ("HOLD",):
                agent_boost = 0.0
            elif action == "SELL" and trend == "BULLISH":
                agent_boost = -1.5   # Ajan tersini söylüyor → güven azalt
            elif action == "STRONG_SELL" and trend == "BULLISH":
                agent_boost = -3.0

            # BEARISH için ters
            if trend == "BEARISH":
                if action in ("SELL", "STRONG_SELL"):
                    agent_boost = abs(agent_boost) if agent_boost <= 0 else agent_boost
                elif action in ("BUY", "STRONG_BUY"):
                    agent_boost = -abs(agent_boost)

        except Exception as e:
            logger.debug(f"Ajan münazarası hatası ({symbol}): {e}")
            debate_result = None

    # ── Nihai Skor Hesabı ─────────────────────────────────────
    # Ağırlıklı kombinasyon:
    #   SMC: %60 (temel motor, en güvenilir)
    #   Gelişmiş: %25 (destekleyici göstergeler)
    #   Ajan Boost: ±1.5 (bonus/ceza)
    final_score = (
        score_smc * 0.60 +
        score_adv * 0.25 +
        (score_smc + score_adv) / 2 * 0.15  # cross-validation
    ) + agent_boost

    final_score = round(min(10.0, max(0.0, final_score)), 2)

    # ── Sonuç dict ────────────────────────────────────────────
    result = {
        **base,
        # Güncellenmiş skor
        "composite":     final_score,
        "composite_smc": score_smc,
        "composite_adv": score_adv,
        "agent_boost":   round(agent_boost, 2),

        # Gelişmiş göstergeler
        "ib":            adv.get("ib", {}),
        "adr":           adv.get("adr", {}),
        "poc":           adv.get("poc", {}),
        "oi":            adv.get("oi", {}),
        "fr":            adv.get("fr", {}),
        "session_adv":   adv.get("session", {}),
        "vwap_bands":    adv.get("vwap", {}),
        "wyckoff_adv":   adv.get("wyckoff", {}),

        # Münazara
        "debate":        debate_result,
        "funding_rate":  funding,
    }

    return result


# ══════════════════════════════════════════════════════════════════════
#  GENİŞLETİLMİŞ ÇIKTI
# ══════════════════════════════════════════════════════════════════════

def print_full_signal(result: dict):
    """Gelişmiş sinyal çıktısı."""
    try:
        from live_scan import ok, bad, warn, nfo, dim, B, R, CY, GR, YL, DM
    except ImportError:
        B=R=CY=GR=YL=DM=""
        def ok(s): return s
        def bad(s): return s
        def warn(s): return s
        def nfo(s): return s
        def dim(s): return s

    sym   = result.get("symbol", "?")
    score = result.get("composite", 0)
    trend = result.get("trend", "NEUTRAL")
    smc_s = result.get("composite_smc", 0)
    adv_s = result.get("composite_adv", 0)
    ab    = result.get("agent_boost", 0)

    score_c = ok if score >= 7 else (warn if score >= 5.5 else dim)
    trend_c = ok if trend == "BULLISH" else bad

    # Gelişmiş indikatörler
    ib   = result.get("ib",  {})
    adr  = result.get("adr", {})
    poc  = result.get("poc", {})
    oi   = result.get("oi",  {})
    fr   = result.get("fr",  {})
    sess = result.get("session_adv", {})
    vwap = result.get("vwap_bands", {})
    wyck = result.get("wyckoff_adv", {})

    def _mini_bar(v, mx=10, w=8, col=GR):
        f = max(0, min(w, int(v / mx * w)))
        return f"{col}{'█'*f}{DM}{'░'*(w-f)}{R}"

    print(f"\n  ╔{'═'*62}╗")
    print(f"  ║  {B}{sym:12}{R}  {score_c(f'{score:.1f}/10')}  {trend_c(trend):8}  "
          f"{_mini_bar(score)}")
    print(f"  ║  SMC: {nfo(f'{smc_s:.1f}')}  Adv: {nfo(f'{adv_s:.1f}')}  "
          f"Ajan: {(ok if ab > 0 else (bad if ab < 0 else dim))(f'{ab:+.1f}')}")
    print(f"  ╠{'═'*62}╣")

    # IB + ADR
    ib_bk  = ib.get("ib_breakout", "?")
    adr_sg = adr.get("adr_signal", "?")
    adr_pu = adr.get("adr_pct_used", 0)
    ib_c   = ok if ib_bk == "BULL" else (bad if ib_bk == "BEAR" else dim)
    adr_c  = ok if adr_sg == "ROOM" else (warn if adr_sg == "NEUTRAL" else bad)
    print(f"  ║  IB Kırılma: {ib_c(ib_bk):10}  ADR: {adr_c(adr_sg)} "
          f"({adr_pu:.0f}% kullanıldı)")

    # POC + OI
    poc_t  = poc.get("confluence_type", "?")
    oi_t   = oi.get("oi_trend", "?")
    poc_c  = ok if "BULL" in poc_t else (bad if "BEAR" in poc_t else dim)
    oi_c   = ok if "BULL" in oi_t  else (bad if "BEAR" in oi_t  else dim)
    print(f"  ║  POC Confluencei: {poc_c(poc_t):16}  OI: {oi_c(oi_t)}")

    # Funding + VWAP
    fr_sg  = fr.get("fr_signal", "?")
    fr_val = fr.get("fr_pct", 0)
    vwap_p = vwap.get("band_position", "?")
    fr_c   = ok if fr.get("fr_score", 0) > 0 else (bad if fr.get("fr_score", 0) < 0 else dim)
    vwap_c = ok if "LOW" in vwap_p else (bad if "HIGH" in vwap_p else dim)
    print(f"  ║  Funding: {fr_c(f'{fr_val:+.4f}%')} {dim(fr_sg[:20])}")
    print(f"  ║  VWAP: {vwap_c(vwap_p):16}  Wyckoff: {nfo(wyck.get('wyckoff_phase','?')[:18])}")

    # Session
    sess_s = sess.get("current_session", "?")
    sess_kz = sess.get("in_kill_zone", False)
    print(f"  ║  Seans: {nfo(sess_s)}  {'🎯 Kill Zone' if sess_kz else ''}")

    # Münazara kararı
    debate = result.get("debate")
    if debate:
        from agents.debate import print_debate_result
        print(f"  ╠{'═'*62}╣")
        print(f"  ║  {B}AJAN KARARI:{R}  "
              f"{(ok if 'BUY' in debate.action else bad)(debate.action):12}  "
              f"Güven: {debate.confidence:.0%}  "
              f"{'[LLM]' if debate.used_llm else '[Kural]'}")
        if debate.rationale:
            words = debate.rationale[:100]
            print(f"  ║  {dim(words)}")

    print(f"  ╚{'═'*62}╝\n")
