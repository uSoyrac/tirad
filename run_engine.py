#!/usr/bin/env python3
"""
run_engine.py — Optimal Sinyal Motoru v3 CLI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Kullanım örnekleri:

  # Tek sembol analiz
  python run_engine.py --symbol ETH/USDT

  # Tüm watchlist tarama
  python run_engine.py --scan

  # Yüksek skor filtresi ile tarama
  python run_engine.py --scan --min-score 6.5

  # LLM debate ile (Ollama çalışıyor olmalı)
  python run_engine.py --scan --llm

  # Bakiye ile (pozisyon boyutlaması için)
  python run_engine.py --scan --balance 500
"""

import argparse
import logging
import sys
from pathlib import Path

# Proje kökünü path'e ekle
sys.path.insert(0, str(Path(__file__).parent))

# ── Loglama ──────────────────────────────────────────────────────────
logging.basicConfig(
    level  = logging.WARNING,
    format = "%(asctime)s  %(name)s  %(levelname)s  %(message)s",
)
# Debug için: logging.getLogger("bot.engine").setLevel(logging.DEBUG)

# ── Varsayılan Watchlist ───────────────────────────────────────────────
DEFAULT_WATCHLIST = [
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "BNB/USDT",
    "AVAX/USDT",
    "LINK/USDT",
    "DOT/USDT",
    "XRP/USDT",
    "ARB/USDT",
    "OP/USDT",
]


def main() -> int:
    """CLI giriş noktası. 0 = başarılı, 1 = hata."""
    parser = argparse.ArgumentParser(
        description="Kripto Alpha İstihbarat — Sinyal Motoru v3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--symbol",
        help="Tek sembol analiz ('ETH/USDT')",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Watchlist taraması çalıştır",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=5.5,
        metavar="SCORE",
        help="Minimum sinyal skoru (varsayılan: 5.5)",
    )
    parser.add_argument(
        "--balance",
        type=float,
        default=0.0,
        metavar="USDT",
        help="Mevcut USDT bakiyesi (pozisyon boyutu için)",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Ollama LLM debate'i etkinleştir",
    )
    parser.add_argument(
        "--min-confirmations",
        type=int,
        default=2,
        metavar="N",
        help="Minimum confluence onay sayısı (varsayılan: 2)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="STANDARD",
        choices=["STANDARD", "PROP_EVAL", "PROP_FUNDED"],
        help="Çalışma modu: STANDARD, PROP_EVAL, PROP_FUNDED",
    )
    parser.add_argument(
        "--max-dd",
        type=float,
        default=0.0,
        help="Günlük Max Drawdown limiti (Örn: 4.0). Aşılırsa işlem durdurulur.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Debug loglarını göster",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger("bot.engine").setLevel(logging.DEBUG)

    if not args.symbol and not args.scan:
        parser.print_help()
        return 0

    # ── Engine oluştur ────────────────────────────────────────────────
    try:
        from bot.engine import SignalEngine
        from bot.engine.reporter import print_signal, print_scan_summary
    except ImportError as exc:
        print(f"İçe aktarma hatası: {exc}")
        print("Lütfen 'pip install -r requirements.txt' çalıştırın.")
        return 1

    engine = SignalEngine(
        min_score         = args.min_score,
        min_confirmations = args.min_confirmations,
        use_llm           = args.llm,
        balance           = args.balance,
        mode              = args.mode,
    )

    # ── Prop Firm Max DD Kontrolü ─────────────────────────────────────
    if args.mode in ["PROP_EVAL", "PROP_FUNDED"] and args.max_dd > 0:
        # Gerçek uygulamada bu veri veritabanından / aracı kurumdan alınır.
        current_daily_dd = 0.0 # Placeholder
        if current_daily_dd >= args.max_dd:
            print(f"\n[DURDURULDU] Günlük Max Drawdown ({args.max_dd}%) aşıldı! Prop Firm hesabı riske atılamaz.\n")
            return 1
        else:
            print(f"  [PROP MODE: {args.mode}] Günlük DD izleniyor (Max: {args.max_dd}%)")

    # ── Tek sembol ────────────────────────────────────────────────────
    if args.symbol:
        print(f"\n  Analiz ediliyor: {args.symbol} ...")
        result = engine.analyze(args.symbol)
        if result:
            print_signal(result)
        else:
            print(f"\n  Sinyal üretilemedi: {args.symbol}\n")
        return 0

    # ── Watchlist tarama ──────────────────────────────────────────────
    if args.scan:
        print(f"\n  {len(DEFAULT_WATCHLIST)} sembol taranıyor ...\n")
        results = engine.scan_watchlist(DEFAULT_WATCHLIST, min_score=args.min_score)
        print_scan_summary(results)

        # En iyi 3 sinyalin detayını göster
        for r in results[:3]:
            print_signal(r)

        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
