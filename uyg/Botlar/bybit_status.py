#!/usr/bin/env python3
"""Bybit TESTNET durum toplayıcı — dashboard /bybit sekmesi için (read-only).

Testnet hesabını okur (equity, açık pozisyonlar, son işlemler, PnL, DD-limitlerine mesafe),
paper/bybit_status.json yazar. Cron (her 15 dk). Anahtarlar .hyro_env'den; emir YOK (read-only).

Çalıştırma: . /root/tirad/.hyro_env && /root/tirad/.venv/bin/python /root/tirad/uyg/Botlar/bybit_status.py
"""
import json
import os
import time
from pathlib import Path

OUT = Path("/root/tirad/paper") if Path("/root/tirad/paper").exists() else Path(__file__).resolve().parent / "_state"
OUT.mkdir(parents=True, exist_ok=True)
STATUS = OUT / "bybit_status.json"
FIRM = "HyroTrader (hedef) — Bybit perp"
DAILY_LIMIT, TOTAL_LIMIT = -5.0, -10.0   # HyroTrader 2-step (%)


def main():
    import ccxt
    k, s = os.environ.get("BYBIT_TESTNET_KEY"), os.environ.get("BYBIT_TESTNET_SECRET")
    rec = {"ts": time.strftime("%Y-%m-%d %H:%M UTC"), "firm": FIRM,
           "mode": "TESTNET forward-doğrulama (gerçek sermaye YOK)", "funded": False,
           "limits": {"daily": DAILY_LIMIT, "total": TOTAL_LIMIT}}
    prev = {}
    if STATUS.exists():
        try:
            prev = json.loads(STATUS.read_text())
        except Exception:  # noqa: BLE001
            prev = {}
    try:
        ex = ccxt.bybit({"apiKey": k, "secret": s, "enableRateLimit": True,
                         "options": {"defaultType": "swap"}})
        ex.set_sandbox_mode(True)
        wb = ex.privateGetV5AccountWalletBalance({"accountType": "UNIFIED"})["result"]["list"]
        eq = float(wb[0].get("totalEquity") or 0) if wb else 0.0
        avail = float(wb[0].get("totalAvailableBalance") or 0) if wb else 0.0
        rec["equity"], rec["available"] = round(eq, 2), round(avail, 2)
        # baseline & peak (kalıcı)
        start_eq = prev.get("start_eq") or (eq if eq > 0 else 10000.0)
        peak = max(prev.get("peak_eq") or eq, eq)
        # gün başı equity (UTC gün değişiminde sıfırla)
        today = time.strftime("%Y-%m-%d")
        day_start = prev.get("day_start_eq") if prev.get("day") == today else eq
        rec.update(start_eq=round(start_eq, 2), peak_eq=round(peak, 2),
                   day=today, day_start_eq=round(day_start or eq, 2))
        rec["pnl_pct"] = round((eq / start_eq - 1) * 100, 2) if start_eq else 0.0
        rec["daily_dd_pct"] = round((eq / (day_start or eq) - 1) * 100, 2)
        rec["total_dd_pct"] = round((eq / peak - 1) * 100, 2) if peak else 0.0
        rec["daily_room"] = round(rec["daily_dd_pct"] - DAILY_LIMIT, 2)   # limite kalan pay
        rec["total_room"] = round(rec["total_dd_pct"] - TOTAL_LIMIT, 2)
        # açık pozisyonlar
        pos = []
        for p in ex.fetch_positions():
            c = float(p.get("contracts") or 0)
            if c:
                pos.append({"sym": p["symbol"].split("/")[0], "side": p.get("side"),
                            "notional": round(float(p.get("notional") or 0), 2),
                            "entry": p.get("entryPrice"),
                            "upnl": round(float(p.get("unrealizedPnl") or 0), 2)})
        rec["positions"] = pos
        # son kapanan işlemler (realized PnL)
        trades = []
        try:
            cp = ex.privateGetV5PositionClosedPnl({"category": "linear", "limit": 12})
            for t in cp["result"]["list"]:
                trades.append({"sym": t.get("symbol"), "side": t.get("side"),
                               "pnl": round(float(t.get("closedPnl") or 0), 2),
                               "ts": time.strftime("%m-%d %H:%M", time.gmtime(int(t.get("updatedTime", 0)) / 1000))})
        except Exception:  # noqa: BLE001
            pass
        rec["recent_trades"] = trades
        rec["n_open"] = len(pos)
        # NAV eğrisi (her çalışmada nokta ekle, son 300)
        curve = prev.get("nav_curve") or []
        curve.append({"ts": rec["ts"], "v": round(eq, 2)})
        rec["nav_curve"] = curve[-300:]
        rec["ok"] = True
    except Exception as e:  # noqa: BLE001
        rec["ok"] = False
        rec["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    STATUS.write_text(json.dumps(rec, ensure_ascii=False, indent=2))
    print(f"[{rec['ts']}] equity={rec.get('equity')} pos={rec.get('n_open')} ok={rec.get('ok')}")


if __name__ == "__main__":
    main()
