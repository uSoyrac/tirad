#!/usr/bin/env python3
"""
paper_trader.py — Kağıt İşlem Simülatörü
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Gerçek Binance fiyatlarıyla sanal para ticareti yapar.
Canlıya geçmeden önce 2 hafta boyunca stratejiyi test et.

Kullanım:
  python paper_trader.py                  # 4H döngü modunda çalıştır
  python paper_trader.py --now            # Şimdi bir döngü çalıştır
  python paper_trader.py --report         # Detaylı rapor göster
  python paper_trader.py --reset          # DB'yi sıfırla ve yeniden başla
  python paper_trader.py --balance 500    # Başlangıç bakiyesi ayarla (varsayılan: $200)

Özellikler:
  • Gerçek sinyal motoru (live_scan.py SMC analizi)
  • Gerçek Binance fiyatları (ccxt public API — API key gerekmez)
  • 4H mum OHLC ile SL/TP simülasyonu
  • Bileşik büyüme takibi + kilometre taşları
  • Her trade için email bildirimi (isteğe bağlı)
  • Canlı mod hazırlık skoru hesaplaması
"""

import argparse
import json
import logging
import math
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

# ── Logging ──────────────────────────────────────────────────────────
def _setup_logging():
    os.makedirs("logs", exist_ok=True)
    try:
        import colorlog
        h = colorlog.StreamHandler()
        h.setFormatter(colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s [%(levelname)s] %(name)s: %(message)s%(reset)s",
            datefmt="%H:%M:%S"
        ))
    except ImportError:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S"
        ))
    fh = logging.FileHandler("logs/paper_trader.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[h, fh])
    for noisy in ["httpx", "httpcore", "ccxt", "urllib3", "requests"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)

_setup_logging()
logger = logging.getLogger("paper")

# ══════════════════════════════════════════════════════════════════════
#  YAPILANDIRMA
# ══════════════════════════════════════════════════════════════════════

PAPER_DB      = os.getenv("PAPER_DB", "data/database/paper_trades.db")
START_BALANCE = float(os.getenv("PAPER_START_BALANCE", "200.0"))
MAX_POSITIONS = 4
MIN_SCORE     = float(os.getenv("PAPER_MIN_SCORE", "6.0"))
RISK_PCT      = 0.02    # %2 sabit risk
MAX_LEVERAGE  = 5
TARGET_X      = 500     # $200 → $100,000 (500x)

WATCHLIST = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "AVAX/USDT",
    "LINK/USDT", "DOT/USDT", "XRP/USDT",
]

CANDLE_SECONDS = 4 * 3600   # 4 saat

# ── TP/SL parametreleri (risk_manager ile aynı) ────────────────────
TP1_PCT   = 0.06;  TP1_CLOSE = 0.40
TP2_PCT   = 0.14;  TP2_CLOSE = 0.35
TP3_PCT   = 0.28;  TP3_CLOSE = 0.25

# ══════════════════════════════════════════════════════════════════════
#  VERİTABANI
# ══════════════════════════════════════════════════════════════════════

def _conn():
    os.makedirs(os.path.dirname(PAPER_DB), exist_ok=True)
    conn = sqlite3.connect(PAPER_DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(start_balance: float = START_BALANCE):
    """Tabloları oluştur, ilk kayıtları ekle."""
    with _conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS paper_positions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol       TEXT    NOT NULL,
            direction    TEXT    NOT NULL,
            entry_price  REAL    NOT NULL,
            quantity     REAL    NOT NULL,
            sl_price     REAL    NOT NULL,
            tp1_price    REAL,
            tp2_price    REAL,
            tp3_price    REAL,
            tp1_qty      REAL,
            tp2_qty      REAL,
            tp3_qty      REAL,
            leverage     INTEGER DEFAULT 3,
            risk_usdt    REAL    DEFAULT 0,
            notional     REAL    DEFAULT 0,
            signal_score REAL    DEFAULT 0,
            tp1_hit      INTEGER DEFAULT 0,
            tp2_hit      INTEGER DEFAULT 0,
            tp3_hit      INTEGER DEFAULT 0,
            sl_moved_be  INTEGER DEFAULT 0,
            status       TEXT    DEFAULT 'OPEN',
            pnl_usdt     REAL    DEFAULT 0,
            opened_at    TEXT,
            closed_at    TEXT,
            closed_price REAL    DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS paper_equity (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            balance    REAL    NOT NULL,
            pnl_usdt   REAL    DEFAULT 0,
            event      TEXT    DEFAULT '',
            symbol     TEXT    DEFAULT '',
            ts         TEXT    DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS paper_meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        """)

        # Başlangıç bakiyesi (sadece boşsa)
        existing = conn.execute(
            "SELECT COUNT(*) FROM paper_equity"
        ).fetchone()[0]
        if existing == 0:
            conn.execute(
                "INSERT INTO paper_equity (balance, event, ts) VALUES (?, 'START', ?)",
                (start_balance, datetime.utcnow().isoformat())
            )
            conn.execute(
                "INSERT OR REPLACE INTO paper_meta (key, value) VALUES (?, ?)",
                ("start_balance", str(start_balance))
            )
            conn.execute(
                "INSERT OR REPLACE INTO paper_meta (key, value) VALUES (?, ?)",
                ("start_ts", datetime.utcnow().isoformat())
            )
            logger.info(f"Paper trader başlatıldı: ${start_balance:.2f}")


def get_paper_balance() -> float:
    """Güncel simüle bakiye."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT balance FROM paper_equity ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return float(row[0]) if row else START_BALANCE


def get_start_balance() -> float:
    with _conn() as conn:
        row = conn.execute(
            "SELECT value FROM paper_meta WHERE key='start_balance'"
        ).fetchone()
        return float(row[0]) if row else START_BALANCE


def get_start_ts() -> Optional[datetime]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT value FROM paper_meta WHERE key='start_ts'"
        ).fetchone()
        if row:
            try:
                return datetime.fromisoformat(row[0])
            except Exception:
                return None
    return None


def record_equity(balance: float, pnl: float, event: str, symbol: str = ""):
    with _conn() as conn:
        conn.execute(
            "INSERT INTO paper_equity (balance, pnl_usdt, event, symbol, ts) VALUES (?,?,?,?,?)",
            (balance, pnl, event, symbol, datetime.utcnow().isoformat())
        )


def save_paper_position(pos: dict) -> int:
    with _conn() as conn:
        cur = conn.execute("""
        INSERT INTO paper_positions
        (symbol, direction, entry_price, quantity, sl_price,
         tp1_price, tp2_price, tp3_price, tp1_qty, tp2_qty, tp3_qty,
         leverage, risk_usdt, notional, signal_score, opened_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            pos["symbol"], pos["direction"], pos["entry_price"],
            pos["quantity"], pos["sl_price"],
            pos["tp1_price"], pos["tp2_price"], pos["tp3_price"],
            pos["tp1_qty"],   pos["tp2_qty"],   pos["tp3_qty"],
            pos.get("leverage", 3), pos.get("risk_usdt", 0),
            pos.get("notional", 0), pos.get("signal_score", 0),
            datetime.utcnow().isoformat(),
        ))
        return cur.lastrowid


def get_open_paper_positions() -> List[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM paper_positions WHERE status='OPEN'"
        ).fetchall()
        return [dict(r) for r in rows]


def update_paper_position(pos_id: int, **kwargs):
    if not kwargs:
        return
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [pos_id]
    with _conn() as conn:
        conn.execute(f"UPDATE paper_positions SET {sets} WHERE id=?", vals)


def get_paper_stats() -> dict:
    with _conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM paper_positions WHERE status != 'OPEN'"
        ).fetchone()[0]
        wins = conn.execute(
            "SELECT COUNT(*) FROM paper_positions WHERE status LIKE '%WIN%'"
        ).fetchone()[0]
        total_pnl = conn.execute(
            "SELECT COALESCE(SUM(pnl_usdt),0) FROM paper_positions WHERE status != 'OPEN'"
        ).fetchone()[0]
        best = conn.execute(
            "SELECT COALESCE(MAX(pnl_usdt),0) FROM paper_positions"
        ).fetchone()[0]
        worst = conn.execute(
            "SELECT COALESCE(MIN(pnl_usdt),0) FROM paper_positions"
        ).fetchone()[0]
        open_cnt = conn.execute(
            "SELECT COUNT(*) FROM paper_positions WHERE status='OPEN'"
        ).fetchone()[0]
        longs = conn.execute(
            "SELECT COUNT(*) FROM paper_positions WHERE direction='LONG' AND status!='OPEN'"
        ).fetchone()[0]
        shorts = conn.execute(
            "SELECT COUNT(*) FROM paper_positions WHERE direction='SHORT' AND status!='OPEN'"
        ).fetchone()[0]
        avg_score = conn.execute(
            "SELECT COALESCE(AVG(signal_score),0) FROM paper_positions WHERE status!='OPEN'"
        ).fetchone()[0]

    return {
        "total_trades":   total,
        "winning_trades": wins,
        "losing_trades":  total - wins,
        "win_rate":       wins / total if total > 0 else 0,
        "total_pnl":      total_pnl,
        "best_trade":     best,
        "worst_trade":    worst,
        "open_positions": open_cnt,
        "longs":          longs,
        "shorts":         shorts,
        "avg_score":      avg_score,
    }


# ══════════════════════════════════════════════════════════════════════
#  POZISYON BOYUTLANDIRMA
# ══════════════════════════════════════════════════════════════════════

def _calc_position(balance: float, entry: float, sl: float,
                   score: float, open_count: int) -> Optional[dict]:
    """risk_manager.calculate_position ile aynı mantık."""
    if balance <= 0 or entry <= 0 or sl <= 0:
        return None

    direction = "LONG" if entry > sl else "SHORT"
    sl_dist = abs(entry - sl) / entry

    if sl_dist <= 0.001 or sl_dist > 0.08:
        return None

    adj_risk = RISK_PCT * (1 - open_count * 0.002)
    risk_usdt = balance * max(adj_risk, 0.01)

    notional_needed = risk_usdt / sl_dist
    leverage = max(1, min(math.ceil(notional_needed / balance), MAX_LEVERAGE))

    # Skor tabanlı kaldıraç tavanı
    max_lev = 5 if score >= 8.0 else (4 if score >= 6.5 else (3 if score >= 5.5 else 2))
    leverage = min(leverage, max_lev)
    notional = balance * leverage

    if notional < 6.0:   # minimum
        return None

    qty = notional / entry

    if direction == "LONG":
        tp1 = entry * (1 + TP1_PCT)
        tp2 = entry * (1 + TP2_PCT)
        tp3 = entry * (1 + TP3_PCT)
    else:
        tp1 = entry * (1 - TP1_PCT)
        tp2 = entry * (1 - TP2_PCT)
        tp3 = entry * (1 - TP3_PCT)

    # EV kontrolü
    blended_rr = TP1_CLOSE * (TP1_PCT / sl_dist) + TP2_CLOSE * (TP2_PCT / sl_dist)
    est_wr = max(0.40, min(0.70, 0.45 + (score - 4.0) / 6.0 * 0.20))
    ev = est_wr * blended_rr - (1 - est_wr)
    if ev < -0.05:
        return None

    return {
        "direction":  direction,
        "risk_usdt":  risk_usdt,
        "sl_pct":     sl_dist * 100,
        "leverage":   leverage,
        "notional":   notional,
        "quantity":   qty,
        "tp1_price":  tp1, "tp2_price": tp2, "tp3_price": tp3,
        "tp1_qty":    qty * TP1_CLOSE,
        "tp2_qty":    qty * TP2_CLOSE,
        "tp3_qty":    qty * TP3_CLOSE,
        "ev":         ev,
        "est_wr":     est_wr,
    }


# ══════════════════════════════════════════════════════════════════════
#  BINANCE FİYAT VERİSİ (public — API key gerekmez)
# ══════════════════════════════════════════════════════════════════════

_exchange_obj = None

def _ex():
    global _exchange_obj
    if _exchange_obj is None:
        import ccxt
        _exchange_obj = ccxt.binance({
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        })
    return _exchange_obj


def _last_price(symbol: str) -> float:
    try:
        t = _ex().fetch_ticker(symbol)
        return float(t["last"])
    except Exception as e:
        logger.warning(f"Fiyat alınamadı ({symbol}): {e}")
        return 0.0


def _fetch_last_candle(symbol: str, tf: str = "4h") -> Optional[dict]:
    """Son kapanmış 4H mumu döner {open, high, low, close}."""
    try:
        ohlcv = _ex().fetch_ohlcv(symbol, tf, limit=2)
        if len(ohlcv) < 2:
            return None
        # Son kapanmış = index 0 (en yeni bitmemiş mum = index 1 olmasın diye -2)
        c = ohlcv[-2]   # [ts, o, h, l, c, v]
        return {"open": c[1], "high": c[2], "low": c[3], "close": c[4]}
    except Exception as e:
        logger.warning(f"OHLCV alınamadı ({symbol}): {e}")
        return None


# ══════════════════════════════════════════════════════════════════════
#  SL / TP SİMÜLASYONU
# ══════════════════════════════════════════════════════════════════════

def _simulate_candle(pos: dict, candle: dict) -> Optional[str]:
    """
    Bir mum içinde SL veya TP vuruşunu simüle eder.
    Dönüş: "SL" / "TP1" / "TP2" / "TP3" / None
    Gerçekçilik: Mum içi fiyat hareketini SL önce kontrol eder
    (muhafazakâr — gerçekte TP önce de vurabilir).
    """
    hi = candle["high"]
    lo = candle["low"]
    d  = pos["direction"]
    sl = pos["sl_price"]

    # SL önce kontrol et (muhafazakâr)
    if d == "LONG":
        if lo <= sl:                                  return "SL"
        if not pos["tp3_hit"] and hi >= pos["tp3_price"]: return "TP3"
        if not pos["tp2_hit"] and hi >= pos["tp2_price"]: return "TP2"
        if not pos["tp1_hit"] and hi >= pos["tp1_price"]: return "TP1"
    else:  # SHORT
        if hi >= sl:                                  return "SL"
        if not pos["tp3_hit"] and lo <= pos["tp3_price"]: return "TP3"
        if not pos["tp2_hit"] and lo <= pos["tp2_price"]: return "TP2"
        if not pos["tp1_hit"] and lo <= pos["tp1_price"]: return "TP1"

    return None


def _handle_tp1(pos_id: int, pos: dict, price: float, balance: float) -> float:
    """TP1 gerçekleşti: kısmı P&L hesapla, SL → breakeven'a taş, bakiyeyi güncelle."""
    pnl = abs(pos["tp1_price"] - pos["entry_price"]) / pos["entry_price"] \
          * pos["notional"] * TP1_CLOSE
    new_balance = balance + pnl
    update_paper_position(
        pos_id,
        tp1_hit=1,
        sl_moved_be=1,
        sl_price=pos["entry_price"],   # breakeven
        pnl_usdt=pos["pnl_usdt"] + pnl,
    )
    record_equity(new_balance, pnl, "TP1", pos["symbol"])
    logger.info(f"  📈 #{pos_id} {pos['symbol']} TP1 @ ${price:,.4f}  "
                f"PnL=${pnl:+.2f}  Bakiye=${new_balance:,.2f}")
    return new_balance


def _handle_tp2(pos_id: int, pos: dict, price: float, balance: float) -> float:
    pnl = abs(pos["tp2_price"] - pos["entry_price"]) / pos["entry_price"] \
          * pos["notional"] * TP2_CLOSE
    new_balance = balance + pnl
    update_paper_position(pos_id, tp2_hit=1, pnl_usdt=pos["pnl_usdt"] + pnl)
    record_equity(new_balance, pnl, "TP2", pos["symbol"])
    logger.info(f"  🎯 #{pos_id} {pos['symbol']} TP2 @ ${price:,.4f}  "
                f"PnL=${pnl:+.2f}  Bakiye=${new_balance:,.2f}")
    return new_balance


def _handle_close(pos_id: int, pos: dict, exit_price: float,
                  balance: float, status: str) -> float:
    """Pozisyonu kapat (SL / TP3 / zorla kapatma)."""
    entry = pos["entry_price"]
    d     = pos["direction"]
    raw_pnl_pct = (exit_price - entry) / entry if d == "LONG" else (entry - exit_price) / entry
    raw_pnl = raw_pnl_pct * pos["notional"]

    # TP1 veya TP2 zaten kısmi kapandıysa, kalan miktar üzerinden P&L hesapla
    already_closed_pct = (TP1_CLOSE if pos["tp1_hit"] else 0) + (TP2_CLOSE if pos["tp2_hit"] else 0)
    remaining_pct = 1.0 - already_closed_pct
    # Kalan kısım için P&L
    remaining_pnl = raw_pnl_pct * pos["notional"] * remaining_pct

    total_pnl = pos["pnl_usdt"] + remaining_pnl
    new_balance = balance + remaining_pnl

    update_paper_position(
        pos_id,
        status=status,
        pnl_usdt=total_pnl,
        closed_at=datetime.utcnow().isoformat(),
        closed_price=exit_price,
    )
    record_equity(new_balance, remaining_pnl, status, pos["symbol"])

    icon = "✅" if "WIN" in status or "TP" in status else "❌"
    logger.info(
        f"  {icon} #{pos_id} {pos['symbol']} KAPANDI [{status}]  "
        f"exit=${exit_price:,.4f}  PnL=${total_pnl:+.2f}  Bakiye=${new_balance:,.2f}"
    )
    return new_balance


# ══════════════════════════════════════════════════════════════════════
#  AÇIK POZİSYONLARI KONTROL ET
# ══════════════════════════════════════════════════════════════════════

def check_open_positions(balance: float) -> float:
    """Tüm açık kağıt pozisyonları için son mum analizi yap."""
    positions = get_open_paper_positions()
    if not positions:
        return balance

    logger.info(f"Açık pozisyon kontrolü: {len(positions)} pozisyon")

    for pos in positions:
        pos_id = pos["id"]
        symbol = pos["symbol"]

        candle = _fetch_last_candle(symbol, "4h")
        if not candle:
            continue

        hit = _simulate_candle(pos, candle)
        if hit is None:
            price = _last_price(symbol)
            pnl_live = (price - pos["entry_price"]) / pos["entry_price"] * pos["notional"]
            pnl_live = pnl_live if pos["direction"] == "LONG" else -pnl_live
            pnl_s = f"+${pnl_live:+.2f}" if pnl_live >= 0 else f"${pnl_live:.2f}"
            logger.info(f"  📊 #{pos_id} {symbol:12} AÇIK  ${price:,.4f}  PnL: {pnl_s}")
            continue

        # TP1
        if hit == "TP1":
            balance = _handle_tp1(pos_id, pos, pos["tp1_price"], balance)
            # Pozisyonu yeni duruma göre yenile
            pos = dict(get_open_paper_positions_by_id(pos_id) or pos)
            continue

        # TP2 (TP1 daha önce vurulmuş olmalı)
        if hit == "TP2":
            if not pos["tp1_hit"]:
                balance = _handle_tp1(pos_id, pos, pos["tp1_price"], balance)
                pos = dict(get_open_paper_positions_by_id(pos_id) or pos)
            balance = _handle_tp2(pos_id, pos, pos["tp2_price"], balance)
            pos = dict(get_open_paper_positions_by_id(pos_id) or pos)
            continue

        # TP3 → pozisyonu kapat
        if hit == "TP3":
            if not pos["tp1_hit"]:
                balance = _handle_tp1(pos_id, pos, pos["tp1_price"], balance)
                pos = dict(get_open_paper_positions_by_id(pos_id) or pos)
            if not pos["tp2_hit"]:
                balance = _handle_tp2(pos_id, pos, pos["tp2_price"], balance)
                pos = dict(get_open_paper_positions_by_id(pos_id) or pos)
            balance = _handle_close(pos_id, pos, pos["tp3_price"], balance, "CLOSED_WIN_TP3")
            continue

        # SL
        if hit == "SL":
            status = "CLOSED_BE" if pos["sl_moved_be"] else "CLOSED_LOSS"
            balance = _handle_close(pos_id, pos, pos["sl_price"], balance, status)

        time.sleep(0.2)

    return balance


def get_open_paper_positions_by_id(pos_id: int) -> Optional[dict]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM paper_positions WHERE id=?", (pos_id,)
        ).fetchone()
        return dict(row) if row else None


# ══════════════════════════════════════════════════════════════════════
#  SİNYAL TARAMA & POZİSYON AÇMA
# ══════════════════════════════════════════════════════════════════════

def scan_and_open(balance: float) -> tuple:
    """Sinyalleri tara, uygun olanları kağıt pozisyon olarak aç."""
    from live_scan import ohlcv, analyze

    open_pos  = get_open_paper_positions()
    open_syms = {p["symbol"] for p in open_pos}
    slots     = MAX_POSITIONS - len(open_pos)

    if slots <= 0:
        logger.info("Max kağıt pozisyon sınırına ulaşıldı.")
        return balance, 0

    logger.info(f"Sinyal taranıyor: {len(WATCHLIST)} sembol  "
                f"({MAX_POSITIONS - slots}/{MAX_POSITIONS} slot dolu)")

    signals = []
    for symbol in WATCHLIST:
        if symbol in open_syms:
            continue
        try:
            df = ohlcv(symbol, "4h", 350)
            if df.empty or len(df) < 100:
                continue
            r = analyze(symbol, is_bist=False)
            if not r:
                continue
            score = r.get("composite", 0)
            trend = r.get("trend", "NEUTRAL")
            if score >= MIN_SCORE and trend in ("BULLISH", "BEARISH"):
                if r.get("entry_low") and r.get("sl"):
                    signals.append(r)
                    logger.info(f"  ✨ {symbol:12} {score:.1f}/10  {trend}")
                else:
                    logger.info(f"  ○  {symbol:12} {score:.1f}/10  (entry/sl eksik)")
            else:
                logger.info(f"  ○  {symbol:12} {score:.1f}/10  {trend}")
        except Exception as e:
            logger.warning(f"  ✗  {symbol}: {e}")
        time.sleep(0.3)

    signals.sort(key=lambda x: x["composite"], reverse=True)
    opened = 0

    for sig in signals[:slots]:
        entry  = (sig["entry_low"] + sig["entry_high"]) / 2
        sl     = sig["sl"]
        score  = sig["composite"]
        symbol = sig["symbol"]

        calc = _calc_position(balance, entry, sl, score, len(open_pos) + opened)
        if calc is None:
            logger.warning(f"  ✗ {symbol}: Pozisyon hesaplanamadı")
            continue

        pos_id = save_paper_position({
            "symbol":       symbol,
            "direction":    calc["direction"],
            "entry_price":  entry,
            "quantity":     calc["quantity"],
            "sl_price":     sl,
            "tp1_price":    calc["tp1_price"],
            "tp2_price":    calc["tp2_price"],
            "tp3_price":    calc["tp3_price"],
            "tp1_qty":      calc["tp1_qty"],
            "tp2_qty":      calc["tp2_qty"],
            "tp3_qty":      calc["tp3_qty"],
            "leverage":     calc["leverage"],
            "risk_usdt":    calc["risk_usdt"],
            "notional":     calc["notional"],
            "signal_score": score,
        })
        record_equity(balance, 0, "OPEN", symbol)

        dir_s = "LONG 📈" if calc["direction"] == "LONG" else "SHORT 📉"
        logger.info(
            f"  ✅ #{pos_id} {symbol:12} {dir_s}  "
            f"entry=${entry:,.4f}  SL=${sl:,.4f}  "
            f"Lev={calc['leverage']}x  Notional=${calc['notional']:.2f}"
        )
        opened += 1
        _notify_trade(sig, calc, pos_id)

    return balance, opened


# ══════════════════════════════════════════════════════════════════════
#  EMAIL BİLDİRİM
# ══════════════════════════════════════════════════════════════════════

def _notify_trade(sig: dict, calc: dict, pos_id: int):
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        sender    = os.getenv("EMAIL_SENDER", "")
        password  = os.getenv("EMAIL_APP_PASSWORD", "")
        recipient = os.getenv("EMAIL_RECIPIENT", sender)
        if not sender or not password:
            return

        symbol    = sig["symbol"]
        direction = calc["direction"]
        score     = sig["composite"]
        entry     = (sig["entry_low"] + sig["entry_high"]) / 2
        dir_emoji = "🟢 LONG" if direction == "LONG" else "🔴 SHORT"

        subject = f"[PAPER] {dir_emoji} {symbol} — Skor {score:.1f}/10"

        body = f"""
<html><body style="font-family:monospace;background:#111;color:#e0e0e0;padding:20px">
<h2 style="color:#ffa500">📝 KAĞIT İŞLEM #{pos_id}</h2>
<h3 style="color:{'#00ff88' if direction=='LONG' else '#ff4444'}">{dir_emoji} {symbol}</h3>
<table style="border-collapse:collapse;width:100%">
<tr><td style="padding:6px;color:#aaa">Skor</td>
    <td style="color:#00ff88;font-weight:bold">{score:.1f}/10</td></tr>
<tr><td style="padding:6px;color:#aaa">Giriş</td>
    <td>${entry:,.4f}</td></tr>
<tr><td style="padding:6px;color:#aaa">Stop Loss</td>
    <td style="color:#ff4444">${sig['sl']:,.4f}  ({calc['sl_pct']:.1f}%)</td></tr>
<tr><td style="padding:6px;color:#aaa">TP1 (+6%)</td>
    <td style="color:#00ff88">${calc['tp1_price']:,.4f}</td></tr>
<tr><td style="padding:6px;color:#aaa">TP2 (+14%)</td>
    <td style="color:#00ff88">${calc['tp2_price']:,.4f}</td></tr>
<tr><td style="padding:6px;color:#aaa">TP3 (+28%)</td>
    <td style="color:#00ff88">${calc['tp3_price']:,.4f}</td></tr>
<tr><td style="padding:6px;color:#aaa">Kaldıraç</td>
    <td>{calc['leverage']}x</td></tr>
<tr><td style="padding:6px;color:#aaa">Notional</td>
    <td>${calc['notional']:.2f} (simüle)</td></tr>
<tr><td style="padding:6px;color:#aaa">Risk</td>
    <td>${calc['risk_usdt']:.2f} (%2)</td></tr>
</table>
<p style="background:#1a1a1a;padding:10px;border-radius:4px;color:#ffa500">
  ⚠️ Bu bir <strong>KAĞIT İŞLEM</strong> bildirimidir — gerçek para kullanılmıyor.
</p>
<p style="color:#555;font-size:11px">
  Alpha Paper Trader — {datetime.utcnow():%Y-%m-%d %H:%M UTC}
</p>
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

        logger.info(f"📧 Kağıt trade email: {subject}")
    except Exception as e:
        logger.debug(f"Email gönderilemedi: {e}")


# ══════════════════════════════════════════════════════════════════════
#  CANLI MOD HAZIRLIK SKORU
# ══════════════════════════════════════════════════════════════════════

def live_readiness_score(stats: dict, balance: float, days_running: int) -> dict:
    """
    Stratejiyi canlı moda taşımaya hazır mı?
    0-100 puan verir, eşik = 70.
    """
    score = 0
    reasons = []
    warnings = []

    # 1. İşlem sayısı (min 10 gerekli, 20 ideal)
    n = stats["total_trades"]
    if n >= 20:
        score += 25; reasons.append(f"✅ {n} işlem tamamlandı (≥20)")
    elif n >= 10:
        score += 15; reasons.append(f"⚠️  {n} işlem (≥10, ideal 20)")
        warnings.append(f"Daha fazla işlem verisi toplanmalı ({n}/20)")
    else:
        reasons.append(f"❌ Yalnızca {n} işlem (<10)")
        warnings.append(f"En az 10 işlem tamamlanmalı ({n}/10)")

    # 2. Win rate (min 0.45, ideal 0.55+)
    wr = stats["win_rate"]
    if wr >= 0.55:
        score += 25; reasons.append(f"✅ Win rate {wr:.1%} (≥55%)")
    elif wr >= 0.45:
        score += 15; reasons.append(f"⚠️  Win rate {wr:.1%} (≥45%, ideal ≥55%)")
        warnings.append("Win rate düşük — sinyaller yeniden değerlendirilebilir")
    else:
        reasons.append(f"❌ Win rate {wr:.1%} (<45%)")
        warnings.append("Kritik: Win rate çok düşük — canlıya geçme!")

    # 3. Pozitif P&L
    pnl = stats["total_pnl"]
    n_trades_pnl = stats["total_trades"]
    start = get_start_balance()
    ret_pct = (pnl / start) * 100 if start > 0 else 0
    if n_trades_pnl == 0:
        reasons.append("⚠️  Henüz tamamlanan işlem yok")
    elif pnl > 0 and ret_pct > 10:
        score += 20; reasons.append(f"✅ Net kâr +${pnl:.2f} (+{ret_pct:.1f}%)")
    elif pnl >= 0:
        score += 8;  reasons.append(f"⚠️  Düşük kâr +${pnl:.2f} (+{ret_pct:.1f}%)")
        warnings.append("Kâr marjı düşük — daha fazla test verisi gerekli")
    else:
        reasons.append(f"❌ Negatif P&L ${pnl:.2f}")
        warnings.append("Zarar var — strateji gözden geçirilmeli")

    # 4. Süre (min 7 gün, ideal 14 gün)
    if days_running >= 14:
        score += 15; reasons.append(f"✅ {days_running} gün test edildi (≥14)")
    elif days_running >= 7:
        score += 8;  reasons.append(f"⚠️  {days_running} gün (≥7, ideal 14)")
        warnings.append(f"2 haftalık test tamamlanmalı ({days_running}/14 gün)")
    else:
        reasons.append(f"❌ Yalnızca {days_running} gün (<7)")
        warnings.append(f"Test süresi yetersiz ({days_running}/7 gün minimum)")

    # 5. Max drawdown tahmini (equity curve'den)
    max_dd = _calc_max_drawdown()
    if max_dd < 15:
        score += 15; reasons.append(f"✅ Max drawdown {max_dd:.1f}% (<15%)")
    elif max_dd < 25:
        score += 8;  reasons.append(f"⚠️  Max drawdown {max_dd:.1f}% (<25%)")
        warnings.append("Drawdown biraz yüksek — pozisyon boyutu küçültülebilir")
    else:
        reasons.append(f"❌ Max drawdown {max_dd:.1f}% (>25%)")
        warnings.append("Kritik drawdown — risk parametreleri revize edilmeli")

    ready = score >= 70
    return {
        "score":    score,
        "max":      100,
        "ready":    ready,
        "reasons":  reasons,
        "warnings": warnings,
        "verdict":  "✅ CANLI MODA HAZIR" if ready else "⏳ TEST DEVAM ETMELİ",
    }


def _calc_max_drawdown() -> float:
    """Equity curve'den max drawdown hesapla."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT balance FROM paper_equity ORDER BY id"
        ).fetchall()
    if not rows:
        return 0.0
    balances = [r[0] for r in rows]
    peak = balances[0]
    max_dd = 0.0
    for b in balances:
        if b > peak:
            peak = b
        dd = (peak - b) / peak * 100
        if dd > max_dd:
            max_dd = dd
    return max_dd


# ══════════════════════════════════════════════════════════════════════
#  DASHBOARD & RAPOR
# ══════════════════════════════════════════════════════════════════════

def print_paper_dashboard(balance: float):
    """Kağıt işlem durumu ekranı."""
    try:
        from live_scan import ok, bad, warn, dim, nfo, B, R, CY, GR, YL, DM
    except ImportError:
        B=R=CY=GR=YL=DM=""
        def ok(s): return s
        def bad(s): return s
        def warn(s): return s
        def dim(s): return s
        def nfo(s): return s

    stats    = get_paper_stats()
    start    = get_start_balance()
    start_ts = get_start_ts()
    days     = (datetime.utcnow() - start_ts).days if start_ts else 0
    max_dd   = _calc_max_drawdown()
    x_gained = balance / start if start > 0 else 1
    target   = start * TARGET_X
    prog_pct = math.log(x_gained) / math.log(TARGET_X) * 100 if x_gained > 1 else 0
    prog_pct = min(prog_pct, 100)

    # Progress bar (log-scale)
    BAR    = 50
    filled = max(1, int(prog_pct / 100 * BAR))
    bar_c  = GR if prog_pct > 50 else (YL if prog_pct > 20 else CY)
    bar    = bar_c + "█" * filled + DM + "░" * (BAR - filled) + R

    sep = "═" * 64

    print(f"\n  {sep}")
    print(f"  {B}  📝 KAĞIT İŞLEM RAPORU  [{datetime.utcnow():%Y-%m-%d %H:%M UTC}]{R}")
    print(f"  {sep}")

    # Bakiye + hedef
    pnl_abs  = balance - start
    pnl_sign = f"+${pnl_abs:+,.2f}" if pnl_abs >= 0 else f"${pnl_abs:,.2f}"
    pnl_col  = ok(pnl_sign) if pnl_abs >= 0 else bad(pnl_sign)
    print(f"  Başlangıç   : {B}${start:,.2f}{R}")
    print(f"  Mevcut      : {ok(f'${balance:,.2f}')}  ({pnl_col}  {ok(f'{x_gained:.3f}x')})")
    print(f"  Hedef       : {dim(f'${target:,.0f}')}  ({TARGET_X}x)")
    print(f"  Süre        : {nfo(str(days))} gün  |  Max DD: {warn(f'{max_dd:.1f}%')}")
    print(f"\n  {bar}  {prog_pct:.2f}%")

    # İşlem istatistikleri
    print(f"\n  {'─'*64}")
    if stats["total_trades"] > 0:
        wr   = stats["win_rate"]
        wc   = ok if wr >= 0.52 else (warn if wr >= 0.45 else bad)
        pf   = (stats["best_trade"] * stats["winning_trades"]) / \
               max(abs(stats["worst_trade"]) * stats["losing_trades"], 0.01)
        print(f"  İşlem Sayısı : {nfo(str(stats['total_trades']))}  "
              f"(🏆{stats['winning_trades']} / ❌{stats['losing_trades']})")
        print(f"  Win Rate     : {wc(f'{wr:.1%}')}")
        pnl_s = f"+${stats['total_pnl']:+,.2f}" if stats["total_pnl"] >= 0 else f"${stats['total_pnl']:,.2f}"
        pnl_c = ok(pnl_s) if stats["total_pnl"] >= 0 else bad(pnl_s)
        print(f"  Net P&L      : {pnl_c}")
        best_s  = f"+${stats['best_trade']:+.2f}"
        worst_s = f"${stats['worst_trade']:.2f}"
        avg_sc  = f"{stats['avg_score']:.1f}/10"
        print(f"  En İyi / En Kötü : {ok(best_s)}  /  {bad(worst_s)}")
        print(f"  Long / Short : {nfo(str(stats['longs']))} / {nfo(str(stats['shorts']))}")
        print(f"  Ort. Skor    : {nfo(avg_sc)}")
    else:
        print(f"  {dim('Henüz tamamlanan işlem yok.')}")

    # Açık pozisyonlar
    open_pos = get_open_paper_positions()
    if open_pos:
        print(f"\n  {'─'*64}")
        print(f"  {B}Açık Kağıt Pozisyonlar:{R}")
        for p in open_pos:
            price   = _last_price(p["symbol"])
            d       = p["direction"]
            raw_pnl = (price - p["entry_price"]) / p["entry_price"] * p["notional"]
            live_pnl = raw_pnl if d == "LONG" else -raw_pnl
            pnl_live_s = f"+${live_pnl:+.2f}" if live_pnl >= 0 else f"${live_pnl:.2f}"
            pnl_live_c = ok(pnl_live_s) if live_pnl >= 0 else bad(pnl_live_s)
            tp1_mark   = ok("✓") if p["tp1_hit"] else dim("○")
            dir_c      = ok("LONG") if d == "LONG" else bad("SHORT")
            print(f"  #{p['id']:<3} {p['symbol']:12} {dir_c}  "
                  f"entry=${p['entry_price']:,.4f}  now=${price:,.4f}  "
                  f"PnL:{pnl_live_c}  TP1:{tp1_mark}")

    # Canlı hazırlık skoru
    readiness = live_readiness_score(stats, balance, days)
    rsc = readiness["score"]
    rc  = ok if rsc >= 70 else (warn if rsc >= 50 else bad)
    print(f"\n  {'─'*64}")
    print(f"  {B}Canlı Mod Hazırlık:{R}  {rc(str(rsc))}/100  {readiness['verdict']}")
    for r in readiness["reasons"]:
        print(f"    {r}")
    if readiness["warnings"]:
        print(f"\n  {B}Uyarılar:{R}")
        for w in readiness["warnings"]:
            print(f"    ⚠️  {w}")

    print(f"\n  {sep}\n")


def print_full_report():
    """Tüm kağıt işlemlerin detaylı listesi."""
    try:
        from live_scan import ok, bad, warn, dim, nfo, B, R
    except ImportError:
        B=R=""
        def ok(s): return s
        def bad(s): return s
        def warn(s): return s
        def dim(s): return s
        def nfo(s): return s

    balance = get_paper_balance()
    print_paper_dashboard(balance)

    with _conn() as conn:
        rows = conn.execute("""
        SELECT id, symbol, direction, entry_price, closed_price,
               pnl_usdt, status, signal_score, leverage, notional,
               opened_at, closed_at, tp1_hit, tp2_hit
        FROM paper_positions
        ORDER BY id
        """).fetchall()

    if not rows:
        print("  Henüz işlem yok.\n")
        return

    print(f"\n  {'─'*90}")
    hdr = f"  {'#':>3} {'Sembol':12} {'Yön':5} {'Giriş':>10} {'Çıkış':>10} " \
          f"{'P&L':>9} {'Skor':>5} {'Durum'}"
    print(f"  {B}{hdr}{R}")
    print(f"  {'─'*90}")

    for r in rows:
        closed = r["closed_price"]
        pnl    = r["pnl_usdt"]
        status = r["status"]
        is_win = "WIN" in status or "TP" in status
        is_open = status == "OPEN"

        pnl_s = f"{pnl:+.2f}" if not is_open else "  open"
        pnl_c = ok(pnl_s) if is_win else (warn(pnl_s) if "BE" in status else bad(pnl_s))
        dir_c = ok("LONG") if r["direction"] == "LONG" else bad("SHORT")

        tp_s  = dim("")
        if r["tp1_hit"] and r["tp2_hit"]: tp_s = ok("TP1+2")
        elif r["tp1_hit"]:                tp_s = ok("TP1")

        print(
            f"  {r['id']:>3} {r['symbol']:12} {dir_c:5}  "
            f"${r['entry_price']:>9,.4f}  "
            f"${closed:>9,.4f}  "
            f"{pnl_c:>9}  "
            f"{r['signal_score']:>4.1f}  "
            f"{status}  {tp_s}"
        )

    print(f"  {'─'*90}\n")


# ══════════════════════════════════════════════════════════════════════
#  CANDLE ZAMANLAYICI
# ══════════════════════════════════════════════════════════════════════

def seconds_to_next_4h() -> float:
    now    = datetime.now(timezone.utc).timestamp()
    return (int(now // CANDLE_SECONDS) + 1) * CANDLE_SECONDS - now


def wait_for_candle():
    wait = seconds_to_next_4h() + 5
    nxt  = datetime.fromtimestamp(
        datetime.now(timezone.utc).timestamp() + wait, tz=timezone.utc
    )
    logger.info(f"Bir sonraki döngü: {nxt:%H:%M:%S UTC}  ({wait/60:.1f} dakika)")
    while wait > 0:
        chunk = min(wait, 300)
        time.sleep(chunk)
        wait -= chunk
        if wait > 60:
            logger.info(f"Mum kapanışına {wait/60:.0f} dakika kaldı...")


# ══════════════════════════════════════════════════════════════════════
#  ANA DÖNGÜ
# ══════════════════════════════════════════════════════════════════════

def run_cycle() -> dict:
    """Tek bir paper trading döngüsü."""
    balance = get_paper_balance()
    logger.info(f"{'='*55}")
    logger.info(f"KAĞIT DÖNGÜSÜ  {datetime.utcnow():%Y-%m-%d %H:%M UTC}  "
                f"Bakiye=${balance:,.2f}")

    # 1. Açık pozisyonları kontrol et
    balance = check_open_positions(balance)

    # 2. Yeni sinyaller tara
    balance, opened = scan_and_open(balance)

    # 3. Dashboard
    print_paper_dashboard(balance)

    stats = get_paper_stats()
    return {
        "balance": balance,
        "opened":  opened,
        "stats":   stats,
    }


# ══════════════════════════════════════════════════════════════════════
#  GİRİŞ NOKTASI
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Alpha Paper Trader — Gerçek fiyat, simüle para"
    )
    parser.add_argument("--now",     action="store_true", help="Şimdi bir döngü çalıştır")
    parser.add_argument("--report",  action="store_true", help="Detaylı rapor göster ve çık")
    parser.add_argument("--reset",   action="store_true", help="DB'yi sıfırla ve yeniden başla")
    parser.add_argument("--balance", type=float, default=None,
                        help=f"Başlangıç bakiyesi (varsayılan: ${START_BALANCE})")
    args = parser.parse_args()

    start_bal = args.balance or START_BALANCE

    # ── Sıfırla ──────────────────────────────────────────────────
    if args.reset:
        confirm = input(f"Kağıt trade DB sıfırlanacak ({PAPER_DB}). Devam? (evet/hayır): ")
        if confirm.strip().lower() == "evet":
            import os as _os
            if _os.path.exists(PAPER_DB):
                _os.remove(PAPER_DB)
            init_db(start_bal)
            logger.info(f"✅ DB sıfırlandı. Yeni başlangıç: ${start_bal:.2f}")
        else:
            print("İptal edildi.")
        return

    # ── Başlat ───────────────────────────────────────────────────
    init_db(start_bal)

    if args.report:
        print_full_report()
        return

    logger.info("╔══════════════════════════════════════╗")
    logger.info("║  ALPHA PAPER TRADER BAŞLATILDI       ║")
    logger.info("╚══════════════════════════════════════╝")
    logger.info(f"Başlangıç Bakiye : ${get_start_balance():,.2f}")
    logger.info(f"Hedef            : ${get_start_balance() * TARGET_X:,.0f}  ({TARGET_X}x)")
    logger.info(f"Watchlist        : {', '.join(WATCHLIST)}")
    logger.info(f"Min Skor         : {MIN_SCORE:.1f}/10")
    logger.info(f"Risk/İşlem       : {RISK_PCT:.0%}")

    # ── Döngü ────────────────────────────────────────────────────
    loop = 0
    while True:
        loop += 1
        logger.info(f"\nDÖNGÜ #{loop}")
        try:
            run_cycle()
        except KeyboardInterrupt:
            logger.info("Kullanıcı tarafından durduruldu.")
            break
        except Exception as e:
            logger.exception(f"Döngü hatası: {e}")

        if args.now:
            logger.info("--now: tek döngü tamamlandı.")
            break

        wait_for_candle()


if __name__ == "__main__":
    main()
