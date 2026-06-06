#!/usr/bin/env python3
"""
ultimate_prop_bot.py — ULTIMATE HİBRİT PROP BOTU
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Claude'un "Compound Engine / Survival" mimarisi ile bizim "SMC + Trend Hunter" 
motorumuzun kusursuz birleşimi.

Özellikler:
1. Claude'un "intraday_halt" (%3 günlük zarar limiti) kuralını uygular.
2. Claude'un "profit_bank" (%3 kârı cebe at, trailing-DD'den kaç) kuralını uygular.
3. Piyasa yatayken SignalEngine'in muhafazakar (PROP_FUNDED) kurallarına uyar.
4. Hacim patladığında TREND_HUNTER pusu moduna geçer ve asimetrik kâr yakalar.

Kullanım:
  python ultimate_prop_bot.py --balance 100000 --firm hyro2
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

# Yol ayarları (Claude'un compound_engine modülüne erişim için)
sys.path.append(str(Path(__file__).resolve().parent / "uyg/06_HAZIR_BOTLAR_RAPORLAR/botlar"))
import compound_engine as ce

from bot.engine.signal_engine import SignalEngine
from bot_binance_sniper import print_sniper_signal, get_top_binance_futures

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")

_STATE_FILE = Path("ultimate_state.json")

def load_state() -> dict:
    if _STATE_FILE.exists():
        return json.loads(_STATE_FILE.read_text())
    return {"start_eq": None, "peak_eq": None, "day": None, "day_start_eq": None}

def save_state(st: dict):
    _STATE_FILE.write_text(json.dumps(st))

def update_daily_state(equity: float, st: dict):
    today = time.strftime("%Y-%m-%d")
    if st["start_eq"] is None:
        st.update(start_eq=equity, peak_eq=equity, day=today, day_start_eq=equity)
    
    if st["day"] != today:
        st["day"] = today
        st["day_start_eq"] = equity
    
    st["peak_eq"] = max(st["peak_eq"] or equity, equity)
    return st

def main():
    parser = argparse.ArgumentParser(description="Ultimate Prop Bot")
    parser.add_argument("--balance", type=float, default=100000.0, help="Mevcut bakiye (USDT)")
    parser.add_argument("--firm", type=str, default="hyro2", choices=list(ce.FIRMS.keys()), help="Firma risk profili")
    parser.add_argument("--min-score", type=float, default=6.0, help="Minimum sinyal skoru")
    args = parser.parse_args()

    print(f"\n{'-'*60}\n🚀 ALPHA İSTİHBARAT: ULTIMATE PROP BOT (Hibrit Karargah)\n{'-'*60}")
    
    st = load_state()
    equity = args.balance
    st = update_daily_state(equity, st)
    
    firm_rules = ce.FIRMS[args.firm]
    print(f"[*] Firma Profili: {firm_rules['label']}")
    print(f"[*] Başlangıç: ${st['start_eq']} | Gün Başı: ${st['day_start_eq']} | Zirve: ${st['peak_eq']} | Mevcut: ${equity}")

    # 1. Claude'un Güvenlik Kuralları: Kill Switch & Intraday Halt
    halt_reason = ce.kill_switch(equity, st["peak_eq"], st["day_start_eq"], firm_rules)
    if not halt_reason:
        halt_reason = ce.intraday_halt(equity, st["day_start_eq"], halt=0.03)

    if halt_reason:
        print(f"\n[⛔ DURDURULDU] {halt_reason}")
        print("Sistemin (Trailing-DD veya Günlük Limit) korunması için bugün işlem yapılmayacak.")
        save_state(st)
        sys.exit(0)

    # 2. Claude'un Kâr Bankalama Kuralı: Profit Bank (+%3'te cebe at)
    gross, trader_cut, new_baseline = ce.profit_bank(equity, st["start_eq"], trigger=0.03, split=0.80)
    if gross > 0:
        print(f"\n[💰 PROFIT BANK TETİKLENDİ] Kâr hedefi (+%3) aşıldı!")
        print(f"   -> Toplam Kâr: ${gross:.2f}")
        print(f"   -> Sizin Payınız (%80): ${trader_cut:.2f}")
        print(f"   -> Trailing-DD'den korunmak için yeni başlangıç seviyesi (Baseline) güncellendi: ${new_baseline:.2f}")
        st["start_eq"] = new_baseline
        st["peak_eq"] = new_baseline
        st["day_start_eq"] = new_baseline
        save_state(st)
        sys.exit(0) # Kâr cebe atıldıysa işlemi kapat ve bekle (Compound yapma).

    print("[✔] Emniyet kemerleri devrede. Tehlike yok. Hedef taraması başlıyor...")

    # 3. Bizim Kılıcımız: SignalEngine (Trend Hunter modlu)
    engine = SignalEngine(
        min_score=args.min_score,
        balance=equity,
        mode="PROP_FUNDED"  # Sizer bu modda kaldıraç esnetir ama SignalEngine hala SMC çalıştırır.
    )
    
    crypto_symbols = get_top_binance_futures(limit=15)
    print(f"\n[*] Piyasalar Taranıyor ({len(crypto_symbols)} Sembol)...")
    results = engine.scan_watchlist(crypto_symbols, min_score=args.min_score)
    
    # 4. Sonuçları Sırala (Trend Hunter varsa en başa at)
    def priority_sort(res):
        is_hunter = 1 if "HUNTER" in res.action.value else 0
        return (is_hunter, res.composite)

    results.sort(key=priority_sort, reverse=True)
    
    if results:
        print(f"\n[+] Payout İçin En İdeal {len(results)} Fırsat Bulundu.")
        best_signal = results[0]
        if "HUNTER" in best_signal.action.value:
            print("🔥 DİKKAT: TREND HUNTER (Pusu Modu) TETİKLENDİ! HACİM PATLAMASI YAKALANDI!")
        else:
            print("🛡️ Piyasalar yatay. Muhafazakar (Survival) sinyaller değerlendiriliyor.")
        
        print_sniper_signal(best_signal)
    else:
        print(f"\n[!] Gerekli risk/getiri profiline uyan fırsat bulunamadı. Sabırla bekleniyor...")

    save_state(st)

if __name__ == "__main__":
    main()
