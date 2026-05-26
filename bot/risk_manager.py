"""
bot/risk_manager.py — Dinamik pozisyon boyutlandırma + bileşik büyüme
%2 sabit risk + kaldıraç hesabı + minimum notional kontrolü.
"""
import math
import logging

logger = logging.getLogger("bot.risk")

# ─── Sabit parametreler ───────────────────────────────────────
RISK_PCT      = 0.02    # İşlem başına %2 risk
MAX_LEVERAGE  = 5       # Max kaldıraç
MIN_NOTIONAL  = 10.0    # Binance minimum notional (USDT)
MAX_POSITIONS = 4       # Aynı anda max açık pozisyon
TP1_PCT       = 0.06    # TP1 hedefi (+%6 long, -%6 short)
TP2_PCT       = 0.14    # TP2 hedefi
TP3_PCT       = 0.28    # TP3 hedefi
TP1_CLOSE     = 0.40    # TP1'de pozisyonun %40'ını kapat
TP2_CLOSE     = 0.35
TP3_CLOSE     = 0.25    # Kalan hepsini kapat


def calculate_position(
    balance:      float,   # Mevcut USDT bakiyesi
    entry_price:  float,   # Giriş fiyatı
    sl_price:     float,   # Stop-loss fiyatı
    signal_score: float,   # Composite sinyal skoru (0-10)
    open_count:   int = 0, # Mevcut açık pozisyon sayısı
) -> dict:
    """
    Optimal pozisyon boyutu hesaplar.

    Döner: {
        "valid":      bool,       # İşlem geçerli mi?
        "reason":     str,        # Geçersizse neden
        "risk_usdt":  float,      # Riske giren USDT
        "sl_pct":     float,      # SL mesafesi %
        "leverage":   int,        # Kullanılacak kaldıraç
        "notional":   float,      # Toplam pozisyon USDT değeri
        "quantity":   float,      # Coin miktarı
        "tp1_price":  float,
        "tp2_price":  float,
        "tp3_price":  float,
        "tp1_qty":    float,
        "tp2_qty":    float,
        "tp3_qty":    float,
        "direction":  str,        # "LONG" / "SHORT"
    }
    """
    if balance <= 0 or entry_price <= 0 or sl_price <= 0:
        return {"valid": False, "reason": "Geçersiz fiyat/bakiye"}

    if open_count >= MAX_POSITIONS:
        return {"valid": False, "reason": f"Max {MAX_POSITIONS} pozisyon sınırı aşıldı"}

    direction = "LONG" if entry_price > sl_price else "SHORT"

    # ── SL mesafesi ───────────────────────────────────────────
    sl_dist = abs(entry_price - sl_price) / entry_price
    if sl_dist <= 0.001:
        return {"valid": False, "reason": "SL çok yakın (<0.1%)"}
    if sl_dist > 0.08:
        return {"valid": False, "reason": f"SL çok uzak ({sl_dist:.1%} > %8)"}

    # ── Risk USDT ─────────────────────────────────────────────
    # Açık pozisyon sayısına göre risk biraz azalt
    adj_risk = RISK_PCT * (1 - open_count * 0.002)   # 0.2% azalma per pozisyon
    risk_usdt = balance * max(adj_risk, 0.01)

    # ── Kaldıraç hesabı ───────────────────────────────────────
    # Pozisyon notional = risk / sl_dist
    # Leverage = notional / balance (margin)
    notional_needed = risk_usdt / sl_dist
    leverage = math.ceil(notional_needed / balance)
    leverage = max(1, min(leverage, MAX_LEVERAGE))

    # Gerçek notional (kaldıraçla)
    notional = balance * leverage
    if notional > notional_needed * 1.5:
        # Kaldıraç çok yüksek çıktıysa küçült
        notional = notional_needed
        leverage = max(1, math.ceil(notional / balance))

    # Skor tabanlı kaldıraç tavanı
    if signal_score >= 8.0:   max_lev = 5
    elif signal_score >= 6.5: max_lev = 4
    elif signal_score >= 5.5: max_lev = 3
    else:                     max_lev = 2
    leverage = min(leverage, max_lev, MAX_LEVERAGE)

    notional = balance * leverage

    # ── Minimum notional kontrolü ─────────────────────────────
    if notional < MIN_NOTIONAL:
        return {
            "valid":   False,
            "reason":  f"Bakiye çok düşük: notional ${notional:.2f} < ${MIN_NOTIONAL} minimum",
        }

    # ── Coin miktarı ─────────────────────────────────────────
    quantity = notional / entry_price

    # ── TP fiyatları ─────────────────────────────────────────
    if direction == "LONG":
        tp1 = entry_price * (1 + TP1_PCT)
        tp2 = entry_price * (1 + TP2_PCT)
        tp3 = entry_price * (1 + TP3_PCT)
    else:
        tp1 = entry_price * (1 - TP1_PCT)
        tp2 = entry_price * (1 - TP2_PCT)
        tp3 = entry_price * (1 - TP3_PCT)

    # TP miktarları
    tp1_qty = quantity * TP1_CLOSE
    tp2_qty = quantity * TP2_CLOSE
    tp3_qty = quantity * TP3_CLOSE

    # ── Expected value (Kelly check) ──────────────────────────
    blended_rr = TP1_CLOSE * (TP1_PCT / sl_dist) + TP2_CLOSE * (TP2_PCT / sl_dist)
    # Win rate tahmini (skor bazlı)
    est_wr = 0.45 + (signal_score - 4.0) / 6.0 * 0.20   # 4→0.45, 10→0.65
    est_wr = max(0.40, min(0.70, est_wr))
    ev = est_wr * blended_rr - (1 - est_wr)
    if ev < -0.05:   # Negatif expected value
        return {"valid": False, "reason": f"Negatif beklenen değer: EV={ev:.2f}"}

    logger.info(
        f"Pozisyon hesaplandı: {direction} {entry_price:.4f}  "
        f"SL={sl_price:.4f} ({sl_dist:.1%})  "
        f"Lev={leverage}x  Notional=${notional:.2f}  "
        f"Risk=${risk_usdt:.2f}  EW={est_wr:.0%}  EV={ev:.2f}"
    )

    return {
        "valid":      True,
        "reason":     "OK",
        "direction":  direction,
        "risk_usdt":  risk_usdt,
        "sl_pct":     sl_dist * 100,
        "leverage":   leverage,
        "notional":   notional,
        "quantity":   quantity,
        "tp1_price":  tp1,
        "tp2_price":  tp2,
        "tp3_price":  tp3,
        "tp1_qty":    tp1_qty,
        "tp2_qty":    tp2_qty,
        "tp3_qty":    tp3_qty,
        "est_wr":     est_wr,
        "blended_rr": blended_rr,
        "ev":         ev,
    }


def compound_growth_estimate(
    balance:   float,
    win_rate:  float = 0.58,
    rr:        float = 2.5,
    risk_pct:  float = RISK_PCT,
    n_trades:  int = 100,
) -> dict:
    """
    Bileşik büyüme projeksiyonu.
    Geometrik ortalama: G = (1+rr*r)^p * (1-r)^(1-p)
    """
    p = win_rate; q = 1 - p; r = risk_pct
    g = ((1 + rr * r) ** p) * ((1 - r) ** q)
    final = balance * (g ** n_trades)
    e_trade = p * rr * r - q * r
    log_g = math.log(g) if g > 0 else 0

    # Hedef: $100 → $100,000 (1000x) kaç işlem?
    if log_g > 0:
        trades_to_1000x = math.ceil(math.log(1000) / log_g)
    else:
        trades_to_1000x = float("inf")

    return {
        "start":           balance,
        "final":           final,
        "gain_pct":        (final / balance - 1) * 100,
        "g_per_trade":     g,
        "log_g":           log_g,
        "e_per_trade_pct": e_trade * 100,
        "trades_to_1000x": trades_to_1000x,
        "n_trades":        n_trades,
    }


def print_compound_summary(balance: float):
    """Terminal'e bileşik büyüme özeti yazar."""
    from live_scan import ok, warn, bad, dim, B, R, CY, GR, YL

    est = compound_growth_estimate(balance, win_rate=0.60, rr=2.5, n_trades=200)
    print(f"\n  Bileşik Büyüme (WR=%60, R:R 2.5, Risk=%2):")
    print(f"  Başlangıç: {B}${balance:,.2f}{R}")
    final_s = f"${est['final']:,.0f}"
    gain_s  = f"{est['gain_pct']:.0f}"
    print(f"  200 işlem: {ok(final_s)}  (+%{gain_s})")
    t1000   = f"{est['trades_to_1000x']}"
    dim_str = dim(f"(günde 1 işlem → {t1000} gun)")
    print(f"  1000x hedef: {B}{t1000} işlem{R}  {dim_str}")
