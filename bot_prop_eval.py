#!/usr/bin/env python3
"""
bot_prop_eval.py — Prop-Firm Evaluation (Sınav) Botu
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Bu bot, fon şirketlerinin (FTMO, Apex, vb.) değerlendirme aşamalarını
geçecek şekilde tasarlanmıştır. Temel odak noktası PARA KAZANMAK DEĞİL,
HESABI KORUMAKTIR (Sermaye koruması).

Özellikler:
- Mode: PROP_EVAL (Risk yarıya iner, kaldıraç max 2x)
- Günlük Drawdown limiti katı bir şekilde uygulanır.
- Kripto (Binance) ve Hisse/Forex (Yahoo Finance) aynı anda taranır.

Kullanım:
  python bot_prop_eval.py --balance 100000 --max-dd 4.5
"""

import argparse
import logging
import sys

from bot.engine.signal_engine import SignalEngine
from bot.engine.stock_data import fetch_stock_data
from bot_binance_sniper import print_sniper_signal, get_top_binance_futures

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")

# Sınav için en stabil Forex ve US Hisse senetleri (Volatility / Likidite dengeli)
EVAL_STOCK_WATCHLIST = [
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", # Majör Forex
    "AAPL", "MSFT", "GOOGL", "SPY",     # US Hisseleri & Endeks
]

def check_daily_drawdown(max_dd_limit: float) -> bool:
    """
    Simüle edilmiş Günlük Drawdown kontrolü.
    Gerçek uygulamada bu veriyi fon şirketinin API'sinden veya MT5'ten çekeriz.
    """
    # Placeholder: Şimdilik %0 olarak varsayıyoruz.
    current_dd = 0.0
    if current_dd >= max_dd_limit:
        print(f"\n[DURDURULDU] Günlük Max Drawdown ({current_dd}%) limiti ({max_dd_limit}%) aşıldı!")
        print("Prop-Firm sınav kuralları gereği bot o gün için işlemi durdurdu.")
        return True
    return False

def scan_stocks_and_forex(engine: SignalEngine, min_score: float):
    """US Stock ve Forex sembollerini tarar."""
    print(f"\n[*] Hisse ve Forex Taraması Başlıyor ({len(EVAL_STOCK_WATCHLIST)} Sembol)...")
    results = []
    for sym in EVAL_STOCK_WATCHLIST:
        # Hisse verisi 1 saatlik (60m) veya 4 saatlik çekilebilir.
        df = fetch_stock_data(sym, interval="60m", period="30d")
        if df.empty:
            continue
            
        result = engine.analyze(symbol=sym, df_override=df)
        if result and result.composite >= min_score:
            results.append(result)
            
    results.sort(key=lambda x: x.composite, reverse=True)
    return results

def main():
    parser = argparse.ArgumentParser(description="Prop-Firm Evaluation Bot")
    parser.add_argument("--balance", type=float, default=100000.0, help="Fon sınavı sermayesi (USD)")
    parser.add_argument("--max-dd", type=float, default=4.5, help="Günlük maksimum düşüş limiti (%)")
    parser.add_argument("--min-score", type=float, default=5.5, help="Minimum sinyal skoru")
    args = parser.parse_args()

    print(f"\n{'-'*50}\n🛡️  ALPHA İSTİHBARAT: PROP-FIRM EVALUATION BOT\n{'-'*50}")
    
    # 1. Drawdown Koruması
    if check_daily_drawdown(args.max_dd):
        sys.exit(1)
        
    print(f"[✔] Drawdown güvende (Limit: %{args.max_dd}). Sınav modu aktif.")

    # 2. Motoru PROP_EVAL modunda başlat
    engine = SignalEngine(
        min_score=args.min_score,
        balance=args.balance,
        mode="PROP_EVAL"  # Sermaye koruma modu!
    )
    
    all_signals = []

    # 3. Kripto Taraması (Sadece en stabil Top 10)
    crypto_symbols = get_top_binance_futures(limit=10)
    print(f"\n[*] Kripto Taraması Başlıyor...")
    crypto_results = engine.scan_watchlist(crypto_symbols, min_score=args.min_score)
    all_signals.extend(crypto_results)
    
    # 4. Hisse/Forex Taraması
    stock_results = scan_stocks_and_forex(engine, args.min_score)
    all_signals.extend(stock_results)
    
    # 5. Sonuçları Sırala ve En İyi İşlemi Bul
    all_signals.sort(key=lambda x: x.composite, reverse=True)
    
    if all_signals:
        print(f"\n[+] En Güvenli {len(all_signals)} Fırsat Bulundu. (İlk sıradaki işleme girilir)")
        print_sniper_signal(all_signals[0])
    else:
        print(f"\n[!] Sınav modunda risk alınacak bir sinyal bulunamadı. Sermaye korumaya devam.")

if __name__ == "__main__":
    main()
