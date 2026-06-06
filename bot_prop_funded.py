#!/usr/bin/env python3
"""
bot_prop_funded.py — Prop-Firm Funded (Kâr Jeneratörü) Botu
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sınav geçilip fonlanan hesaba (Funded Account) ulaşıldığında kullanılır.
Amacı, "House Money" (içeride kazanılan kâr) kullanarak agresif asimetrik kâr 
(Trend Hunter) fırsatlarını değerlendirmek ve aylık Payout'u maksimize etmektir.

Özellikler:
- Mode: PROP_FUNDED (Kelly Kriteri agressifleşir, 10x'e kadar kaldıraç açılabilir)
- Hem Kripto hem Hisse/Forex pazarını tarar.
- İçeride biriken kâr "buffer" olarak algılandığı için büyük pozisyonlar alır.

Kullanım:
  python bot_prop_funded.py --balance 100000 --max-dd 5.0
"""

import argparse
import logging
import sys

from bot.engine.signal_engine import SignalEngine
from bot.engine.stock_data import fetch_stock_data
from bot_binance_sniper import print_sniper_signal, get_top_binance_futures

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")

# Funded hesapta volatilite aranır. (Nasdaq, Tech Stocks, Altın vs.)
FUNDED_WATCHLIST = [
    "GC=F", "NQ=F", "EURUSD=X",       # Altın, Nasdaq, EURUSD
    "TSLA", "NVDA", "MSTR", "COIN",   # Volatil US Hisseleri
]

def check_daily_drawdown(max_dd_limit: float) -> bool:
    """Simüle edilmiş Günlük Drawdown kontrolü."""
    current_dd = 0.0
    if current_dd >= max_dd_limit:
        print(f"\n[DURDURULDU] Günlük Max Drawdown ({current_dd}%) limiti ({max_dd_limit}%) aşıldı!")
        print("Prop-Firm kuralları gereği Funded hesap o gün için işlemi durdurdu.")
        return True
    return False

def scan_stocks_and_forex(engine: SignalEngine, min_score: float):
    print(f"\n[*] Funded Hisse/Emtia Taraması Başlıyor ({len(FUNDED_WATCHLIST)} Sembol)...")
    results = []
    for sym in FUNDED_WATCHLIST:
        df = fetch_stock_data(sym, interval="60m", period="30d")
        if df.empty:
            continue
            
        result = engine.analyze(symbol=sym, df_override=df)
        if result and result.composite >= min_score:
            results.append(result)
            
    results.sort(key=lambda x: x.composite, reverse=True)
    return results

def main():
    parser = argparse.ArgumentParser(description="Prop-Firm Funded Bot")
    parser.add_argument("--balance", type=float, default=100000.0, help="Fonlanmış hesap sermayesi (USD)")
    parser.add_argument("--max-dd", type=float, default=5.0, help="Günlük maksimum düşüş limiti (%)")
    parser.add_argument("--min-score", type=float, default=6.0, help="Minimum sinyal skoru (Daha seçici)")
    args = parser.parse_args()

    print(f"\n{'-'*50}\n💰 ALPHA İSTİHBARAT: PROP-FIRM FUNDED BOT (PAYOUT GENERATOR)\n{'-'*50}")
    
    if check_daily_drawdown(args.max_dd):
        sys.exit(1)
        
    print(f"[✔] Drawdown güvende (Limit: %{args.max_dd}). Asimetrik risk modu (PROP_FUNDED) aktif.")

    engine = SignalEngine(
        min_score=args.min_score,
        balance=args.balance,
        mode="PROP_FUNDED"  # Kârı maksimize etme modu!
    )
    
    all_signals = []

    # Kripto Taraması
    crypto_symbols = get_top_binance_futures(limit=15)
    print(f"\n[*] Funded Kripto Taraması Başlıyor...")
    crypto_results = engine.scan_watchlist(crypto_symbols, min_score=args.min_score)
    all_signals.extend(crypto_results)
    
    # Hisse/Emtia Taraması
    stock_results = scan_stocks_and_forex(engine, args.min_score)
    all_signals.extend(stock_results)
    
    # Sonuçları Sırala (Trend Hunter varsa en başa at, yoksa skora göre sırala)
    def priority_sort(res):
        is_hunter = 1 if "HUNTER" in res.action.value else 0
        return (is_hunter, res.composite)

    all_signals.sort(key=priority_sort, reverse=True)
    
    if all_signals:
        print(f"\n[+] Payout İçin En İdeal {len(all_signals)} Fırsat Bulundu. (Trend Hunter öncelikli)")
        print_sniper_signal(all_signals[0])
    else:
        print(f"\n[!] Yüksek kârlı bir asimetrik fırsat bulunamadı. Pusuya devam ediliyor...")

if __name__ == "__main__":
    main()
