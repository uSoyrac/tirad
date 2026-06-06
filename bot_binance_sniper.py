#!/usr/bin/env python3
"""
bot_binance_sniper.py — Maksimum Kâr Odaklı Top 20 Binance Kripto Avcısı
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Bu bot, Binance Futures üzerindeki en yüksek hacimli 20 coini anlık olarak tarar.
Prop-firm kurallarına takılmaksızın (STANDARD mod), "Trend Hunter" pusu
mekanizmasını ve agresif asimetrik R:R TP (Take Profit) seviyelerini kullanarak
maksimum kâr elde etmeyi hedefler.

Kullanım:
  python bot_binance_sniper.py --balance 1000
"""

import argparse
import logging
import sys
from datetime import datetime

import ccxt
from bot.engine.signal_engine import SignalEngine
from bot.engine.base import Action

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sniper")

def get_top_binance_futures(limit=20) -> list[str]:
    """Binance Futures üzerinde en yüksek hacme sahip coinleri getirir."""
    try:
        print(f"[*] Binance üzerinden en yüksek hacimli {limit} coin çekiliyor...")
        exchange = ccxt.binance({'options': {'defaultType': 'future'}})
        exchange.load_markets()
        tickers = exchange.fetch_tickers()
        
        # Sadece USDT paritelerini al ve hacme göre sırala
        usdt_tickers = [t for sym, t in tickers.items() if sym.endswith('/USDT')]
        usdt_tickers.sort(key=lambda x: float(x.get('quoteVolume', 0)), reverse=True)
        
        symbols = [t['symbol'] for t in usdt_tickers[:limit]]
        print(f"[+] Çekilen Coinler: {', '.join(symbols)}")
        return symbols
    except Exception as e:
        print(f"[-] Binance API hatası: {e}. Varsayılan listeye geçiliyor.")
        return [
            "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
            "DOGE/USDT", "ADA/USDT", "AVAX/USDT", "LINK/USDT", "DOT/USDT"
        ]

def print_sniper_signal(result):
    """Sniper sinyal formatında çıktıyı basar."""
    # Terminal renk kodları
    B = "\033[1m"; R = "\033[0m"
    GR = "\033[32m"; RD = "\033[31m"; YL = "\033[33m"
    CY = "\033[36m"
    
    direction_color = GR if result.direction == "LONG" else RD
    action_color    = YL if "HUNTER" in result.action.value else CY
    
    print(f"\n{B}{'=' * 60}{R}")
    print(f"{B}🎯 SNIPER SİNYALİ YAKALANDI: {result.symbol}{R}  [{result.timestamp[11:16]} UTC]")
    print(f"{B}{'=' * 60}{R}")
    print(f"Aksiyon     : {action_color}{result.action.value}{R}")
    print(f"Yön         : {direction_color}{result.direction}{R}")
    print(f"Skor        : {result.composite:.1f}/10  (SMC: {result.smc_score:.1f}, ADV: {result.adv_score:.1f})")
    print(f"Giriş Fiyatı: {result.entry_price:.4f}")
    print(f"Stop-Loss   : {RD}{result.sl_price:.4f}{R}")
    print(f"Hedef (TP3) : {GR}{result.tp3_price:.4f}{R}")
    print(f"Kaldıraç    : {result.market_structure.composite_score if result.market_structure else 'Bilinmiyor'} (Öneri: 5-10x)")
    
    if result.action in [Action.TREND_HUNTER_LONG, Action.TREND_HUNTER_SHORT]:
        print(f"\n{B}{YL}⚠️ DİKKAT: MACRO BREAKOUT (TREND HUNTER) TETİKLENDİ! ⚠️{R}")
        print("Hacim ve Volatilite patlaması tespit edildi. Asimetrik kâr fırsatı!")
        
    print(f"{B}{'-' * 60}{R}")

def main():
    parser = argparse.ArgumentParser(description="Binance Top 20 Sniper Bot")
    parser.add_argument("--balance", type=float, default=1000.0, help="Sermaye miktarı (USDT)")
    parser.add_argument("--limit", type=int, default=20, help="Taranacak coin sayısı")
    parser.add_argument("--min-score", type=float, default=6.5, help="İşleme girmek için min skor")
    args = parser.parse_args()

    print(f"\n{'-'*50}\n🚀 ALPHA İSTİHBARAT: BINANCE SNIPER BOT\n{'-'*50}")
    
    # 1. Hacimli Coinleri Çek
    symbols = get_top_binance_futures(limit=args.limit)
    
    # 2. Motoru STANDARD modda başlat (Kâr optimizasyonu için)
    engine = SignalEngine(
        min_score=args.min_score,
        balance=args.balance,
        mode="STANDARD"  # Sınırlandırma yok
    )
    
    # 3. Taramayı başlat
    print(f"\n[*] Sinyal taraması başlatılıyor (Min Skor: {args.min_score})...")
    results = engine.scan_watchlist(symbols, min_score=args.min_score)
    
    # 4. En iyisini filtrele (Öncelik Trend Hunter, sonra yüksek skor)
    best_signal = None
    for res in results:
        # Eğer Trend Hunter varsa direkt al
        if res.action in [Action.TREND_HUNTER_LONG, Action.TREND_HUNTER_SHORT]:
            best_signal = res
            break
            
    # Trend Hunter yoksa en yüksek skorluyu al
    if not best_signal and results:
        best_signal = results[0]  # scan_watchlist zaten skora göre sıralıyor
        
    if best_signal:
        print_sniper_signal(best_signal)
    else:
        print(f"\n[!] Şu an için {args.min_score} üzeri güçlü bir fırsat bulunamadı. Sniper pusuya devam ediyor...")
        
    print("\n[✔] Tarama tamamlandı.")

if __name__ == "__main__":
    main()
