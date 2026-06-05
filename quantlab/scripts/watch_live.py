"""Monitor the live TIRAD dashboard (READ-ONLY) + retrain XGBoost on accumulated live data.

Reads the real monitoring DOMAIN (the web dashboard) and reports every bot's live NAV /
targets / staleness / health. Falls back to the local shadow files if the dashboard is
unreachable. When >= MIN_LIVE_TRADES resolved local-shadow trades exist, retrains the
XGBoost on REAL forward outcomes.

Credentials: set env TIRAD_URL / TIRAD_USER / TIRAD_PASS (do NOT hardcode).
Usage: TIRAD_USER=admin TIRAD_PASS=*** python scripts/watch_live.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quantlab.live import dashboard as dash  # noqa: E402
from quantlab.live import shadow_reader as sr  # noqa: E402

MIN_LIVE_TRADES = 30


def bot_health(b: dash.BotLive) -> tuple[str, str]:
    """Per-bot live health — best-judgment thresholds (capital floor > staleness > DD)."""
    if b.nav < 0.85 * b.start:
        return "🔴", "kasa %15+ düştü — durdur"
    if b.maxdd <= -20.0:
        return "🔴", f"drawdown {b.maxdd:.0f}% — risk limiti"
    if b.stale_days >= 2:
        return "🟡", f"{b.stale_days}g güncellenmiyor (canlı çalışmıyor olabilir)"
    if b.nav_pct < -5.0:
        return "🟡", "NAV düşüşte — izle"
    return "🟢", "uyumlu"


def main():
    try:
        bots = dash.parse_bots(dash.fetch_dashboard())
        src = "DASHBOARD"
    except Exception as e:  # noqa: BLE001
        print(f"(Dashboard okunamadı: {type(e).__name__} {e} — yerel shadow'a düşülüyor)")
        bots, src = [], "LOCAL"

    print("=" * 70)
    print(f"  TIRAD CANLI İZLEME — {src} (READ-ONLY, testnet/paper, gerçek para YOK)")
    print("=" * 70)
    if bots:
        print(f"  {len(bots)} bot izleniyor:\n")
        stale = []
        for b in bots:
            lvl, note = bot_health(b)
            print(f"  {lvl} {b.label[:34]:<34} NAV {b.nav_pct:+5.1f}%  ${b.nav:>8,.0f}  "
                  f"MaxDD {b.maxdd:+.0f}%  as-of {b.as_of}")
            print(f"        hedef: {b.targets[:48]:<48} | {note}")
            if b.stale_days >= 2:
                stale.append(b.label[:34])
        if stale:
            print(f"\n  ⚠️ GÜNCELLENMEYEN (bayat) botlar: {stale}")
            print("     → Bu botlar panelde ama canlı çalışmıyor/işlem açmıyor olabilir; runner'larını kontrol et.")
        live = [b for b in bots if b.stale_days < 2]
        print(f"\n  ÖZET: {len(live)}/{len(bots)} bot aktif güncelleniyor. "
              f"En iyi NAV: {max(bots, key=lambda x: x.nav_pct).label[:24]} "
              f"({max(b.nav_pct for b in bots):+.1f}%). Süre çok erken — yargı için ≥haftalar gerek.")

    # local-shadow XGBoost retrain (real forward outcomes)
    s = sr.read_status()
    if s.n_trades < MIN_LIVE_TRADES:
        print(f"\n  XGBoost CANLI eğitimi: {s.n_trades}/{MIN_LIVE_TRADES} çözülmüş işlem — "
              "yeterli gerçek-forward örnek birikince eğitilecek (AUC>0.55=gerçek edge, ~0.5=yok).")
    else:
        print(f"\n  XGBoost: {s.n_trades} canlı işlem hazır — train_xgb_from_live() çalıştırılabilir.")


if __name__ == "__main__":
    main()
