#!/usr/bin/env python3
"""BOT 3 — HİSSE momentum manuel sinyali (Trade The Pool / hisse prop'ları için).

KANITLI edge (3-sleeve'in 3. kolu, OOS Sharpe 1.66, crypto'ya ortogonal). US likit büyük-cap'ler
arasında 90g momentum Top-5 LONG (Jegadeesh-Titman). Net giriş/stop/gerekçe + AÇ/TUT/KAPAT.
Yavaş sinyal (günlük). EMİR YOK — manuel gir. paper/equity_signal.json yazar; /hisse sekmesi gösterir.

⚠️ Büyüklük 2023-26 AI-boğası + survivorship ile şişkin; ileriye haircut'lı bekle. Long-only →
piyasa-yönü riski (genel düşüşte hepsi düşer); stop-loss ZORUNLU. yfinance internet ister.
"""
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

US = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "JPM", "V", "JNJ", "WMT",
      "PG", "XOM", "UNH", "HD", "MA", "BAC", "KO", "PEP", "CVX", "ABBV", "COST", "MRK",
      "AVGO", "PFE", "CSCO", "ADBE", "CRM", "NFLX", "AMD"]
TOP_K = 5
MOM_DAYS = 90
OUT = Path("/root/tirad/paper") if Path("/root/tirad/paper").exists() else Path(__file__).resolve().parent / "_state"
OUT.mkdir(parents=True, exist_ok=True)
SIG = OUT / "equity_signal.json"


def main():
    import yfinance as yf
    raw = yf.download(US, start="2024-06-01", end="2026-06-10", interval="1d", progress=False, auto_adjust=True)
    rows = {}
    for t in US:
        try:
            df = pd.DataFrame({"high": raw["High"][t], "low": raw["Low"][t], "close": raw["Close"][t]}).dropna()
        except Exception:  # noqa: BLE001
            continue
        if len(df) < MOM_DAYS + 30:
            continue
        mom = df["close"].iloc[-1] / df["close"].iloc[-MOM_DAYS] - 1
        ma200 = df["close"].rolling(200).mean().iloc[-1]
        uptrend = df["close"].iloc[-1] > ma200 if not np.isnan(ma200) else True
        tr = (df["high"] - df["low"]).rolling(14).mean().iloc[-1] / df["close"].iloc[-1]
        rows[t] = {"mom": float(mom), "uptrend": bool(uptrend), "atrp": float(tr), "px": float(df["close"].iloc[-1])}

    # uptrend + en yüksek 90g momentum Top-5 LONG
    elig = sorted([t for t in rows if rows[t]["uptrend"]], key=lambda t: rows[t]["mom"], reverse=True)[:TOP_K]
    prev = {}
    if SIG.exists():
        try:
            prev = {p["ticker"] for p in json.loads(SIG.read_text()).get("positions", [])}
        except Exception:  # noqa: BLE001
            prev = set()

    pos = []
    for t in elig:
        r = rows[t]
        stop_dist = float(min(max(r["atrp"] * 2.5, 0.04), 0.10))   # hisse: 4-10% stop bandı
        pos.append({"ticker": t, "side": "LONG", "entry": round(r["px"], 2),
                    "stop": round(r["px"] * (1 - stop_dist), 2), "stop_pct": round(stop_dist * 100, 1),
                    "mom90_pct": round(r["mom"] * 100, 1), "weight_pct": round(100 / TOP_K, 0),
                    "action": "TUT" if t in prev else "AÇ"})
    closes = [{"ticker": t, "action": "KAPAT"} for t in prev if t not in {p["ticker"] for p in pos}]

    rec = {"ts": time.strftime("%Y-%m-%d %H:%M UTC"), "universe": len(rows), "topk": TOP_K,
           "positions": pos, "closes": closes,
           "note": "MANUEL hisse momentum (long-only Top-5, 90g). Firma platformunda elle gir, her "
                   "pozisyona stop-loss (~%4-10) ZORUNLU. Sinyalden çıkana (KAPAT) kadar tut. Long-only "
                   "→ genel piyasa düşüşünde hepsi düşer (piyasa-yönü riski)."}
    SIG.write_text(json.dumps(rec, ensure_ascii=False, indent=2))
    print(f"[{rec['ts']}] {len(pos)} LONG, {len(closes)} kapat (evren {len(rows)})")
    for p in pos:
        print(f"  {p['action']:4} LONG {p['ticker']:6} giriş ${p['entry']} stop ${p['stop']} "
              f"(%{p['stop_pct']}) mom90 {p['mom90_pct']:+.0f}%")
    for c in closes:
        print(f"  KAPAT {c['ticker']}")


if __name__ == "__main__":
    main()
