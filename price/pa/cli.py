"""Komut satırı arayüzü (stdlib).

Örnekler:
  python -m pa.cli --symbol BTC/USDT --tf 1h --htf 4h        # ccxt gerekir
  python -m pa.cli --csv data/sample_btc_1h.csv --tf 1h --portfolio 1000
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from . import data as datamod
from .analyze import analyze
from .report import render


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="pa", description="Price Action analiz motoru")
    g = p.add_argument_group("veri")
    g.add_argument("--symbol", default="BTC/USDT")
    g.add_argument("--tf", default="1h", help="giriş zaman dilimi")
    g.add_argument("--htf", default=None, help="üst zaman dilimi (filtre)")
    g.add_argument("--limit", type=int, default=500)
    g.add_argument("--exchange", default="binance")
    g.add_argument("--csv", default=None, help="giriş TF CSV yolu")
    g.add_argument("--htf-csv", default=None, help="üst TF CSV yolu")

    r = p.add_argument_group("risk")
    r.add_argument("--portfolio", type=float, default=None)
    r.add_argument("--risk-pct", type=float, default=1.0)
    r.add_argument("-k", type=int, default=2, help="swing fractal penceresi")

    p.add_argument("--data", action="store_true",
                   help="BÖLÜM 2: canlı funding/OI/long-short çek (ağ gerekir)")

    args = p.parse_args(argv)

    try:
        if args.csv:
            entry = datamod.load_csv(args.csv)
            src = f"CSV {args.csv}"
        else:
            entry = datamod.fetch_ohlcv(args.symbol, args.tf, args.limit, args.exchange)
            src = f"{args.exchange} {args.symbol} {args.tf}"
    except Exception as e:  # noqa: BLE001 — kaynak alınamadıysa açıkça bildir
        print(f"⚠️ Giriş verisi alınamadı: {e}", file=sys.stderr)
        return 2

    htf = None
    htf_tf = args.htf or ""
    if args.htf_csv:
        try:
            htf = datamod.load_csv(args.htf_csv)
            htf_tf = args.htf or "HTF"
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ Üst TF CSV alınamadı: {e}", file=sys.stderr)
    elif args.htf and not args.csv:
        try:
            htf = datamod.fetch_ohlcv(args.symbol, args.htf, args.limit, args.exchange)
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ Üst TF verisi alınamadı: {e}", file=sys.stderr)

    result = analyze(entry, htf, entry_tf=args.tf, htf_tf=htf_tf,
                     symbol=args.symbol, k=args.k)

    reading = None
    if args.data:
        from .market import collect
        reading = collect(args.symbol)  # her metrik kendi içinde yakalanır

    print(f"# Kaynak: {src}\n")
    print(render(result, reading=reading,
                 portfolio=args.portfolio, risk_pct=args.risk_pct))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
