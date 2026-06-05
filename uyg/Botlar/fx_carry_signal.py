#!/usr/bin/env python3
"""BOT 2 — FX CARRY manuel sinyali (FundingPips/forex venue'leri için).

Tek gerçek FX faktörü: carry. Cari yıl politika-faizlerine göre G10 para birimlerini USD'ye
karşı sıralar; yüksek-faizli Top-2 LONG, düşük-faizli Bottom-2 SHORT. İşlenebilir FX paritesi +
yön (BUY/SELL) + carry farkı üretir. Yavaş sinyal (faiz değişince ~çeyreklik döner). EMİR YOK —
manuel gir. paper/fx_signal.json yazar; /forex sekmesi gösterir.

⚠️ MODEST faktör (~0.5 Sharpe, 9/12 yıl +); prop +%10 hedefi için yavaş — yavaş-gelir/diversifikasyon.
   Carry kriz-kuyruğu taşır (risk-off'ta düşer); stop-loss ZORUNLU.
"""
import json
import time
from pathlib import Path

OUT = Path("/root/tirad/paper") if Path("/root/tirad/paper").exists() else Path(__file__).resolve().parent / "_state"
OUT.mkdir(parents=True, exist_ok=True)
SIG = OUT / "fx_signal.json"
YEAR = 2026
# pariteler: ccy -> (pair, sign) ; sign=+1 ise 'ccy LONG = pariteyi BUY', -1 ise 'ccy LONG = pariteyi SELL'
PAIR = {"EUR": ("EURUSD", +1), "GBP": ("GBPUSD", +1), "AUD": ("AUDUSD", +1), "NZD": ("NZDUSD", +1),
        "JPY": ("USDJPY", -1), "CAD": ("USDCAD", -1), "CHF": ("USDCHF", -1)}
RATE = {"USD": 3.75, "EUR": 2.25, "GBP": 4.0, "JPY": 0.75, "AUD": 3.6, "CAD": 2.75, "CHF": 0.25, "NZD": 3.25}
K = 2


def main():
    diff = {c: RATE[c] - RATE["USD"] for c in PAIR}     # USD'ye karşı carry (yıllık %)
    ranked = sorted(diff, key=diff.get, reverse=True)
    longs, shorts = ranked[:K], ranked[-K:]
    pos = []
    for c in longs:
        pair, sgn = PAIR[c]
        pos.append({"ccy": c, "carry_pct": round(diff[c], 2), "pair": pair,
                    "action": "BUY" if sgn > 0 else "SELL", "dir": f"LONG {c}"})
    for c in shorts:
        pair, sgn = PAIR[c]
        pos.append({"ccy": c, "carry_pct": round(diff[c], 2), "pair": pair,
                    "action": "SELL" if sgn > 0 else "BUY", "dir": f"SHORT {c}"})
    rec = {"ts": time.strftime("%Y-%m-%d %H:%M UTC"), "year": YEAR, "split": "long top-2 / short bottom-2 carry",
           "positions": pos,
           "note": "MANUEL FX carry — firma platformunda elle gir, her pozisyona stop-loss (~%2-3). "
                   "Yavaş sinyal (faiz değişince döner). MODEST faktör (~0.5 Sharpe) — prop-passer DEĞİL, "
                   "yavaş-gelir/diversifikasyon. Carry risk-off'ta sert düşebilir."}
    SIG.write_text(json.dumps(rec, ensure_ascii=False, indent=2))
    print(f"[{rec['ts']}] FX carry ({YEAR}):")
    for p in pos:
        print(f"  {p['dir']:10} → {p['pair']} {p['action']:4} (carry {p['carry_pct']:+.2f}%/yıl)")


if __name__ == "__main__":
    main()
