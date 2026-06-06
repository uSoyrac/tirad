"""LIVE perp screener — 24h hacim Δ, Open Interest Δ, funding Δ (en çok artan/düşen) + funding-flip.

Funding-squeeze tezini beslemek için: yüksek-|funding| (kalabalık) coinleri ve funding'in TERS
DÖNDÜĞÜ (flip) anları tespit eder. Read-only (ccxt public). Emir YOK.

Metrikler (Binance USDT-perp, top-N hacim):
  • vol_surge   = son-gün hacmi / önceki 7-gün ort. (>1 artıyor)
  • oi_chg_24h  = OI 24s değişimi %
  • funding_now = anlık 8s funding (bps), funding_chg_24h = 24s funding değişimi (bps)
  • flip        = funding işareti son 24s'te değişti mi (squeeze adayı)

Usage: python scripts/screener.py [N]
"""

from __future__ import annotations

import sys
import time
import warnings

warnings.filterwarnings("ignore")


def _ex():
    import ccxt
    return ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "future"}})


def main(n=30):
    ex = _ex()
    print("Piyasa yükleniyor…", flush=True)
    m = ex.load_markets()
    tk = ex.fetch_tickers()
    # top-N USDT perp by 24h quote volume
    cand = []
    for s, v in m.items():
        if not (v.get("swap") and v.get("quote") == "USDT" and v.get("active")):
            continue
        if v.get("base", "").endswith(("UP", "DOWN", "BULL", "BEAR")):
            continue
        qv = (tk.get(s) or {}).get("quoteVolume") or 0
        cand.append((s, v.get("base", s), qv))
    cand.sort(key=lambda x: x[2], reverse=True)
    cand = cand[:n]
    print(f"Top {len(cand)} likit perp taranıyor (hacim/OI/funding)…", flush=True)

    rows = []
    for sym, base, qv in cand:
        row = {"base": base, "qv": qv, "px_chg": (tk.get(sym) or {}).get("percentage")}
        # vol surge (daily)
        try:
            d = ex.fetch_ohlcv(sym, "1d", limit=9)
            vols = [c[5] for c in d]
            if len(vols) >= 8:
                row["vol_surge"] = vols[-1] / (sum(vols[-8:-1]) / 7 or 1e-9)
        except Exception:  # noqa: BLE001
            pass
        # OI 24h change
        try:
            oi = ex.fetch_open_interest_history(sym, "1h", limit=25)
            if len(oi) >= 25:
                a = oi[-1].get("openInterestValue") or oi[-1].get("openInterestAmount")
                b = oi[-25].get("openInterestValue") or oi[-25].get("openInterestAmount")
                if a and b:
                    row["oi_chg"] = (a / b - 1) * 100
        except Exception:  # noqa: BLE001
            pass
        # funding now + 24h change + flip
        try:
            fh = ex.fetch_funding_rate_history(sym, limit=6)
            if len(fh) >= 4:
                now = fh[-1]["fundingRate"] * 1e4          # bps
                prev = fh[-4]["fundingRate"] * 1e4         # ~24h ago (3x8h)
                row["fund_now"] = now
                row["fund_chg"] = now - prev
                row["flip"] = (now > 0) != (prev > 0)
        except Exception:  # noqa: BLE001
            pass
        rows.append(row)
        time.sleep(ex.rateLimit / 1000)

    def top(key, rev, k=8, fmt="{:+.1f}"):
        vals = [r for r in rows if r.get(key) is not None]
        vals.sort(key=lambda r: r[key], reverse=rev)
        return " | ".join(f"{r['base']} {fmt.format(r[key])}" for r in vals[:k])

    out = ["# LIVE perp screener (Binance USDT-perp)", f"as-of {time.strftime('%Y-%m-%d %H:%M UTC')}", "",
           "## 24h HACİM en çok ARTAN (vol_surge = son gün / 7g ort)", "  " + top("vol_surge", True, fmt="x{:.1f}"),
           "## 24h HACİM en çok DÜŞEN", "  " + top("vol_surge", False, fmt="x{:.1f}"), "",
           "## OPEN INTEREST en çok ARTAN (24s %)", "  " + top("oi_chg", True),
           "## OPEN INTEREST en çok DÜŞEN", "  " + top("oi_chg", False), "",
           "## FUNDING en çok ARTAN (24s Δ bps)", "  " + top("fund_chg", True),
           "## FUNDING en çok DÜŞEN", "  " + top("fund_chg", False), "",
           "## EN YÜKSEK funding (kalabalık LONG — fade/short adayı, bps/8h)", "  " + top("fund_now", True),
           "## EN DÜŞÜK funding (kalabalık SHORT — long adayı, bps/8h)", "  " + top("fund_now", False), "",
           "## ⚡ FUNDING FLIP (son 24s işaret değişti — SQUEEZE adayı)",
           "  " + (" | ".join(f"{r['base']} ({r['fund_now']:+.1f}bps)" for r in rows if r.get("flip")) or "(yok)"), "",
           "Tez: yüksek-|funding| = kalabalık; funding TERS dönünce farmer'lar unwind → yön hareketi.",
           "Flip + bizim trend/funding sinyaliyle UYUMLU ise işlem adayı. (Backtest: run_funding_flip.py)"]
    report = "\n".join(out)
    print("\n" + report)
    from pathlib import Path
    Path(__file__).resolve().parents[1].joinpath("reports_out", "screener.md").write_text(report)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 30)
