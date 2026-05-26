"""
bot/portfolio.py — 4-5 varlıklı portfolio koordinatörü
Her 4H mum kapanışında çalışır: tarar → sinyal varsa emir açar → açık pozisyonları yönetir.
"""
import logging
import time
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger("bot.portfolio")

# ─── İzleme listesi (her zaman taranır) ─────────────────────
DEFAULT_WATCHLIST = [
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "BNB/USDT",
    "AVAX/USDT",
]

# ─── Max eş zamanlı açık pozisyon ───────────────────────────
MAX_POSITIONS = 4
MIN_SCORE     = 6.0   # Sinyal için minimum skor


def run_portfolio_cycle(
    watchlist: Optional[List[str]] = None,
    notify_fn=None,   # email gönderme fonksiyonu
) -> dict:
    """
    Tek portfolio döngüsü:
    1. Sosyal tarama (hızlı)
    2. Her sembol için SMC analizi
    3. Sinyal varsa + pozisyon yoksa → emir aç
    4. Açık pozisyonları kontrol et (SL/TP takibi)
    5. Bileşik tracker güncelle
    """
    from bot.executor       import get_balance, get_all_positions
    from bot.risk_manager   import calculate_position, MAX_POSITIONS as MP
    from bot.position_manager import (
        get_open_positions, save_position, close_position,
        mark_tp1_hit, mark_tp2_hit, update_sl_price, init_positions_db
    )
    from bot.compound_tracker import (
        init_compound_db, record_trade, print_compound_dashboard
    )
    from live_scan import (
        ohlcv, analyze, head, h2, sep, ok, bad, warn, nfo, dim, B, R, CY
    )

    # ── Init ─────────────────────────────────────────────────
    init_positions_db()
    balance = get_balance()
    init_compound_db(balance)

    if watchlist is None:
        watchlist = DEFAULT_WATCHLIST

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    head(f"PORTFOLIO DÖNGÜSÜ  {timestamp}")
    print(f"  Bakiye: {ok(f'${balance:,.2f}')}  |  Watchlist: {len(watchlist)} sembol")

    # ── Açık pozisyon sayısı ──────────────────────────────────
    open_pos = get_open_positions()
    open_symbols = {p["symbol"] for p in open_pos}
    print(f"  Açık Pozisyon: {nfo(str(len(open_pos)))}/{MAX_POSITIONS}")

    # ── Açık pozisyon SL/TP takibi ───────────────────────────
    if open_pos:
        h2("AÇIK POZİSYON TAKİBİ")
        _check_open_positions(open_pos, balance)

    # ── Sinyal tarama ─────────────────────────────────────────
    if len(open_pos) >= MAX_POSITIONS:
        print(f"\n  {warn('Max pozisyon sınırına ulaşıldı — yeni sinyal aranmıyor')}")
        _print_status_summary(balance)
        return {"status": "MAX_POSITIONS", "balance": balance}

    h2("SİNYAL TARAMA")
    print()
    signals = []

    for symbol in watchlist:
        if symbol in open_symbols:
            print(f"  {symbol:14} {dim('zaten açık — atlanıyor')}")
            continue

        sys_import = __import__("sys")
        sys_import.stdout.write(f"  {symbol:14} ... ")
        sys_import.stdout.flush()

        try:
            df = ohlcv(symbol, "4h", 350)
            if df.empty or len(df) < 100:
                print(dim("veri yok"))
                continue

            r = analyze(symbol, is_bist=False)
            if not r:
                print(dim("analiz başarısız"))
                continue

            score = r["composite"]
            trend = r["trend"]
            color = ok if score >= 7 else (warn if score >= MIN_SCORE else dim)
            print(f"{color(f'{score:.1f}/10')}  {trend}")

            if score >= MIN_SCORE and trend in ("BULLISH", "BEARISH"):
                if r.get("entry_low") and r.get("sl"):
                    signals.append(r)

        except Exception as e:
            print(dim(f"hata: {e}"))
            logger.exception(f"Tarama hatası {symbol}")

        time.sleep(0.3)

    # ── Sinyal sıralama + emir gönderme ───────────────────────
    signals.sort(key=lambda x: x["composite"], reverse=True)
    opened = 0

    if signals:
        h2("AÇILAN POZİSYONLAR")
        for sig in signals:
            if len(open_pos) + opened >= MAX_POSITIONS:
                break

            pos_data = _try_open_position(sig, balance, len(open_pos) + opened)
            if pos_data:
                opened += 1
                record_trade(balance, 0, sig["symbol"], "OPEN")
                if notify_fn:
                    try:
                        notify_fn(sig, pos_data)
                    except Exception:
                        pass
    else:
        print(f"\n  {dim('Eşik üstünde sinyal yok — bekleniyor.')}")

    # ── Dashboard ─────────────────────────────────────────────
    print_compound_dashboard(balance)
    _print_status_summary(balance)

    return {
        "status":      "OK",
        "balance":     balance,
        "signals":     len(signals),
        "opened":      opened,
        "open_count":  len(open_pos) + opened,
        "timestamp":   timestamp,
    }


def _try_open_position(sig: dict, balance: float, open_count: int) -> Optional[dict]:
    """Sinyal için pozisyon açmayı dener."""
    from bot.executor       import open_position, set_stop_loss, set_take_profit
    from bot.risk_manager   import calculate_position
    from bot.position_manager import save_position
    from live_scan import ok, bad, warn, nfo, dim, B, R

    symbol    = sig["symbol"]
    entry     = (sig["entry_low"] + sig["entry_high"]) / 2
    sl_price  = sig["sl"]
    direction = sig["trend"]
    score     = sig["composite"]

    pos_calc = calculate_position(
        balance=balance,
        entry_price=entry,
        sl_price=sl_price,
        signal_score=score,
        open_count=open_count,
    )

    if not pos_calc["valid"]:
        print(f"  {bad('✗')} {symbol}: {pos_calc['reason']}")
        return None

    side = "buy" if direction == "BULLISH" else "sell"

    print(f"\n  {ok('→')} {B}{symbol}{R}  {ok('LONG') if direction=='BULLISH' else bad('SHORT')}")
    print(f"     Skor={score:.1f}  Entry=${entry:,.4f}  SL=${sl_price:,.4f}")
    print(f"     Lev={pos_calc['leverage']}x  Notional=${pos_calc['notional']:,.2f}"
          f"  Risk=${pos_calc['risk_usdt']:.2f}")

    # Emir gönder
    order = open_position(symbol, side, pos_calc["quantity"], pos_calc["leverage"])
    if not order:
        print(f"  {bad('✗')} Emir gönderilemedi: {symbol}")
        return None

    # SL
    set_stop_loss(symbol, side, sl_price, pos_calc["quantity"])

    # TP1 + TP2 + TP3
    set_take_profit(symbol, side, pos_calc["tp1_price"], pos_calc["tp1_qty"], "TP1")
    set_take_profit(symbol, side, pos_calc["tp2_price"], pos_calc["tp2_qty"], "TP2")
    set_take_profit(symbol, side, pos_calc["tp3_price"], pos_calc["tp3_qty"], "TP3")

    # DB'ye kaydet
    pos_id = save_position({
        "symbol":       symbol,
        "direction":    direction,
        "entry_price":  entry,
        "quantity":     pos_calc["quantity"],
        "sl_price":     sl_price,
        "tp1_price":    pos_calc["tp1_price"],
        "tp2_price":    pos_calc["tp2_price"],
        "tp3_price":    pos_calc["tp3_price"],
        "tp1_qty":      pos_calc["tp1_qty"],
        "tp2_qty":      pos_calc["tp2_qty"],
        "tp3_qty":      pos_calc["tp3_qty"],
        "leverage":     pos_calc["leverage"],
        "risk_usdt":    pos_calc["risk_usdt"],
        "notional":     pos_calc["notional"],
        "signal_score": score,
        "balance":      balance,
    })

    print(f"  {ok('✅')} Pozisyon #{pos_id} açıldı")
    return {**pos_calc, "pos_id": pos_id, "symbol": symbol}


def _check_open_positions(open_pos: list, balance: float):
    """
    Açık pozisyonlardaki fiyatı kontrol et.
    TP1 vurduysa → SL breakeven'a çek.
    Pozisyon kapandıysa → DB güncelle.
    """
    from bot.executor import get_position, cancel_all_orders, set_stop_loss, get_current_price
    from bot.position_manager import mark_tp1_hit, mark_tp2_hit, close_position, update_sl_price
    from bot.compound_tracker import record_trade
    from live_scan import ok, bad, warn, nfo, dim, B, R

    for p in open_pos:
        symbol    = p["symbol"]
        direction = p["direction"]
        entry     = p["entry_price"]
        sl        = p["sl_price"]
        tp1       = p["tp1_price"]
        tp2       = p["tp2_price"]
        pos_id    = p["id"]

        # Gerçek exchange'den pozisyon sorgula
        live_pos = get_position(symbol)
        price    = get_current_price(symbol)

        if not live_pos or live_pos["size"] == 0:
            # Pozisyon kapanmış (SL veya TP)
            if direction == "LONG":
                pnl = (price - entry) / entry * p["notional"]
                status = "CLOSED_WIN" if price >= tp1 else "CLOSED_LOSS"
            else:
                pnl = (entry - price) / entry * p["notional"]
                status = "CLOSED_WIN" if price <= tp1 else "CLOSED_LOSS"

            pnl_icon = ok(f"+${pnl:,.2f}") if pnl > 0 else bad(f"${pnl:,.2f}")
            print(f"  {symbol:14} KAPANDI  {pnl_icon}  [{status}]")
            close_position(pos_id, price, pnl, status, balance)
            record_trade(balance + pnl, pnl, symbol, status)
            continue

        # Pozisyon hâlâ açık — TP1 kontrolü (manuel)
        if not p["tp1_hit"]:
            if (direction == "LONG"  and price >= tp1) or \
               (direction == "SHORT" and price <= tp1):
                tp1_pnl = abs(tp1 - entry) / entry * p["notional"] * 0.40
                mark_tp1_hit(pos_id, price, tp1_pnl, balance)
                # SL → breakeven
                cancel_all_orders(symbol)
                side = "buy" if direction == "LONG" else "sell"
                set_stop_loss(symbol, side, entry, live_pos["size"])
                print(f"  {ok('✅')} {symbol} TP1 HIT @ ${price:,.4f}  SL → Breakeven ${entry:,.4f}")

        pnl_live = live_pos["pnl"]
        pnl_c = ok(f"+${pnl_live:,.2f}") if pnl_live >= 0 else bad(f"${pnl_live:,.2f}")
        print(f"  {symbol:14} AÇIK  @ ${price:,.4f}  PnL: {pnl_c}")


def _print_status_summary(balance: float):
    from bot.position_manager import get_stats
    from live_scan import ok, bad, warn, dim, B, R, CY

    st = get_stats()
    if st["total_trades"] == 0:
        return
    wrc = ok if st["win_rate"] >= 0.52 else (warn if st["win_rate"] >= 0.45 else bad)
    print(f"\n  {'─'*52}")
    print(f"  {B}Toplam Performans:{R}")
    wr_s   = f"{st['win_rate']:.1%}"
    pnl_s2 = f"+${st['total_pnl']:+,.2f}" if st["total_pnl"] >= 0 else f"${st['total_pnl']:,.2f}"
    pnl_c2 = ok(pnl_s2) if st["total_pnl"] >= 0 else bad(pnl_s2)
    print(f"  İşlem: {st['total_trades']}  WR: {wrc(wr_s)}  Net P&L: {pnl_c2}")
