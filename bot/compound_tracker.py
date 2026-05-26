"""
bot/compound_tracker.py — Bileşik büyüme takibi + hedef hesabı
$100 → $100,000 yolculuğunu her işlem sonrası günceller.
"""
import sqlite3
import math
import os
import logging
from datetime import datetime

logger = logging.getLogger("bot.compound")

DB_PATH = os.getenv("BOT_DB", "data/database/bot_positions.db")

# ─── Hedef ───────────────────────────────────────────────────
TARGET_X = 1000   # 1000x büyüme hedefi ($100 → $100,000)


def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_compound_db(start_balance: float):
    with _conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS equity_curve (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            balance    REAL NOT NULL,
            pnl_usdt   REAL DEFAULT 0,
            trade_num  INTEGER DEFAULT 0,
            event      TEXT DEFAULT '',
            symbol     TEXT DEFAULT '',
            ts         TEXT DEFAULT ''
        )""")
        # Sadece tablo boşsa başlangıç kaydı ekle
        existing = conn.execute("SELECT COUNT(*) FROM equity_curve").fetchone()[0]
        if existing == 0:
            conn.execute(
                "INSERT INTO equity_curve (balance, event, ts) VALUES (?, 'START', ?)",
                (start_balance, datetime.utcnow().isoformat())
            )


def record_trade(balance: float, pnl_usdt: float, symbol: str, event: str = "TRADE"):
    with _conn() as conn:
        trade_num = conn.execute("SELECT COUNT(*) FROM equity_curve").fetchone()[0]
        conn.execute(
            """INSERT INTO equity_curve (balance, pnl_usdt, trade_num, event, symbol, ts)
               VALUES (?,?,?,?,?,?)""",
            (balance, pnl_usdt, trade_num,
             event, symbol, datetime.utcnow().isoformat())
        )


def get_equity_curve() -> list:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM equity_curve ORDER BY id"
        ).fetchall()
        return [dict(zip([c[0] for c in conn.execute("SELECT * FROM equity_curve LIMIT 0").description], r))
                for r in rows] if rows else []


def get_start_balance() -> float:
    with _conn() as conn:
        row = conn.execute(
            "SELECT balance FROM equity_curve ORDER BY id LIMIT 1"
        ).fetchone()
        return float(row[0]) if row else 0.0


def get_current_balance_from_curve() -> float:
    with _conn() as conn:
        row = conn.execute(
            "SELECT balance FROM equity_curve ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return float(row[0]) if row else 0.0


def compound_status(current_balance: float) -> dict:
    """
    Mevcut bakiyeye göre hedefe ne kadar kaldı hesaplar.
    """
    start = get_start_balance() or current_balance
    x_gained = current_balance / start if start > 0 else 1
    x_remaining = TARGET_X / x_gained if x_gained > 0 else TARGET_X
    target_balance = start * TARGET_X

    # Kaç işlem kaldı? (ortalama parametrelerle)
    wr = 0.58; rr = 2.5; r = 0.02
    g = ((1 + rr * r) ** wr) * ((1 - r) ** (1 - wr))
    log_g = math.log(g) if g > 1 else 1e-10
    trades_left = math.ceil(math.log(x_remaining) / log_g) if x_remaining > 1 else 0

    curve = get_equity_curve()
    trade_count = len([e for e in curve if e.get("event") == "TRADE"])

    return {
        "start_balance":    start,
        "current_balance":  current_balance,
        "target_balance":   target_balance,
        "x_gained":         x_gained,
        "x_remaining":      x_remaining,
        "progress_pct":     math.log(x_gained) / math.log(TARGET_X) * 100 if x_gained > 1 else 0,
        "trades_done":      trade_count,
        "est_trades_left":  trades_left,
        "total_pnl":        current_balance - start,
        "total_return_pct": (x_gained - 1) * 100,
    }


def print_compound_dashboard(current_balance: float):
    """Terminal'e bileşik büyüme dashboard'u yazar."""
    try:
        from live_scan import ok, bad, warn, dim, nfo, B, R, CY, GR, YL, DM
    except ImportError:
        def ok(s): return s
        def bad(s): return s
        def warn(s): return s
        def dim(s): return s
        def nfo(s): return s
        B=R=CY=GR=YL=DM=""

    st = compound_status(current_balance)
    start = st["start_balance"]
    x = st["x_gained"]
    prog = st["progress_pct"]

    # Log-scale progress bar (40 chars)
    BAR = 40
    filled = max(1, int(prog / 100 * BAR))
    bar_col = GR if prog > 50 else (YL if prog > 20 else CY)
    bar = bar_col + "█" * filled + DM + "░" * (BAR - filled) + R

    print(f"\n  {'═'*60}")
    print(f"  {B}  BİLEŞİK BÜYÜME HEDEFİ: ${start:.0f} → ${st['target_balance']:,.0f} ({TARGET_X}x){R}")
    print(f"  {'═'*60}")
    print(f"  {bar}  {prog:.1f}%")
    print()
    print(f"  Mevcut Bakiye  : {ok(f'${current_balance:,.2f}')}")
    pnl_s = f"+${st['total_pnl']:+,.2f}" if st["total_pnl"] >= 0 else f"${st['total_pnl']:,.2f}"
    pnl_c = ok(pnl_s) if st["total_pnl"] >= 0 else bad(pnl_s)
    print(f"  Kazanılan      : {ok(f'{x:.2f}x')}  {pnl_c}")
    xrem_s  = f"{st['x_remaining']:.1f}x"
    tbal_s  = f"${st['target_balance']:,.0f}"
    trem_s  = f"{st['est_trades_left']} islem"
    print(f"  Kalan Hedef    : {warn(xrem_s)}  ({tbal_s} icin)")
    print(f"  Tamamlanan İş. : {nfo(str(st['trades_done']))}")
    print(f"  Tahmini Kalan  : {nfo(trem_s)}  "
          f"{dim('(WR=%58, RR=2.5, risk=%2 varsayimi)')}")

    # Kilometre taşları
    milestones = [(10, "$1K"), (100, "$10K"), (1000, "$100K"), (10000, "$1M")]
    print(f"\n  {'─'*40}")
    print(f"  {B}{CY}Kilometre Taşları:{R}")
    for mult, label in milestones:
        target = start * mult
        done = current_balance >= target
        trades_to = max(0, math.ceil(math.log(mult / x) / math.log(
            ((1 + 2.5*0.02)**0.58) * ((1-0.02)**0.42)
        ))) if x < mult else 0
        icon = ok("✅") if done else dim("○")
        dist = ok(f"${current_balance:,.0f} → ULAŞILDI") if done else \
               nfo(f"~{trades_to} işlem kaldı")
        print(f"  {icon} {label:8}  ${target:>12,.0f}    {dist}")

    print(f"  {'═'*60}\n")
