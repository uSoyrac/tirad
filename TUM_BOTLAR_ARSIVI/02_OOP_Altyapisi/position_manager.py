"""
bot/position_manager.py — Açık pozisyon takibi + SL/TP yönetimi
SQLite'ta açık pozisyonları saklar, TP1 sonrası SL breakeven'a çeker.
"""
import sqlite3
import json
import logging
import os
from datetime import datetime
from typing import Optional, List

logger = logging.getLogger("bot.positions")

DB_PATH = os.getenv("BOT_DB", "data/database/bot_positions.db")


def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_positions_db():
    with _conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol       TEXT NOT NULL,
            direction    TEXT NOT NULL,       -- LONG / SHORT
            entry_price  REAL NOT NULL,
            quantity     REAL NOT NULL,
            sl_price     REAL NOT NULL,
            tp1_price    REAL NOT NULL,
            tp2_price    REAL NOT NULL,
            tp3_price    REAL NOT NULL,
            tp1_qty      REAL NOT NULL,
            tp2_qty      REAL NOT NULL,
            tp3_qty      REAL NOT NULL,
            leverage     INTEGER DEFAULT 3,
            risk_usdt    REAL DEFAULT 0,
            notional     REAL DEFAULT 0,
            signal_score REAL DEFAULT 0,
            tp1_hit      INTEGER DEFAULT 0,   -- 0/1
            tp2_hit      INTEGER DEFAULT 0,
            tp3_hit      INTEGER DEFAULT 0,
            sl_moved_be  INTEGER DEFAULT 0,   -- SL breakeven'a taşındı mı
            status       TEXT DEFAULT 'OPEN', -- OPEN/CLOSED_WIN/CLOSED_LOSS/CLOSED_BE
            pnl_usdt     REAL DEFAULT 0,
            opened_at    TEXT DEFAULT '',
            closed_at    TEXT DEFAULT '',
            notes        TEXT DEFAULT ''
        )""")

        conn.execute("""
        CREATE TABLE IF NOT EXISTS trade_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            pos_id     INTEGER,
            event      TEXT,     -- OPEN/SL_HIT/TP1/TP2/TP3/SL_BE_MOVED/CLOSED
            price      REAL,
            pnl_usdt   REAL DEFAULT 0,
            balance    REAL DEFAULT 0,
            ts         TEXT
        )""")


# ── CRUD ────────────────────────────────────────────────────────

def save_position(pos: dict) -> int:
    with _conn() as conn:
        cur = conn.execute("""
        INSERT INTO positions
        (symbol, direction, entry_price, quantity, sl_price,
         tp1_price, tp2_price, tp3_price, tp1_qty, tp2_qty, tp3_qty,
         leverage, risk_usdt, notional, signal_score, opened_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            pos["symbol"], pos["direction"], pos["entry_price"],
            pos["quantity"], pos["sl_price"],
            pos["tp1_price"], pos["tp2_price"], pos["tp3_price"],
            pos["tp1_qty"],   pos["tp2_qty"],   pos["tp3_qty"],
            pos.get("leverage", 3), pos.get("risk_usdt", 0),
            pos.get("notional", 0), pos.get("signal_score", 0),
            datetime.utcnow().isoformat(),
        ))
        pos_id = cur.lastrowid
        _log_event(conn, pos_id, "OPEN", pos["entry_price"], 0, pos.get("balance", 0))
        logger.info(f"Pozisyon kaydedildi: #{pos_id} {pos['direction']} {pos['symbol']}")
        return pos_id


def get_open_positions() -> List[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM positions WHERE status='OPEN'"
        ).fetchall()
        return [dict(r) for r in rows]


def get_position_by_id(pos_id: int) -> Optional[dict]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM positions WHERE id=?", (pos_id,)).fetchone()
        return dict(row) if row else None


def mark_tp1_hit(pos_id: int, price: float, pnl: float, balance: float):
    with _conn() as conn:
        conn.execute(
            "UPDATE positions SET tp1_hit=1, sl_moved_be=1, sl_price=entry_price WHERE id=?",
            (pos_id,)
        )
        _log_event(conn, pos_id, "TP1_HIT", price, pnl, balance)
    logger.info(f"#{pos_id} TP1 hit @ ${price:.4f}  PnL=${pnl:.2f}  SL → Breakeven")


def mark_tp2_hit(pos_id: int, price: float, pnl: float, balance: float):
    with _conn() as conn:
        conn.execute("UPDATE positions SET tp2_hit=1 WHERE id=?", (pos_id,))
        _log_event(conn, pos_id, "TP2_HIT", price, pnl, balance)
    logger.info(f"#{pos_id} TP2 hit @ ${price:.4f}  PnL=${pnl:.2f}")


def close_position(pos_id: int, price: float, pnl: float, status: str, balance: float):
    with _conn() as conn:
        conn.execute(
            """UPDATE positions SET status=?, pnl_usdt=?, closed_at=?
               WHERE id=?""",
            (status, pnl, datetime.utcnow().isoformat(), pos_id)
        )
        _log_event(conn, pos_id, status, price, pnl, balance)
    logger.info(f"#{pos_id} KAPANDI: {status} @ ${price:.4f}  PnL=${pnl:.2f}")


def update_sl_price(pos_id: int, new_sl: float):
    with _conn() as conn:
        conn.execute("UPDATE positions SET sl_price=?, sl_moved_be=1 WHERE id=?",
                     (new_sl, pos_id))
    logger.info(f"#{pos_id} SL güncellendi: ${new_sl:.4f}")


def _log_event(conn, pos_id, event, price, pnl, balance):
    conn.execute(
        "INSERT INTO trade_log (pos_id, event, price, pnl_usdt, balance, ts) VALUES (?,?,?,?,?,?)",
        (pos_id, event, price, pnl, balance, datetime.utcnow().isoformat())
    )


# ── İSTATİSTİK ──────────────────────────────────────────────────

def get_stats() -> dict:
    with _conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM positions WHERE status != 'OPEN'"
        ).fetchone()[0]
        wins = conn.execute(
            "SELECT COUNT(*) FROM positions WHERE status LIKE '%WIN%'"
        ).fetchone()[0]
        total_pnl = conn.execute(
            "SELECT COALESCE(SUM(pnl_usdt),0) FROM positions WHERE status != 'OPEN'"
        ).fetchone()[0]
        avg_pnl = conn.execute(
            "SELECT COALESCE(AVG(pnl_usdt),0) FROM positions WHERE status != 'OPEN'"
        ).fetchone()[0]
        best = conn.execute(
            "SELECT MAX(pnl_usdt) FROM positions"
        ).fetchone()[0] or 0
        worst = conn.execute(
            "SELECT MIN(pnl_usdt) FROM positions"
        ).fetchone()[0] or 0
        open_cnt = conn.execute(
            "SELECT COUNT(*) FROM positions WHERE status='OPEN'"
        ).fetchone()[0]

    return {
        "total_trades":   total,
        "winning_trades": wins,
        "losing_trades":  total - wins,
        "win_rate":       wins / total if total > 0 else 0,
        "total_pnl":      total_pnl,
        "avg_pnl":        avg_pnl,
        "best_trade":     best,
        "worst_trade":    worst,
        "open_positions": open_cnt,
    }
