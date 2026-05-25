import sqlite3
import json
from datetime import datetime
from pathlib import Path


DB_PATH = Path(__file__).parent / "alpha.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            symbol TEXT NOT NULL,
            asset_type TEXT NOT NULL,  -- 'crypto' or 'bist'
            direction TEXT,            -- 'LONG', 'SHORT', 'NEUTRAL'
            composite_score REAL,
            smc_score REAL,
            classic_score REAL,
            institutional_score REAL,
            mtf_score REAL,
            social_score REAL,
            entry_low REAL,
            entry_high REAL,
            stop_loss REAL,
            tp1 REAL,
            tp2 REAL,
            tp3 REAL,
            leverage REAL,
            raw_data TEXT
        );

        CREATE TABLE IF NOT EXISTS social_mentions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            symbol TEXT NOT NULL,
            source TEXT,
            language TEXT,
            sentiment REAL,
            mention_count INTEGER,
            raw_text TEXT
        );

        CREATE TABLE IF NOT EXISTS market_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL, volume REAL,
            funding_rate REAL,
            open_interest REAL
        );

        CREATE TABLE IF NOT EXISTS backtest_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT,
            start_date TEXT,
            end_date TEXT,
            win_rate REAL,
            profit_factor REAL,
            max_drawdown REAL,
            sharpe_ratio REAL,
            total_trades INTEGER,
            params TEXT
        );
    """)
    conn.commit()
    conn.close()


def save_signal(signal: dict):
    conn = get_conn()
    conn.execute("""
        INSERT INTO signals (
            timestamp, symbol, asset_type, direction,
            composite_score, smc_score, classic_score, institutional_score,
            mtf_score, social_score, entry_low, entry_high,
            stop_loss, tp1, tp2, tp3, leverage, raw_data
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.utcnow().isoformat(), signal.get("symbol"), signal.get("asset_type"),
        signal.get("direction"), signal.get("composite_score"), signal.get("smc_score"),
        signal.get("classic_score"), signal.get("institutional_score"), signal.get("mtf_score"),
        signal.get("social_score"), signal.get("entry_low"), signal.get("entry_high"),
        signal.get("stop_loss"), signal.get("tp1"), signal.get("tp2"), signal.get("tp3"),
        signal.get("leverage"), json.dumps(signal)
    ))
    conn.commit()
    conn.close()


def get_recent_signals(limit: int = 20) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM signals ORDER BY timestamp DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_social_mention(data: dict):
    conn = get_conn()
    conn.execute("""
        INSERT INTO social_mentions (timestamp, symbol, source, language, sentiment, mention_count, raw_text)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.utcnow().isoformat(), data["symbol"], data.get("source"),
        data.get("language"), data.get("sentiment", 0), data.get("mention_count", 1),
        data.get("raw_text", "")[:2000]
    ))
    conn.commit()
    conn.close()
