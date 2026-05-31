#!/usr/bin/env python3
"""Tek seferlik tarama — cron/systemd timer bunu çağırır.

Sembol listesini tarar, geçerli setup'ları stdout'a ve bir log dosyasına
yazar. Ağ erişimi gerektirir (Binance public). Erişilemeyen sembol atlanır
ve hata olarak işaretlenir; hiçbir şey uydurulmaz.

Ortam değişkenleri (opsiyonel):
  PA_SYMBOLS   virgüllü liste (örn. "BTC/USDT,ETH/USDT,SOL/USDT")
  PA_ENTRY_TF  giriş zaman dilimi (varsayılan 1h)
  PA_HTF       üst zaman dilimi filtresi (varsayılan 4h; "none" = kapalı)
  PA_LIMIT     çekilecek mum sayısı (varsayılan 300)
  PA_PORTFOLIO pozisyon büyüklüğü hesabı için portföy (opsiyonel)
  PA_LOG_DIR   log klasörü (varsayılan price/output)
  PA_DATA      "1" ise geçerli setup'lar için BÖLÜM 2 verisi de çekilir
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

# price/ kökünü import yoluna ekle
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pa.scanner import scan
from pa.report import render

DEFAULT_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]


def _env_symbols() -> list[str]:
    raw = os.environ.get("PA_SYMBOLS", "").strip()
    if not raw:
        return DEFAULT_SYMBOLS
    return [s.strip() for s in raw.split(",") if s.strip()]


def main() -> int:
    symbols = _env_symbols()
    entry_tf = os.environ.get("PA_ENTRY_TF", "1h")
    htf_env = os.environ.get("PA_HTF", "4h").strip().lower()
    htf = None if htf_env in ("none", "", "off") else os.environ.get("PA_HTF", "4h")
    limit = int(os.environ.get("PA_LIMIT", "300"))
    portfolio = os.environ.get("PA_PORTFOLIO")
    portfolio_f = float(portfolio) if portfolio else None
    want_data = os.environ.get("PA_DATA", "0") == "1"

    log_dir = os.environ.get(
        "PA_LOG_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "output"))
    os.makedirs(log_dir, exist_ok=True)

    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%d %H:%M:%SZ")

    report = scan(symbols, entry_tf=entry_tf, htf=htf, limit=limit)

    out_lines: list[str] = [f"# Tarama @ {stamp} | TF={entry_tf} HTF={htf or '-'}"]

    valids = report.valid_setups
    if not valids:
        out_lines.append(f"  İşlem yok. Taranan: {len(symbols)}, "
                         f"hata: {len(report.errors)}")
    for item in valids:
        reading = None
        if want_data:
            try:
                from pa.market import collect
                reading = collect(item.symbol)
            except Exception:  # noqa: BLE001 — veri başarısızsa setup yine geçerli
                reading = None
        out_lines.append("")
        out_lines.append(render(item.result, reading=reading,
                                portfolio=portfolio_f))

    for item in report.errors:
        out_lines.append(f"  ⚠️ {item.symbol}: veri alınamadı ({item.error})")

    text = "\n".join(out_lines)
    print(text)

    # günlük log dosyasına ekle
    log_path = os.path.join(log_dir, now.strftime("scan-%Y-%m-%d.log"))
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(text + "\n\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
