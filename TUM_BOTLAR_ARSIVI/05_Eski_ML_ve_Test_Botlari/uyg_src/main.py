#!/usr/bin/env python3
"""
Alpha İstihbarat Sistemi — Giriş noktası
Kullanım:
  python main.py              → Tek tarama (scheduler yok)
  python main.py --loop       → Sürekli tarama (APScheduler)
  python main.py --social     → Sadece sosyal güncelleme
  python main.py --backtest   → Backtest modu
  python main.py --status     → Son sinyalleri göster
"""
import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# .env yükle
load_dotenv(Path(__file__).parent / ".env")

# Logging ayarla
def setup_logging(level: str = "INFO"):
    try:
        import colorlog
        handler = colorlog.StreamHandler()
        handler.setFormatter(colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s [%(levelname)s] %(name)s: %(message)s%(reset)s",
            datefmt="%H:%M:%S",
        ))
        logging.basicConfig(handlers=[handler], level=getattr(logging, level, logging.INFO))
    except ImportError:
        logging.basicConfig(
            level=getattr(logging, level, logging.INFO),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    # Üçüncü parti kütüphane loglarını bastır
    for noisy in ["httpx", "httpcore", "ccxt", "urllib3", "requests", "asyncio"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)


def check_env():
    """Kritik env değişkenlerini kontrol eder."""
    warnings = []
    if not os.getenv("ANTHROPIC_API_KEY"):
        warnings.append("ANTHROPIC_API_KEY eksik — Claude analizi devre dışı")
    if not os.getenv("BINANCE_API_KEY"):
        warnings.append("BINANCE_API_KEY eksik — Public API kullanılacak (limitli)")
    if not os.getenv("EMAIL_SENDER"):
        warnings.append("EMAIL_SENDER eksik — Email bildirimleri devre dışı")
    if not os.getenv("YOUTUBE_API_KEY"):
        warnings.append("YOUTUBE_API_KEY eksik — YouTube transkriptleri kısıtlı")

    for w in warnings:
        logging.getLogger("main").warning(f"⚠️  {w}")


def main():
    parser = argparse.ArgumentParser(description="Alpha İstihbarat Sistemi")
    parser.add_argument("--loop", action="store_true", help="Sürekli tarama modu")
    parser.add_argument("--social", action="store_true", help="Sadece sosyal güncelleme")
    parser.add_argument("--backtest", action="store_true", help="Backtest modu")
    parser.add_argument("--status", action="store_true", help="Son sinyalleri göster")
    parser.add_argument("--symbol", type=str, help="Tek sembol analiz et (örn: BTC/USDT)")
    parser.add_argument("--config", type=str, default="config/settings.yaml")
    parser.add_argument("--log-level", type=str, default="INFO")
    args = parser.parse_args()

    setup_logging(args.log_level)
    logger = logging.getLogger("main")
    logger.info("Alpha İstihbarat Sistemi başlatılıyor...")

    check_env()

    # DB başlat
    from data.database.db import init_db
    init_db()

    # Config yükle
    from main_engine import load_config
    config = load_config(args.config)

    if args.status:
        from data.database.db import get_recent_signals
        signals = get_recent_signals(20)
        print(f"\n{'='*60}")
        print(f"Son {len(signals)} sinyal:")
        for s in signals:
            print(f"  {s['timestamp'][:16]}  {s['symbol']:12}  {s['signal_level']:10}  {s.get('composite_score', 0):.1f}/10  {s.get('direction', '?')}")
        return

    if args.backtest:
        run_backtest_mode(config)
        return

    if args.symbol:
        # Tek sembol
        from main_engine import run_full_scan
        from market.data_fetcher import MarketDataFetcher
        from main_engine import analyze_symbol
        from output.console_printer import print_signal

        fetcher = MarketDataFetcher()
        asset_type = "bist" if args.symbol.endswith(".IS") else "crypto"
        score = analyze_symbol(args.symbol, asset_type, fetcher, config, {})
        if score:
            print_signal(score)
        return

    if args.loop:
        from scheduler import start_scheduler
        start_scheduler(config)
    else:
        from main_engine import run_full_scan
        run_full_scan(config)


def run_backtest_mode(config: dict):
    """Tüm watchlist için backtest çalıştırır."""
    from market.data_fetcher import MarketDataFetcher
    from analysis.smc_engine import analyze_smc
    from analysis.classic_indicators import analyze_classic
    from backtest.engine import run_backtest

    logger = logging.getLogger("backtest")
    fetcher = MarketDataFetcher()

    symbols = config.get("crypto_watchlist", ["BTC/USDT", "ETH/USDT", "SOL/USDT"])

    def simple_signal(df):
        """Basit backtest sinyal fonksiyonu."""
        smc = analyze_smc(df, config.get("smc", {}))
        classic = analyze_classic(df, config.get("technical", {}))
        if smc.trend == "BULLISH" and smc.score >= 5 and classic.score >= 5:
            return "LONG"
        elif smc.trend == "BEARISH" and smc.score >= 5 and classic.score >= 5:
            return "SHORT"
        return None

    print(f"\n{'='*60}")
    print(f"{'BACKTEST SONUÇLARI':^60}")
    print(f"{'='*60}")

    for symbol in symbols:
        df = fetcher.fetch(symbol, "4h", 500)
        if df.empty:
            continue

        result = run_backtest(df, simple_signal, symbol=symbol, timeframe="4h")

        print(f"\n{symbol}:")
        print(f"  İşlem sayısı:  {result.total_trades}")
        print(f"  Win Rate:      {result.win_rate:.1%}  (hedef: >52%)")
        print(f"  Profit Factor: {result.profit_factor:.2f}  (hedef: >1.3)")
        print(f"  Max Drawdown:  {result.max_drawdown:.1%}  (hedef: <20%)")
        print(f"  Sharpe:        {result.sharpe_ratio:.2f}  (hedef: >1.0)")
        print(f"  Toplam Getiri: {result.total_return:.1%}")


if __name__ == "__main__":
    main()
