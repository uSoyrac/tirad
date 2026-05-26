"""
agents/debate.py — Çoklu Ajan Münazara Protokolü
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TradingAgents mimarisini yerel Ollama ile ücretsiz çalıştırır.

Ajan Yapısı:
  1. TechnicalAnalystAgent  — SMC+ICT teknik raporunu üretir
  2. SentimentAnalystAgent   — Sosyal/haber duygu skorunu değerlendirir
  3. BullResearcherAgent     — LONG tezini savunur (en güçlü argümanlar)
  4. BearResearcherAgent     — SHORT/bekle tezini savunur
  5. PortfolioManagerAgent   — Münazarayı dinler, final kararı verir

Fallback:
  Ollama mevcut değilse kural tabanlı ağırlıklı oylama kullanılır.
  Sistem her koşulda çalışır — LLM opsiyonel katmandır.

Kullanım:
  from agents.debate import run_debate
  decision = run_debate(technical_report, sentiment_data, symbol="ETH/USDT")
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from agents import ollama_client as llm

logger = logging.getLogger("agents.debate")

# ══════════════════════════════════════════════════════════════════════
#  VERİ YAPILARI
# ══════════════════════════════════════════════════════════════════════

@dataclass
class TechnicalReport:
    """SMC analiz motorundan gelen teknik rapor."""
    symbol:          str
    composite_score: float        # 0-10
    trend:           str          # BULLISH / BEARISH / NEUTRAL
    entry_price:     float = 0.0
    sl_price:        float = 0.0
    tp1_price:       float = 0.0
    tp2_price:       float = 0.0
    tp3_price:       float = 0.0
    bos_bull:        bool = False
    choch_bull:      bool = False
    bos_bear:        bool = False
    choch_bear:      bool = False
    spring:          bool = False
    utad:            bool = False
    ib_breakout:     str  = "NONE"
    adr_signal:      str  = "NEUTRAL"
    adr_pct_used:    float = 0.0
    poc_confluence:  str  = "NEUTRAL"
    oi_trend:        str  = "UNKNOWN"
    fr_signal:       str  = "NEUTRAL"
    vwap_position:   str  = "UNKNOWN"
    wyckoff_phase:   str  = "NEUTRAL"
    session:         str  = "UNKNOWN"
    advanced_score:  float = 0.0
    notes:           str  = ""


@dataclass
class SentimentData:
    """Sosyal/haber duygu verisi."""
    symbol:        str
    score:         float = 0.5      # 0-1 (0.5 = nötr)
    label:         str   = "NÖTR"   # BOĞA / NÖTR / AYI
    mention_count: int   = 0
    headlines:     list  = field(default_factory=list)
    sources:       dict  = field(default_factory=dict)


@dataclass
class DebateDecision:
    """Münazara sonucu."""
    symbol:          str
    action:          str           # STRONG_BUY / BUY / HOLD / SELL / STRONG_SELL
    direction:       str           # LONG / SHORT / NEUTRAL
    confidence:      float         # 0.0 - 1.0
    final_score:     float         # 0-10
    bull_score:      float = 0.0
    bear_score:      float = 0.0
    rationale:       str   = ""
    bull_argument:   str   = ""
    bear_argument:   str   = ""
    used_llm:        bool  = False
    debate_rounds:   int   = 0
    timestamp:       str   = ""


# ══════════════════════════════════════════════════════════════════════
#  SİSTEM PROMPTLARI
# ══════════════════════════════════════════════════════════════════════

_SYSTEM_BULL = """Sen bir kripto vadeli işlem piyasasında uzman LONG araştırmacısısın.
Görevin: Verilen teknik ve duygu verilerinden yola çıkarak en güçlü LONG tezini savunmak.
- Her zaman bullish argümanları ön plana çıkar
- Risk/ödül oranı ve teknik seviyeleri kullan
- Kısa, net ve güçlü argümanlar üret (max 150 kelime)
- Rakamları kullan: entry, TP seviyeleri, RR oranı"""

_SYSTEM_BEAR = """Sen bir kripto vadeli işlem piyasasında uzman SHORT/bekle araştırmacısısın.
Görevin: Verilen teknik ve duygu verilerinden yola çıkarak en güçlü BEAR/bekle tezini savunmak.
- Riskleri, tuzakları ve olumsuz sinyalleri ön plana çıkar
- Neden beklemek veya short açmak mantıklı olduğunu anlat
- Kısa, net ve güçlü argümanlar üret (max 150 kelime)
- Somut teknik seviyeleri kullan"""

_SYSTEM_PM = """Sen bir kripto hedge fund portföy müdürüsün.
Görevin: Boğa ve ayı araştırmacıların argümanlarını değerlendirip net bir karar vermek.
%2 risk yönetimi, maksimum 5x kaldıraç ve SMC teknikleri kullanıyorsun.
Kararını şu JSON formatında döndür:
{
  "action": "STRONG_BUY/BUY/HOLD/SELL/STRONG_SELL",
  "direction": "LONG/SHORT/NEUTRAL",
  "confidence": 0.0-1.0,
  "rationale": "kısa gerekçe (max 80 kelime)"
}"""


# ══════════════════════════════════════════════════════════════════════
#  KURAL TABANLI FALLBACK
# ══════════════════════════════════════════════════════════════════════

def _rule_based_decision(
    tech: TechnicalReport,
    sent: SentimentData,
) -> DebateDecision:
    """
    Ollama olmadan kural tabanlı münazara simülasyonu.
    Ağırlıklı oylama sistemi.
    """
    bull_score = 0.0
    bear_score = 0.0
    bull_args  = []
    bear_args  = []

    # ── Teknik sinyal ──────────────────────────────────────────
    comp = tech.composite_score
    if comp >= 7.0:
        bull_score += 3.0; bull_args.append(f"Güçlü teknik skor: {comp:.1f}/10")
    elif comp >= 5.5:
        bull_score += 1.5; bull_args.append(f"Orta teknik skor: {comp:.1f}/10")
    elif comp <= 3.0:
        bear_score += 2.0; bear_args.append(f"Zayıf teknik skor: {comp:.1f}/10")

    # ── Trend ─────────────────────────────────────────────────
    if tech.trend == "BULLISH":
        bull_score += 2.5; bull_args.append("SMC trend BULLISH (BOS/CHoCH teyidi)")
    elif tech.trend == "BEARISH":
        bear_score += 2.5; bear_args.append("SMC trend BEARISH")

    # ── Yapısal sinyaller ──────────────────────────────────────
    if tech.bos_bull:
        bull_score += 1.5; bull_args.append("BOS Bullish kırılma onaylandı")
    if tech.choch_bull:
        bull_score += 1.0; bull_args.append("CHoCH Bullish dönüşüm")
    if tech.spring:
        bull_score += 2.0; bull_args.append("Wyckoff Spring tespit edildi — güçlü reversal")
    if tech.utad:
        bear_score += 2.0; bear_args.append("Wyckoff UTAD — dağıtım tuzağı")

    # ── IB Kırılma ─────────────────────────────────────────────
    if tech.ib_breakout == "BULL":
        bull_score += 1.0; bull_args.append("IB High kırıldı — boğa genişlemesi")
    elif tech.ib_breakout == "BEAR":
        bear_score += 1.0; bear_args.append("IB Low kırıldı — ayı genişlemesi")

    # ── ADR Tükenme ────────────────────────────────────────────
    if tech.adr_signal == "EXHAUSTED":
        bear_score += 1.5; bear_args.append(f"ADR %{tech.adr_pct_used:.0f} kullanıldı — tükenme riski")
    elif tech.adr_signal == "ROOM":
        bull_score += 1.0; bull_args.append("ADR alanı var — momentum devam edebilir")
    elif tech.adr_signal == "OVEREXTENDED":
        bear_score += 2.5; bear_args.append(f"ADR aşıldı (%{tech.adr_pct_used:.0f}) — reversal riski yüksek")

    # ── POC Confluence ─────────────────────────────────────────
    if "STRONG_BULL" in tech.poc_confluence:
        bull_score += 2.5; bull_args.append("POC + OB/FVG güçlü boğa çakışması")
    elif "BULL" in tech.poc_confluence:
        bull_score += 1.5; bull_args.append("POC boğa confluencei")
    elif "STRONG_BEAR" in tech.poc_confluence:
        bear_score += 2.5; bear_args.append("POC + OB/FVG güçlü ayı çakışması")
    elif "BEAR" in tech.poc_confluence:
        bear_score += 1.5; bear_args.append("POC ayı confluencei")

    # ── Open Interest ──────────────────────────────────────────
    if "BULL_STRONG" in tech.oi_trend:
        bull_score += 2.0; bull_args.append("OI ↑ + Fiyat ↑ — kurumsal long girişi")
    elif "BEAR_STRONG" in tech.oi_trend:
        bear_score += 2.0; bear_args.append("OI ↑ + Fiyat ↓ — kurumsal short girişi")

    # ── Funding Rate ───────────────────────────────────────────
    if "EXTREME_NEGATIVE" in tech.fr_signal:
        bull_score += 2.0; bull_args.append("Aşırı negatif funding → short squeeze potansiyeli")
    elif "EXTREME_POSITIVE" in tech.fr_signal:
        bear_score += 2.0; bear_args.append("Aşırı pozitif funding → long liquidation riski")
    elif "NEGATIVE" in tech.fr_signal:
        bull_score += 0.5
    elif "POSITIVE" in tech.fr_signal:
        bear_score += 0.5

    # ── VWAP Konumu ────────────────────────────────────────────
    if tech.vwap_position == "EXTREME_LOW":
        bull_score += 1.5; bull_args.append("Fiyat VWAP −2σ altında — aşırı satım")
    elif tech.vwap_position == "EXTREME_HIGH":
        bear_score += 1.5; bear_args.append("Fiyat VWAP +2σ üstünde — aşırı alım")
    elif "ABOVE" in tech.vwap_position:
        bull_score += 0.5

    # ── Wyckoff ────────────────────────────────────────────────
    if tech.wyckoff_phase in ("ACCUMULATION_PHASE", "SPRING", "LPS_ZONE"):
        bull_score += 1.5; bull_args.append(f"Wyckoff: {tech.wyckoff_phase}")
    elif tech.wyckoff_phase in ("DISTRIBUTION_PHASE", "UTAD", "LPSY_ZONE"):
        bear_score += 1.5; bear_args.append(f"Wyckoff: {tech.wyckoff_phase}")

    # ── Duygu ──────────────────────────────────────────────────
    if sent.label == "BOĞA" and sent.score > 0.65:
        bull_score += 1.0; bull_args.append(f"Sosyal duygu BOĞA (%{sent.score*100:.0f})")
    elif sent.label == "AYI" and sent.score < 0.35:
        bear_score += 1.0; bear_args.append(f"Sosyal duygu AYI (%{(1-sent.score)*100:.0f})")
    elif sent.score > 0.70:
        # Aşırı iyimserlik = kontrarian bear
        bear_score += 0.5; bear_args.append("Aşırı iyimser duygu → kontrarian risk")

    # ── Advanced score ─────────────────────────────────────────
    if tech.advanced_score >= 6.0:
        bull_score += 1.5; bull_args.append(f"Gelişmiş skor güçlü: {tech.advanced_score:.1f}/10")
    elif tech.advanced_score <= 3.0:
        bear_score += 1.0; bear_args.append(f"Gelişmiş skor zayıf: {tech.advanced_score:.1f}/10")

    # ── Final karar ────────────────────────────────────────────
    net = bull_score - bear_score
    total = bull_score + bear_score
    confidence = min(1.0, abs(net) / max(total, 1.0))

    if net >= 5.0:
        action = "STRONG_BUY";  direction = "LONG"
    elif net >= 2.5:
        action = "BUY";         direction = "LONG"
    elif net <= -5.0:
        action = "STRONG_SELL"; direction = "SHORT"
    elif net <= -2.5:
        action = "SELL";        direction = "SHORT"
    else:
        action = "HOLD";        direction = "NEUTRAL"

    final_score = min(10.0, max(0.0, (net + 10) / 2))

    rationale_parts = []
    if bull_args:
        rationale_parts.append("BOĞA: " + "; ".join(bull_args[:3]))
    if bear_args:
        rationale_parts.append("AYI: " + "; ".join(bear_args[:3]))

    return DebateDecision(
        symbol        = tech.symbol,
        action        = action,
        direction     = direction,
        confidence    = round(confidence, 2),
        final_score   = round(final_score, 2),
        bull_score    = round(bull_score, 2),
        bear_score    = round(bear_score, 2),
        rationale     = " | ".join(rationale_parts),
        bull_argument = "; ".join(bull_args[:4]),
        bear_argument = "; ".join(bear_args[:4]),
        used_llm      = False,
        debate_rounds = 0,
        timestamp     = __import__("datetime").datetime.utcnow().isoformat(),
    )


# ══════════════════════════════════════════════════════════════════════
#  LLM TABANLI MÜNAZARA
# ══════════════════════════════════════════════════════════════════════

def _format_tech_report(tech: TechnicalReport) -> str:
    """Teknik raporu LLM'e gönderilecek metin formatına çevirir."""
    return f"""
SEMBOL: {tech.symbol}
Bileşik SMC Skoru: {tech.composite_score:.1f}/10
Gelişmiş Skor: {tech.advanced_score:.1f}/10
Trend: {tech.trend}
Giriş: ${tech.entry_price:.4f}  SL: ${tech.sl_price:.4f}
TP1: ${tech.tp1_price:.4f}  TP2: ${tech.tp2_price:.4f}  TP3: ${tech.tp3_price:.4f}

Yapısal Sinyaller:
  BOS Bullish: {tech.bos_bull}  CHoCH Bullish: {tech.choch_bull}
  BOS Bearish: {tech.bos_bear}  CHoCH Bearish: {tech.choch_bear}
  Wyckoff Spring: {tech.spring}  UTAD: {tech.utad}
  Wyckoff Faz: {tech.wyckoff_phase}

Gelişmiş İndikatörler:
  IB Kırılma: {tech.ib_breakout}
  ADR Durumu: {tech.adr_signal} (%{tech.adr_pct_used:.0f} kullanıldı)
  POC Confluence: {tech.poc_confluence}
  Open Interest Trend: {tech.oi_trend}
  Funding Rate: {tech.fr_signal}
  VWAP Konumu: {tech.vwap_position}
  Aktif Seans: {tech.session}
""".strip()


def _llm_debate(
    tech:   TechnicalReport,
    sent:   SentimentData,
    rounds: int = 2,
) -> DebateDecision:
    """
    Ollama ile gerçek LLM münazarası.
    rounds: kaç tur tartışma yapılacak (1-3 önerilir)
    """
    model_deep  = llm.best_available_model(prefer_reasoning=True)
    model_quick = llm.best_available_model(prefer_reasoning=False)

    if not model_deep and not model_quick:
        logger.info("Ollama model bulunamadı — kural tabanlı sisteme geçiliyor")
        return _rule_based_decision(tech, sent)

    tech_text = _format_tech_report(tech)
    sent_text = f"Sosyal Duygu: {sent.label} ({sent.score:.2f}/1.0) | Bahsedilme: {sent.mention_count}"

    context = f"{tech_text}\n\n{sent_text}"

    bull_arg = ""
    bear_arg = ""

    # ── Tur 1: İlk argümanlar ─────────────────────────────────
    logger.info(f"[Münazara] Tur 1 başlıyor — model: {model_deep or model_quick}")

    bull_prompt = f"Aşağıdaki piyasa verilerine dayanarak {tech.symbol} için güçlü LONG tezi sun:\n\n{context}"
    bear_prompt = f"Aşağıdaki piyasa verilerine dayanarak {tech.symbol} için güçlü BEAR/BEKLE tezi sun:\n\n{context}"

    bull_arg = llm.query(bull_prompt, _SYSTEM_BULL, model_quick, temperature=0.4) or ""
    bear_arg = llm.query(bear_prompt, _SYSTEM_BEAR, model_quick, temperature=0.4) or ""

    # ── Tur 2+: Karşılıklı itiraz ─────────────────────────────
    for r in range(1, rounds):
        logger.info(f"[Münazara] Tur {r+1} — itiraz turu")
        if bull_arg and bear_arg:
            bull_counter = llm.query(
                f"Rakip ayı tezi:\n{bear_arg}\n\nBu itirazı çür ve LONG tezini güçlendir:\n{context}",
                _SYSTEM_BULL, model_quick, temperature=0.4
            ) or bull_arg

            bear_counter = llm.query(
                f"Rakip boğa tezi:\n{bull_arg}\n\nBu itirazı çür ve BEAR tezini güçlendir:\n{context}",
                _SYSTEM_BEAR, model_quick, temperature=0.4
            ) or bear_arg

            bull_arg = bull_counter
            bear_arg = bear_counter

    # ── Portföy Müdürü Kararı ─────────────────────────────────
    logger.info("[Münazara] Portföy müdürü kararı alınıyor...")

    pm_prompt = f"""
Piyasa Verisi:
{context}

BOĞA Araştırmacısı Argümanı:
{bull_arg[:400] if bull_arg else 'Argüman üretilemedi'}

AYI Araştırmacısı Argümanı:
{bear_arg[:400] if bear_arg else 'Argüman üretilemedi'}

Yukarıdaki münazarayı değerlendirerek net bir yatırım kararı ver.
"""

    pm_response = llm.query_json(
        pm_prompt,
        _SYSTEM_PM,
        model_deep,
        default={
            "action":     "HOLD",
            "direction":  "NEUTRAL",
            "confidence": 0.5,
            "rationale":  "LLM yanıtı parse edilemedi",
        }
    )

    action    = pm_response.get("action", "HOLD").upper()
    direction = pm_response.get("direction", "NEUTRAL").upper()
    conf      = float(pm_response.get("confidence", 0.5))
    rationale = pm_response.get("rationale", "")

    # Skora çevir
    action_scores = {
        "STRONG_BUY": 9.0, "BUY": 7.0, "HOLD": 5.0,
        "SELL": 3.0, "STRONG_SELL": 1.0,
    }
    final_score = action_scores.get(action, 5.0)

    # Kural tabanlı skorları da ekle (hibrit)
    rule_dec = _rule_based_decision(tech, sent)
    hybrid_score = (final_score + rule_dec.final_score) / 2

    return DebateDecision(
        symbol        = tech.symbol,
        action        = action,
        direction     = direction,
        confidence    = round(conf, 2),
        final_score   = round(hybrid_score, 2),
        bull_score    = rule_dec.bull_score,
        bear_score    = rule_dec.bear_score,
        rationale     = rationale,
        bull_argument = bull_arg[:300] if bull_arg else "",
        bear_argument = bear_arg[:300] if bear_arg else "",
        used_llm      = True,
        debate_rounds = rounds,
        timestamp     = __import__("datetime").datetime.utcnow().isoformat(),
    )


# ══════════════════════════════════════════════════════════════════════
#  ANA GİRİŞ NOKTASI
# ══════════════════════════════════════════════════════════════════════

def run_debate(
    tech:         TechnicalReport,
    sent:         SentimentData,
    max_rounds:   int  = 2,
    use_llm:      bool = True,
    force_rules:  bool = False,
) -> DebateDecision:
    """
    Münazarayı çalıştır ve karar döndür.

    Args:
        tech:        TechnicalReport — SMC analiz çıktısı
        sent:        SentimentData  — Sosyal duygu verisi
        max_rounds:  Münazara tur sayısı (1-3, daha fazla = daha uzun)
        use_llm:     True → Ollama dene, False → direkt kural tabanlı
        force_rules: True → Ollama mevcut olsa da kural tabanlı kullan

    Döner:
        DebateDecision — action, direction, confidence, rationale
    """
    t0 = time.time()

    if force_rules or not use_llm:
        dec = _rule_based_decision(tech, sent)
        logger.info(
            f"[Münazara] Kural tabanlı  {tech.symbol}: {dec.action}  "
            f"bull={dec.bull_score:.1f}  bear={dec.bear_score:.1f}  "
            f"conf={dec.confidence:.2f}  ({time.time()-t0:.1f}s)"
        )
        return dec

    # Ollama mevcut mu?
    if llm.is_available():
        logger.info(f"[Münazara] Ollama aktif — {max_rounds} tur LLM münazarası başlıyor")
        dec = _llm_debate(tech, sent, max_rounds)
        logger.info(
            f"[Münazara] LLM kararı  {tech.symbol}: {dec.action}  "
            f"conf={dec.confidence:.2f}  ({time.time()-t0:.1f}s)"
        )
    else:
        logger.info("[Münazara] Ollama bulunamadı — kural tabanlı sisteme geçildi")
        dec = _rule_based_decision(tech, sent)
        logger.info(
            f"[Münazara] Kural tabanlı  {tech.symbol}: {dec.action}  "
            f"({time.time()-t0:.1f}s)"
        )

    return dec


# ══════════════════════════════════════════════════════════════════════
#  ÇIKTI YARDIMCISI
# ══════════════════════════════════════════════════════════════════════

def print_debate_result(dec: DebateDecision):
    """Terminal çıktısı."""
    try:
        from live_scan import ok, bad, warn, nfo, dim, B, R, CY, GR, YL
    except ImportError:
        B=R=CY=GR=YL=""
        def ok(s): return s
        def bad(s): return s
        def warn(s): return s
        def nfo(s): return s
        def dim(s): return s

    action_colors = {
        "STRONG_BUY":  ok,
        "BUY":         ok,
        "HOLD":        warn,
        "SELL":        bad,
        "STRONG_SELL": bad,
    }
    col = action_colors.get(dec.action, warn)

    conf_bar = "█" * int(dec.confidence * 10) + "░" * (10 - int(dec.confidence * 10))
    llm_tag  = dim("[LLM]") if dec.used_llm else dim("[Kural]")

    print(f"\n  ┌{'─'*56}┐")
    print(f"  │  {B}MÜNAZARA KARARI{R}  {dec.symbol:12}  {llm_tag}")
    print(f"  │  {col(dec.action):20}  Yön: {col(dec.direction)}")
    print(f"  │  Güven: {GR}{conf_bar}{R}  {dec.confidence:.0%}")
    if dec.used_llm:
        print(f"  │  Tur sayısı: {dec.debate_rounds}")
    else:
        bsc = f"{CY}{dec.bull_score:.1f}{R}"
        brc = f"{CY}{dec.bear_score:.1f}{R}"
        print(f"  │  Boğa: {bsc}  Ayı: {brc}  Net: {col(f'{dec.final_score:.1f}')}/10")
    print(f"  │")
    if dec.rationale:
        # Satır kır
        words = dec.rationale.split()
        line = "  │  "
        for w in words[:30]:
            if len(line) + len(w) > 58:
                print(line)
                line = "  │    " + w + " "
            else:
                line += w + " "
        if line.strip():
            print(line)
    print(f"  └{'─'*56}┘\n")
