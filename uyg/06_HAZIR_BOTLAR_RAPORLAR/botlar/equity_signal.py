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
ACCOUNT = 5000.0       # Trade The Pool Flex 5K
TARGET_VOL = 0.06      # portföy yıllık vol-hedefi (%4 DD'ye güvenli; pass sweet-spot)
DD_LIMIT = 0.04        # TTP max DD (statik)
DAILY_LIMIT = 0.02     # TTP günlük
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
        dvol = df["close"].pct_change().tail(20).std()
        rows[t] = {"mom": float(mom), "uptrend": bool(uptrend), "atrp": float(tr),
                   "px": float(df["close"].iloc[-1]), "vol": float(dvol * np.sqrt(252))}

    # uptrend + en yüksek 90g momentum Top-5 LONG
    elig = sorted([t for t in rows if rows[t]["uptrend"]], key=lambda t: rows[t]["mom"], reverse=True)[:TOP_K]
    prev = {}
    if SIG.exists():
        try:
            prev = {p["ticker"] for p in json.loads(SIG.read_text()).get("positions", [])}
        except Exception:  # noqa: BLE001
            prev = set()

    # RİSK-BÜTÇESİ boyutlandırma: toplam stop-riski = DD-bütçesinin %70'i (tampon bırak)
    dd_budget = ACCOUNT * DD_LIMIT
    risk_per_pos = (0.70 * dd_budget) / max(1, len(elig))
    pos = []
    total_risk = total_usd = 0.0
    for t in elig:
        r = rows[t]
        stop_dist = float(min(max(r["atrp"] * 2.5, 0.04), 0.10))   # hisse: 4-10% stop bandı
        exposure = risk_per_pos / stop_dist                         # stop → sabit $ risk
        shares = round(exposure / r["px"], 2) if r["px"] > 0 else 0  # KESİRLİ (TTP/broker destekler)
        usd = round(shares * r["px"], 0)
        total_risk += risk_per_pos
        total_usd += usd
        pos.append({"ticker": t, "side": "LONG", "entry": round(r["px"], 2),
                    "stop": round(r["px"] * (1 - stop_dist), 2), "stop_pct": round(stop_dist * 100, 1),
                    "shares": shares, "usd": usd, "risk_usd": round(risk_per_pos, 0),
                    "mom90_pct": round(r["mom"] * 100, 1), "action": "TUT" if t in prev else "AÇ"})
    closes = [{"ticker": t, "action": "KAPAT"} for t in prev if t not in {p["ticker"] for p in pos}]

    rec = {"ts": time.strftime("%Y-%m-%d %H:%M UTC"), "universe": len(rows), "topk": TOP_K,
           "account": ACCOUNT, "deployed_usd": round(total_usd, 0), "target_vol": TARGET_VOL,
           "total_risk_usd": round(total_risk, 0), "dd_budget_usd": round(dd_budget, 0),
           "risk_ok": bool(total_risk <= dd_budget), "positions": pos, "closes": closes,
           "note": f"TRADE THE POOL ${ACCOUNT:.0f} hisse challenge — MANUEL. Her satırdaki ADET'i al, "
                   f"STOP'u koy (ZORUNLU). Toplam-risk ${total_risk:.0f} / DD-bütçesi ${dd_budget:.0f} "
                   f"(%4) → {'GÜVENLİ ✓' if total_risk <= dd_budget else 'AŞIYOR ⚠️ azalt'}. "
                   "Hedef +%6, günlük -%2, toplam -%4 statik. Sinyalden çıkana (KAPAT) kadar tut. "
                   "Long-only → piyasa geneli düşerse hepsi düşer."}
    SIG.write_text(json.dumps(rec, ensure_ascii=False, indent=2))
    print(f"[{rec['ts']}] {len(pos)} LONG | deploy ${total_usd:.0f}/${ACCOUNT:.0f} | "
          f"toplam-risk ${total_risk:.0f}/${dd_budget:.0f} DD-bütçe {'✓' if total_risk <= dd_budget else '⚠️'}")
    for p in pos:
        print(f"  {p['action']:4} {p['ticker']:6} {p['shares']:4}adet ${p['usd']:.0f} @ ${p['entry']} "
              f"stop ${p['stop']} (risk ${p['risk_usd']:.0f}) mom90 {p['mom90_pct']:+.0f}%")
    for c in closes:
        print(f"  KAPAT {c['ticker']}")


if __name__ == "__main__":
    main()
