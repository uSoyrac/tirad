#!/usr/bin/env python3
"""MANUEL-DOSTU SİNYAL üreticisi — bot-yasaklı firmalar için 'bugün şunları al/sat' listesi.

combo edge'ini (Top-3 momentum + funding long/short) düşük-frekans, net giriş/stop/gerekçeli
bir MANUEL işlem listesine çevirir. Dün ile karşılaştırıp aksiyon der (AÇ/TUT/KAPAT) → minimum
manuel işlem. paper/signal.json yazar; /sinyal sekmesi gösterir. EMİR YOK — sen elle girersin.

Çalıştırma (günlük cron): cd /root/tirad/uyg/Botlar && TIRAD_LIVE=1 \
    /root/tirad/.venv/bin/python /root/tirad/uyg/Botlar/signal_report.py
"""
import json
import time
from pathlib import Path

from hyro_executor import compute_targets   # aynı combo hedef mantığı

OUT = Path("/root/tirad/paper") if Path("/root/tirad/paper").exists() else Path(__file__).resolve().parent / "_state"
OUT.mkdir(parents=True, exist_ok=True)
SIG = OUT / "signal.json"
PER_TRADE_RISK = 0.03
ATR_STOP_MULT = 2.0


def main():
    w, atrp, px, asof, low_vol = compute_targets()
    prev = {}
    if SIG.exists():
        try:
            prev = {p["coin"]: p for p in json.loads(SIG.read_text()).get("positions", [])}
        except Exception:  # noqa: BLE001
            prev = {}

    positions = []
    for coin, wt in sorted(w.items(), key=lambda x: -abs(x[1])):
        side = "LONG" if wt > 0 else "SHORT"
        stop_dist = min(max(atrp.get(coin, 0.02) * ATR_STOP_MULT, 1e-4), PER_TRADE_RISK)
        entry = px.get(coin, 0.0)
        stop = entry * (1 - stop_dist) if wt > 0 else entry * (1 + stop_dist)
        # momentum mu funding mu? (kaba: weight işareti + büyüklük)
        rationale = "momentum+funding" if abs(wt) > 0.2 else ("funding-long" if wt > 0 else "funding-short")
        action = "TUT" if (coin in prev and prev[coin]["side"] == side) else "AÇ"
        positions.append({"coin": coin, "side": side, "entry": round(entry, 6),
                          "stop": round(stop, 6), "stop_pct": round(stop_dist * 100, 1),
                          "weight_pct": round(abs(wt) * 100, 1), "rationale": rationale, "action": action})
    cur = {p["coin"] for p in positions}
    closes = [{"coin": c, "side": prev[c]["side"], "action": "KAPAT"} for c in prev if c not in cur]

    rec = {"ts": time.strftime("%Y-%m-%d %H:%M UTC"), "asof": asof,
           "regime": "SAKİN (tam risk)" if low_vol else "TÜRBÜLANS (riski yarıla/bekle)",
           "n_pos": len(positions), "positions": positions, "closes": closes,
           "note": "MANUEL işlem listesi — firma platformunda elle gir. Stop-loss ZORUNLU (≤%3). "
                   "Pozisyonu sinyal listeden çıkana (KAPAT) kadar tut. Düşük-vol günde challenge başlat."}
    SIG.write_text(json.dumps(rec, ensure_ascii=False, indent=2))
    print(f"[{rec['ts']}] {len(positions)} pozisyon, {len(closes)} kapat, rejim={rec['regime']}")
    for p in positions:
        print(f"  {p['action']:4} {p['side']:5} {p['coin']:6} giriş {p['entry']} stop {p['stop']} "
              f"(%{p['stop_pct']} risk) ağırlık %{p['weight_pct']}")
    for c in closes:
        print(f"  KAPAT {c['side']:5} {c['coin']}")


if __name__ == "__main__":
    main()
