#!/usr/bin/env python3
"""
bot/bot_main.py — Otomasyon Ana Döngüsü

4H mum kapanışını bekler → portfolio döngüsü çalıştırır → tekrar bekler.
%2 risk / bileşik büyüme / $100 → $100K hedefi.

Kullanım:
  python bot/bot_main.py                 # Gerçek mod (BOT_DRY_RUN=false gerekli)
  BOT_DRY_RUN=true python bot/bot_main.py  # Kuru mod (emir göndermez)
  python bot/bot_main.py --now           # Şimdi bir kez çalıştır, beklemeden
  python bot/bot_main.py --status        # Sadece durum göster
"""
import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# PYTHONPATH FIX
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# ── Logging ─────────────────────────────────────────────────
def setup_logging():
    os.makedirs("logs", exist_ok=True)
    try:
        import colorlog
        handler = colorlog.StreamHandler()
        handler.setFormatter(colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s [%(levelname)s] %(name)s: %(message)s%(reset)s",
            datefmt="%H:%M:%S"
        ))
    except ImportError:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S"
        ))

    file_handler = logging.FileHandler("logs/bot.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))

    logging.basicConfig(level=logging.INFO, handlers=[handler, file_handler])
    for noisy in ["httpx", "httpcore", "ccxt", "urllib3", "requests"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)

logger = logging.getLogger("bot.main")

# ══════════════════════════════════════════════════════════════
#  4H MUMU KAPANIŞ ZAMANLAYICISI
# ══════════════════════════════════════════════════════════════

CANDLE_SECONDS = 4 * 3600   # 4 saat

def seconds_to_next_4h() -> float:
    """Bir sonraki 4H mum kapanışına kaç saniye."""
    now = datetime.now(timezone.utc)
    epoch = now.timestamp()
    next_close = (int(epoch // CANDLE_SECONDS) + 1) * CANDLE_SECONDS
    return next_close - epoch


def wait_for_next_candle(dry_run: bool = False):
    """
    Bir sonraki 4H mum kapanışını bekler.
    DRY_RUN=true ise 30 saniye bekler (test için).
    """
    if dry_run:
        wait_sec = 30
        logger.info(f"[DRY] Test modu: {wait_sec}s bekleniyor...")
    else:
        wait_sec = seconds_to_next_4h() + 5   # 5s buffer (Binance index lag)

    next_ts = datetime.now(timezone.utc).timestamp() + wait_sec
    next_dt = datetime.fromtimestamp(next_ts, tz=timezone.utc)
    logger.info(f"Bir sonraki döngü: {next_dt:%H:%M:%S UTC}  ({wait_sec/60:.1f} dakika)")

    # İlerleme göster (her 5 dakikada bir)
    while wait_sec > 0:
        chunk = min(wait_sec, 300)
        time.sleep(chunk)
        wait_sec -= chunk
        if wait_sec > 60:
            logger.info(f"Mum kapanışına {wait_sec/60:.0f} dakika kaldı...")


# ══════════════════════════════════════════════════════════════
#  EMAIL BİLDİRİM
# ══════════════════════════════════════════════════════════════

def notify_trade(sig: dict, pos_data: dict):
    """Trade açıldığında email gönder."""
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        sender   = os.getenv("EMAIL_SENDER", "")
        password = os.getenv("EMAIL_APP_PASSWORD", "")
        recipient= os.getenv("EMAIL_RECIPIENT", sender)
        if not sender or not password:
            return

        direction = sig["trend"]
        symbol    = sig["symbol"]
        score     = sig["composite"]
        entry     = pos_data.get("notional", 0)
        lev       = pos_data.get("leverage", 1)

        dir_emoji = "🟢 LONG" if direction == "BULLISH" else "🔴 SHORT"
        subject = f"[Alpha Bot] {dir_emoji} {symbol} — Skor {score:.1f}/10"

        body = f"""
<html><body style="font-family:monospace;background:#0d0d0d;color:#e0e0e0;padding:20px">
<h2 style="color:#00ff88">{dir_emoji} {symbol}</h2>
<table style="border-collapse:collapse;width:100%">
<tr><td style="padding:4px;color:#aaa">Skor</td><td style="color:#00ff88">{score:.1f}/10</td></tr>
<tr><td style="padding:4px;color:#aaa">Kaldıraç</td><td>{lev}x</td></tr>
<tr><td style="padding:4px;color:#aaa">Notional</td><td>${pos_data.get('notional', 0):,.2f}</td></tr>
<tr><td style="padding:4px;color:#aaa">Risk</td><td>${pos_data.get('risk_usdt', 0):.2f} (%2)</td></tr>
<tr><td style="padding:4px;color:#aaa">SL</td><td style="color:#ff4444">${pos_data.get('tp1_price', 0):,.4f}</td></tr>
<tr><td style="padding:4px;color:#aaa">TP1 (+%6)</td><td style="color:#00ff88">${pos_data.get('tp1_price', 0):,.4f}</td></tr>
<tr><td style="padding:4px;color:#aaa">TP2 (+%14)</td><td style="color:#00ff88">${pos_data.get('tp2_price', 0):,.4f}</td></tr>
<tr><td style="padding:4px;color:#aaa">TP3 (+%28)</td><td style="color:#00ff88">${pos_data.get('tp3_price', 0):,.4f}</td></tr>
</table>
<p style="color:#888;font-size:11px">Alpha İstihbarat Bot — {datetime.utcnow():%Y-%m-%d %H:%M UTC}</p>
</body></html>
"""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = sender
        msg["To"]      = recipient
        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.starttls()
            smtp.login(sender, password)
            smtp.send_message(msg)

        logger.info(f"📧 Email gönderildi: {subject}")
    except Exception as e:
        logger.warning(f"Email gönderilemedi: {e}")


# ══════════════════════════════════════════════════════════════
#  STATUS ÇIKTISI
# ══════════════════════════════════════════════════════════════

def show_status():
    from bot.position_manager import get_open_positions, get_stats, init_positions_db
    from bot.compound_tracker import init_compound_db, print_compound_dashboard
    from bot.executor import get_balance
    from live_scan import head, h2, ok, bad, warn, nfo, dim, B, R, sep

    init_positions_db()
    balance = get_balance()
    init_compound_db(balance)

    head(f"BOT STATUS  {datetime.utcnow():%Y-%m-%d %H:%M UTC}")
    print(f"  Mod:    {'DRY RUN ⚠️' if os.getenv('BOT_DRY_RUN','true').lower()=='true' else ok('CANLI ✅')}")
    print(f"  Bakiye: {ok(f'${balance:,.2f}')}")

    # Açık pozisyonlar
    h2("AÇIK POZİSYONLAR")
    positions = get_open_positions()
    if not positions:
        print(f"  {dim('Açık pozisyon yok')}")
    else:
        print(f"  {'#':4} {'Sembol':14} {'Yön':6} {'Entry':>12} {'SL':>12} {'TP1':>12} {'Skor':>5}")
        sep()
        for p in positions:
            dir_c = ok("LONG") if p["direction"] == "LONG" else bad("SHORT")
            print(f"  {p['id']:<4} {p['symbol']:14} {dir_c}  "
                  f"${p['entry_price']:>10,.4f}  ${p['sl_price']:>10,.4f}  "
                  f"${p['tp1_price']:>10,.4f}  {p['signal_score']:>4.1f}")

    # Genel istatistik
    st = get_stats()
    h2("PERFORMANS")
    wr_c = ok if st["win_rate"] >= 0.52 else (warn if st["win_rate"] >= 0.45 else bad)
    print(f"  Toplam İşlem : {st['total_trades']}")
    print(f"  Win / Loss   : {ok(str(st['winning_trades']))} / {bad(str(st['losing_trades']))}")
    wr_s = f"{st['win_rate']:.1%}"
    print(f"  Win Rate     : {wr_c(wr_s)}")
    pnl_s = f"+${st['total_pnl']:,.2f}" if st["total_pnl"] >= 0 else f"${st['total_pnl']:,.2f}"
    pnl_colored = ok(pnl_s) if st["total_pnl"] >= 0 else bad(pnl_s)
    print(f"  Net P&L      : {pnl_colored}")

    # Bileşik büyüme
    print_compound_dashboard(balance)


# ══════════════════════════════════════════════════════════════
#  ANA GİRİŞ
# ══════════════════════════════════════════════════════════════

def main():
    setup_logging()

    parser = argparse.ArgumentParser(description="Alpha İstihbarat Trading Bot")
    parser.add_argument("--now",    action="store_true", help="Hemen bir döngü çalıştır")
    parser.add_argument("--status", action="store_true", help="Durum göster ve çık")
    parser.add_argument("--dry",    action="store_true", help="Dry-run modu (emir göndermez)")
    args = parser.parse_args()

    if args.dry:
        os.environ["BOT_DRY_RUN"] = "true"

    dry = os.getenv("BOT_DRY_RUN", "true").lower() == "true"

    if args.status:
        show_status()
        return

    # Güvenlik uyarısı
    if not dry:
        logger.warning("🔴 CANLI MOD — Gerçek emirler gönderilecek!")
        if not os.getenv("BINANCE_API_KEY") or not os.getenv("BINANCE_SECRET_KEY"):
            logger.error("BINANCE_API_KEY veya BINANCE_SECRET_KEY eksik!")
            sys.exit(1)
        confirm = input("CANLI MODDA devam etmek istiyor musun? (evet/hayır): ")
        if confirm.strip().lower() != "evet":
            print("İptal edildi."); return
    else:
        logger.info("✅ DRY RUN modu — Gerçek emir gönderilmez")

    logger.info("╔══════════════════════════════════════╗")
    logger.info("║  ALPHA İSTİHBARAT BOT BAŞLATILDI     ║")
    logger.info("╚══════════════════════════════════════╝")
    logger.info(f"Mod: {'DRY RUN' if dry else 'CANLI'}")
    logger.info(f"Max Pozisyon: 4  |  Risk/İşlem: %2  |  Max Kaldıraç: 5x")
    logger.info(f"Sinyal Eşiği: {MIN_SCORE:.1f}/10  |  TF: 4H")

    # ── Ana döngü ─────────────────────────────────────────────
    loop_count = 0
    while True:
        loop_count += 1
        logger.info(f"\n{'='*50}")
        logger.info(f"DÖNGÜ #{loop_count}  {datetime.utcnow():%Y-%m-%d %H:%M UTC}")

        try:
            from bot.portfolio import run_portfolio_cycle
            result = run_portfolio_cycle(notify_fn=notify_trade)
            logger.info(
                f"Döngü tamamlandı: "
                f"Sinyal={result.get('signals',0)}  "
                f"Açılan={result.get('opened',0)}  "
                f"Bakiye=${result.get('balance',0):,.2f}"
            )
        except KeyboardInterrupt:
            logger.info("Kullanıcı tarafından durduruldu.")
            break
        except Exception as e:
            logger.exception(f"Döngü hatası: {e}")

        if args.now:
            logger.info("--now bayrağı: tek döngü tamamlandı.")
            break

        # ── Bir sonraki 4H mum kapanışını bekle ───────────────
        wait_for_next_candle(dry_run=dry)


MIN_SCORE = float(os.getenv("BOT_MIN_SCORE", "6.0"))

if __name__ == "__main__":
    main()
