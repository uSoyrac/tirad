"""
Email bildirimi — Gmail SMTP ile.
App Password ile gönderim: Google Hesabı > Güvenlik > 2FA > App Passwords
"""
import logging
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from analysis.composite_scorer import CompositeScore
from signals.trade_setup import TradeSetup
from signals.position_sizer import PositionSize

logger = logging.getLogger(__name__)

SIGNAL_EMOJI = {
    "STRONG": "🚨",
    "MEDIUM": "📊",
    "WATCHLIST": "👁️",
    "NO_SIGNAL": "📉",
}

DIRECTION_EMOJI = {
    "BULLISH": "📈 LONG",
    "BEARISH": "📉 SHORT",
    "NEUTRAL": "➖ NÖTR",
    "LONG": "📈 LONG",
    "SHORT": "📉 SHORT",
}


def _build_html(
    score: CompositeScore,
    setup: TradeSetup | None,
    pos: PositionSize | None,
    claude_text: str,
) -> str:
    symbol_clean = score.symbol.replace("/", "-")
    direction = DIRECTION_EMOJI.get(score.direction, score.direction)
    emoji = SIGNAL_EMOJI.get(score.signal_level, "📊")
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # Renk
    color_map = {"STRONG": "#e74c3c", "MEDIUM": "#f39c12", "WATCHLIST": "#3498db"}
    color = color_map.get(score.signal_level, "#7f8c8d")

    html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #0a0a0a; color: #e0e0e0; margin: 0; padding: 20px; }}
  .container {{ max-width: 680px; margin: 0 auto; background: #141414; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.5); }}
  .header {{ background: {color}; padding: 20px 28px; }}
  .header h1 {{ margin: 0; font-size: 22px; color: #fff; }}
  .header p {{ margin: 6px 0 0; color: rgba(255,255,255,0.85); font-size: 14px; }}
  .body {{ padding: 24px 28px; }}
  .score-badge {{ background: {color}; color: #fff; font-size: 28px; font-weight: 900;
                  padding: 10px 20px; border-radius: 8px; display: inline-block; margin-bottom: 20px; }}
  .section {{ margin: 20px 0; }}
  .section h2 {{ font-size: 14px; text-transform: uppercase; letter-spacing: 1.5px; color: #888; margin: 0 0 10px; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
  .item {{ background: #1e1e1e; border-radius: 8px; padding: 12px; }}
  .item .label {{ font-size: 11px; color: #666; text-transform: uppercase; }}
  .item .value {{ font-size: 18px; font-weight: 700; margin-top: 4px; }}
  .item .value.up {{ color: #2ecc71; }}
  .item .value.down {{ color: #e74c3c; }}
  .detail-list {{ list-style: none; padding: 0; margin: 0; }}
  .detail-list li {{ padding: 6px 10px; background: #1a1a1a; margin-bottom: 4px; border-radius: 6px; font-size: 13px; }}
  .claude-box {{ background: #1a1f2e; border-left: 4px solid {color}; padding: 16px; border-radius: 0 8px 8px 0; font-size: 14px; line-height: 1.6; white-space: pre-wrap; }}
  .footer {{ background: #0d0d0d; padding: 14px 28px; text-align: center; font-size: 11px; color: #555; }}
  .scores-bar {{ display: flex; gap: 8px; flex-wrap: wrap; margin: 12px 0; }}
  .score-chip {{ background: #1e1e1e; padding: 6px 12px; border-radius: 20px; font-size: 12px; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>{emoji} {score.symbol} — {score.signal_level}</h1>
    <p>{direction} &nbsp;|&nbsp; {now}</p>
  </div>
  <div class="body">

    <div class="score-badge">{score.composite:.1f} / 10</div>
    <div class="scores-bar">
      <span class="score-chip">SMC: {score.smc_score:.1f}/10</span>
      <span class="score-chip">Klasik: {score.classic_score:.1f}/10</span>
      <span class="score-chip">Kurumsal: {score.institutional_score:.1f}/7</span>
      <span class="score-chip">MTF: {score.mtf_score:.1f}/4</span>
      <span class="score-chip">Sosyal: {score.social_score:.1f}/6</span>
    </div>
"""

    # Trade Setup
    if setup and setup.valid:
        price_color = "up" if setup.direction in ("LONG", "BULLISH") else "down"
        html += f"""
    <div class="section">
      <h2>⚡ Trade Setup</h2>
      <div class="grid">
        <div class="item">
          <div class="label">Giriş Bölgesi</div>
          <div class="value {price_color}">{setup.entry_low:.4f} — {setup.entry_high:.4f}</div>
        </div>
        <div class="item">
          <div class="label">Stop Loss</div>
          <div class="value down">{setup.stop_loss:.4f} <small>(-%{setup.sl_pct*100:.1f})</small></div>
        </div>
        <div class="item">
          <div class="label">TP1 → %40 kapat</div>
          <div class="value up">{setup.tp1:.4f} <small>(+%{setup.tp1_pct*100:.1f})</small></div>
        </div>
        <div class="item">
          <div class="label">TP2 → %35 kapat</div>
          <div class="value up">{setup.tp2:.4f} <small>(+%{setup.tp2_pct*100:.1f})</small></div>
        </div>
        <div class="item">
          <div class="label">TP3 → %25 kapat</div>
          <div class="value up">{setup.tp3:.4f} <small>(+%{setup.tp3_pct*100:.1f})</small></div>
        </div>
"""
        if pos:
            html += f"""
        <div class="item">
          <div class="label">Kaldıraç / Pozisyon</div>
          <div class="value">{pos.leverage}x &nbsp; ${pos.position_size:,.0f}</div>
        </div>
"""
        html += "      </div>\n    </div>\n"

    # SMC Detaylar
    if score.smc_details:
        html += '<div class="section"><h2>📐 SMC Analizi</h2><ul class="detail-list">'
        for v in score.smc_details.values():
            html += f"<li>{v}</li>"
        html += "</ul></div>"

    # Klasik İndikatörler
    if score.classic_details:
        html += '<div class="section"><h2>📊 Klasik İndikatörler</h2><ul class="detail-list">'
        for v in score.classic_details.values():
            html += f"<li>{v}</li>"
        html += "</ul></div>"

    # Kurumsal / Sosyal
    all_extra = {**score.institutional_details, **score.mtf_details, **score.social_details}
    if all_extra:
        html += '<div class="section"><h2>🏦 Kurumsal & Sosyal</h2><ul class="detail-list">'
        for v in all_extra.values():
            html += f"<li>{v}</li>"
        html += "</ul></div>"

    # Claude Analizi
    if claude_text:
        html += f"""
    <div class="section">
      <h2>🤖 Claude AI Değerlendirmesi</h2>
      <div class="claude-box">{claude_text}</div>
    </div>
"""

    html += """
  </div>
  <div class="footer">
    ⚠️ Bu analiz yalnızca bilgilendirme amaçlıdır. Finansal tavsiye değildir.<br>
    Alpha İstihbarat Sistemi — Tüm kararlar kullanıcıya aittir.
  </div>
</div>
</body>
</html>
"""
    return html


def _build_subject(score: CompositeScore) -> str:
    emoji = SIGNAL_EMOJI.get(score.signal_level, "📊")
    direction = "LONG" if score.direction in ("BULLISH", "LONG") else (
        "SHORT" if score.direction in ("BEARISH", "SHORT") else "NÖTR"
    )
    return f"{emoji} {score.symbol} — {score.signal_level} {direction} | Skor: {score.composite:.1f}/10"


def send_signal_email(
    score: CompositeScore,
    setup: TradeSetup | None = None,
    pos: PositionSize | None = None,
    claude_text: str = "",
    config: dict = None,
) -> bool:
    """
    Gmail SMTP ile sinyal emaili gönderir.
    .env'den EMAIL_SENDER, EMAIL_APP_PASSWORD, EMAIL_RECIPIENT okur.
    """
    sender = os.getenv("EMAIL_SENDER", "")
    password = os.getenv("EMAIL_APP_PASSWORD", "")
    recipient = os.getenv("EMAIL_RECIPIENT", sender)

    if not sender or not password:
        logger.warning("Email bilgileri eksik (.env: EMAIL_SENDER, EMAIL_APP_PASSWORD)")
        return False

    smtp_host = "smtp.gmail.com"
    smtp_port = 587

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = _build_subject(score)
        msg["From"] = f"Alpha İstihbarat <{sender}>"
        msg["To"] = recipient

        html_body = _build_html(score, setup, pos, claude_text)
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, recipient, msg.as_string())

        logger.info(f"Email gönderildi: {score.symbol} → {recipient}")
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error("Email auth hatası — App Password doğru mu? Gmail 2FA açık mı?")
        return False
    except Exception as e:
        logger.error(f"Email gönderim hatası: {e}")
        return False


def send_daily_report(signals: list[dict], config: dict = None) -> bool:
    """Günlük özet raporu emaili."""
    sender = os.getenv("EMAIL_SENDER", "")
    password = os.getenv("EMAIL_APP_PASSWORD", "")
    recipient = os.getenv("EMAIL_RECIPIENT", sender)

    if not sender or not password:
        return False

    now = datetime.utcnow().strftime("%Y-%m-%d")
    subject = f"📊 Alpha İstihbarat — Günlük Rapor {now}"

    strong = [s for s in signals if s.get("signal_level") == "STRONG"]
    medium = [s for s in signals if s.get("signal_level") == "MEDIUM"]

    html = f"""
<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;background:#0a0a0a;color:#e0e0e0;padding:20px;">
<div style="max-width:600px;margin:0 auto;background:#141414;border-radius:12px;padding:28px;">
<h1 style="color:#f1c40f;">📊 Günlük Özet — {now}</h1>
<p>Güçlü sinyal: <b style="color:#e74c3c;">{len(strong)}</b> |
   Orta sinyal: <b style="color:#f39c12;">{len(medium)}</b></p>
<hr style="border-color:#333;">
"""

    for s in strong + medium:
        col = "#e74c3c" if s.get("signal_level") == "STRONG" else "#f39c12"
        html += f"""
<div style="background:#1e1e1e;padding:14px;border-radius:8px;margin:12px 0;border-left:4px solid {col};">
  <b>{s.get('symbol','?')}</b> — {s.get('signal_level','?')} | Skor: {s.get('composite',0):.1f}/10 | {s.get('direction','?')}
</div>"""

    html += """
<p style="font-size:11px;color:#555;margin-top:20px;">
Alpha İstihbarat Sistemi — Bu rapor yalnızca bilgilendirme amaçlıdır.
</p>
</div></body></html>
"""

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Alpha İstihbarat <{sender}>"
        msg["To"] = recipient
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, recipient, msg.as_string())

        logger.info(f"Günlük rapor gönderildi → {recipient}")
        return True
    except Exception as e:
        logger.error(f"Günlük rapor hatası: {e}")
        return False
