"""
bot/executor.py — Binance Futures emir motoru
Gerçek emir gönderir: LONG/SHORT açma, SL/TP ayarı, pozisyon kapatma.
DRY_RUN=True iken sadece loglar, gerçek emir göndermez.
"""
import os
import math
import logging
import time
from typing import Optional

import ccxt

logger = logging.getLogger("bot.executor")

# ──────────────────────────────────────────────────────────────
DRY_RUN = os.getenv("BOT_DRY_RUN", "true").lower() == "true"
# ──────────────────────────────────────────────────────────────


def _exchange():
    """Binance Futures (USDT-M) bağlantısı."""
    return ccxt.binance({
        "apiKey":  os.getenv("BINANCE_API_KEY", ""),
        "secret":  os.getenv("BINANCE_SECRET_KEY", ""),
        "enableRateLimit": True,
        "options": {
            "defaultType":       "future",
            "adjustForTimeDifference": True,
        },
    })


_ex = None

def ex():
    global _ex
    if _ex is None:
        _ex = _exchange()
    return _ex


# ══════════════════════════════════════════════════════════════
#  BAKİYE & POZİSYON
# ══════════════════════════════════════════════════════════════

def get_balance() -> float:
    """USDT cüzdan bakiyesi (futures available balance)."""
    try:
        bal = ex().fetch_balance({"type": "future"})
        return float(bal["USDT"]["free"])
    except Exception as e:
        logger.error(f"Bakiye alınamadı: {e}")
        return 0.0


def get_position(symbol: str) -> Optional[dict]:
    """
    Açık pozisyon bilgisi.
    Dönüş: {"size": float, "side": "long"/"short", "entry": float, "pnl": float}
    veya None (pozisyon yok).
    """
    try:
        positions = ex().fetch_positions([symbol])
        for p in positions:
            size = float(p.get("contracts", 0) or 0)
            if size != 0:
                return {
                    "symbol":    p["symbol"],
                    "side":      p["side"],          # "long" / "short"
                    "size":      abs(size),
                    "entry":     float(p.get("entryPrice", 0) or 0),
                    "pnl":       float(p.get("unrealizedPnl", 0) or 0),
                    "notional":  float(p.get("notional", 0) or 0),
                    "leverage":  int(p.get("leverage", 1) or 1),
                    "liq_price": float(p.get("liquidationPrice", 0) or 0),
                }
        return None
    except Exception as e:
        logger.error(f"Pozisyon alınamadı ({symbol}): {e}")
        return None


def get_all_positions() -> list:
    """Tüm açık pozisyonlar."""
    try:
        positions = ex().fetch_positions()
        return [p for p in positions
                if float(p.get("contracts", 0) or 0) != 0]
    except Exception as e:
        logger.error(f"Tüm pozisyonlar alınamadı: {e}")
        return []


# ══════════════════════════════════════════════════════════════
#  KALDIRAÇ & MİNİMUM BOYUT
# ══════════════════════════════════════════════════════════════

def set_leverage(symbol: str, leverage: int) -> bool:
    try:
        if DRY_RUN:
            logger.info(f"[DRY] Kaldıraç ayarlandı: {symbol} {leverage}x")
            return True
        ex().set_leverage(leverage, symbol)
        logger.info(f"Kaldıraç: {symbol} {leverage}x")
        return True
    except Exception as e:
        logger.warning(f"Kaldıraç ayarlanamadı ({symbol}): {e}")
        return False


def get_min_qty(symbol: str) -> float:
    """Binance minimum lot büyüklüğü."""
    try:
        markets = ex().load_markets()
        mkt = markets.get(symbol, {})
        limits = mkt.get("limits", {}).get("amount", {})
        return float(limits.get("min", 0.001))
    except Exception:
        return 0.001


def round_qty(symbol: str, qty: float) -> float:
    """Miktarı Binance precision'a yuvarla."""
    try:
        markets = ex().load_markets()
        mkt = markets.get(symbol, {})
        precision = mkt.get("precision", {}).get("amount", 3)
        factor = 10 ** precision
        return math.floor(qty * factor) / factor
    except Exception:
        return round(qty, 3)


# ══════════════════════════════════════════════════════════════
#  MARKET EMRİ (AÇMA)
# ══════════════════════════════════════════════════════════════

def open_position(
    symbol:   str,
    side:     str,    # "buy" (LONG) / "sell" (SHORT)
    quantity: float,  # coin cinsinden
    leverage: int = 3,
) -> Optional[dict]:
    """
    Piyasa fiyatından pozisyon açar.
    Önce kaldıracı ayarlar, sonra MARKET emri gönderir.
    """
    set_leverage(symbol, leverage)
    qty = round_qty(symbol, quantity)
    min_qty = get_min_qty(symbol)
    if qty < min_qty:
        logger.warning(f"Miktar çok küçük: {qty} < {min_qty} ({symbol})")
        return None

    if DRY_RUN:
        price = _last_price(symbol)
        logger.info(
            f"[DRY] AÇILIYOR: {side.upper()} {symbol}  "
            f"qty={qty}  ~${qty*price:,.2f}  lev={leverage}x"
        )
        return {"id": "DRY_RUN", "side": side, "amount": qty,
                "price": price, "symbol": symbol}

    try:
        order = ex().create_market_order(
            symbol, side, qty,
            params={"positionSide": "LONG" if side == "buy" else "SHORT"}
        )
        logger.info(
            f"✅ POZİSYON AÇILDI: {side.upper()} {symbol} "
            f"qty={qty} @ ~${order.get('average', 0):,.4f}"
        )
        return order
    except Exception as e:
        logger.error(f"❌ Emir gönderilemedi ({symbol}): {e}")
        return None


# ══════════════════════════════════════════════════════════════
#  STOP LOSS & TAKE PROFIT (Native Binance)
# ══════════════════════════════════════════════════════════════

def set_stop_loss(
    symbol:      str,
    side:        str,   # Pozisyon yönü: "buy" (long) / "sell" (short)
    sl_price:    float,
    quantity:    float,
) -> Optional[dict]:
    """
    STOP_MARKET emri — native Binance SL.
    Long pozisyon için sell STOP_MARKET, Short için buy STOP_MARKET.
    """
    close_side = "sell" if side == "buy" else "buy"
    pos_side   = "LONG" if side == "buy" else "SHORT"
    qty = round_qty(symbol, quantity)

    if DRY_RUN:
        logger.info(f"[DRY] SL AYARLANDI: {symbol}  fiyat=${sl_price:,.4f}  qty={qty}")
        return {"id": "DRY_SL", "stopPrice": sl_price}

    try:
        order = ex().create_order(
            symbol, "STOP_MARKET", close_side, qty,
            params={
                "stopPrice":    sl_price,
                "closePosition": False,
                "positionSide": pos_side,
                "workingType":  "CONTRACT_PRICE",
                "timeInForce":  "GTC",
            }
        )
        logger.info(f"✅ SL AYARLANDI: {symbol} @ ${sl_price:,.4f}")
        return order
    except Exception as e:
        logger.error(f"❌ SL ayarlanamadı ({symbol}): {e}")
        return None


def set_take_profit(
    symbol:   str,
    side:     str,     # Pozisyon yönü
    tp_price: float,
    quantity: float,
    label:    str = "TP",
) -> Optional[dict]:
    """TAKE_PROFIT_MARKET emri."""
    close_side = "sell" if side == "buy" else "buy"
    pos_side   = "LONG" if side == "buy" else "SHORT"
    qty = round_qty(symbol, quantity)

    if DRY_RUN:
        logger.info(f"[DRY] {label} AYARLANDI: {symbol}  fiyat=${tp_price:,.4f}  qty={qty}")
        return {"id": f"DRY_{label}", "stopPrice": tp_price}

    try:
        order = ex().create_order(
            symbol, "TAKE_PROFIT_MARKET", close_side, qty,
            params={
                "stopPrice":    tp_price,
                "closePosition": False,
                "positionSide": pos_side,
                "workingType":  "CONTRACT_PRICE",
                "timeInForce":  "GTC",
            }
        )
        logger.info(f"✅ {label} AYARLANDI: {symbol} @ ${tp_price:,.4f}  qty={qty}")
        return order
    except Exception as e:
        logger.error(f"❌ {label} ayarlanamadı ({symbol}): {e}")
        return None


def cancel_all_orders(symbol: str):
    """Semboldeki tüm açık emirleri iptal eder (SL/TP güncellerken)."""
    if DRY_RUN:
        logger.info(f"[DRY] Tüm emirler iptal: {symbol}")
        return
    try:
        ex().cancel_all_orders(symbol)
        logger.info(f"Emirler iptal: {symbol}")
    except Exception as e:
        logger.warning(f"Emir iptal hatası ({symbol}): {e}")


def close_position_market(symbol: str, side: str, quantity: float) -> bool:
    """Market fiyatından pozisyonu tamamen kapat."""
    close_side = "sell" if side == "buy" else "buy"
    pos_side   = "LONG" if side == "buy" else "SHORT"
    qty = round_qty(symbol, quantity)

    if DRY_RUN:
        price = _last_price(symbol)
        logger.info(f"[DRY] POZİSYON KAPATILDI: {symbol}  @ ~${price:,.4f}")
        return True

    try:
        ex().create_market_order(
            symbol, close_side, qty,
            params={"positionSide": pos_side, "reduceOnly": True}
        )
        logger.info(f"✅ Pozisyon kapatıldı: {symbol}")
        return True
    except Exception as e:
        logger.error(f"❌ Pozisyon kapatılamadı ({symbol}): {e}")
        return False


# ══════════════════════════════════════════════════════════════
#  YARDIMCI
# ══════════════════════════════════════════════════════════════

def _last_price(symbol: str) -> float:
    try:
        ticker = ex().fetch_ticker(symbol)
        return float(ticker["last"])
    except Exception:
        return 0.0


def get_current_price(symbol: str) -> float:
    return _last_price(symbol)
