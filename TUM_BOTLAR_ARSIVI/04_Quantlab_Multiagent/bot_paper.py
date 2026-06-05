#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
BOT_PAPER — Combo (trend+funding) PAPER-TRADING defteri  (CANLI EMİR YOK)
═══════════════════════════════════════════════════════════════════════════════
Önerilen bot_combo'yu ileriye-dönük, survivorship-free, SIFIR riskle doğrular.
Her çalıştırmada: güncel hedef pozisyonları + OOS-başından bugüne paper NAV + paper
emirleri yazar ve ledger'ı (reports_out/paper_book.json) güncel-tutar. Yeni barlar
geldikçe tekrar çalıştır → NAV uzar, track-record birikir.

Bu, canlı sermayeden ÖNCEKİ disiplinli kapıdır: backtest Sharpe ~1.74/2.25 ileriye
dönük gerçek-veride tutuyor mu, parayı riske atmadan gör.

ÇALIŞTIRMA:  quantlab/.venv/bin/python uyg/Botlar/bot_paper.py
(İdeal: günde bir / 4 saatte bir çalıştır — örn. cron.)
═══════════════════════════════════════════════════════════════════════════════
"""
from _botlib import load_universe


def main():
    print(__doc__)
    cfg, frames, higher, targets, momentum, fundings = load_universe()
    from quantlab.paper import combo_book
    from pathlib import Path

    book = combo_book.build_book(frames, fundings, cfg)
    led_path = Path(__file__).resolve().parents[2] / "quantlab" / "reports_out" / "paper_book.json"
    led_path.parent.mkdir(exist_ok=True)

    # önceki ledger'a göre değişen emirleri göster
    prev = {}
    if led_path.exists():
        import json
        prev = json.loads(led_path.read_text()).get("holdings", {})

    h = book["holdings"]
    print(f"=== PAPER DEFTER (as-of {book['as_of']}) — CANLI EMİR YOK ===")
    print(f"Ağırlık: trend {book['weights']['trend']} / funding {book['weights']['funding']}")
    print("\nGÜNCEL HEDEF:")
    print(f"  TREND  -> LONG {h['trend_long'] or '(nakit)'}")
    print(f"  FUNDING-> LONG {h['funding_long']}  |  SHORT {h['funding_short']}")
    if prev:
        pl = set(prev.get("trend_long", []))
        print(f"\nTREND emir farkı: GİR {sorted(set(h['trend_long'])-pl)} | ÇIK {sorted(pl-set(h['trend_long']))}")
    print(f"\nPAPER NAV (OOS başından): ${book['nav_start']:.0f} -> ${book['nav_now']:.0f}")
    print(f"  Şu ana kadar OOS Sharpe {book['oos_sharpe_to_date']} | MaxDD {book['oos_maxdd_to_date']*100:.1f}%")
    print(f"  ({len(book['nav_series'])} günlük kayıt)")

    combo_book.save_ledger(book, led_path)
    print(f"\nLedger kaydedildi -> {led_path}")
    print("⚠️ Paper-trade. Canlı sermaye yok. Backtest survivorship-capped — ileriye-dönük doğrula.")


if __name__ == "__main__":
    main()
