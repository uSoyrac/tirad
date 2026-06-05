#!/usr/bin/env python3
"""TIRAD sağlık snapshot — paper/*.json'ı okur, canlı↔backtest sapma sağlığını
hesaplar, health.log'a satır + paper/health.json yazar. Auth/HTTP gerektirmez.
Cron: her 4 saatte (paper_runner'dan sonra). Eklenme: Claude."""
import glob
import json
import time

PAPER = "/root/tirad/paper"


def health(b):
    s = b.get("stats") or {}
    ref = b.get("ref") or {}
    se = float(b.get("start_eq") or 1000.0)
    nav = float(s.get("navnow", se))
    navpct = (nav / se - 1.0) * 100.0 if se else 0.0
    days = int(s.get("days", 0) or 0)
    curve = [float(p.get("v", se)) for p in (b.get("nav") or []) if isinstance(p, dict)]
    live_mdd, peak = 0.0, (curve[0] if curve else se)
    for v in curve:
        peak = max(peak, v)
        live_mdd = min(live_mdd, v / peak - 1.0)
    live_mdd *= 100.0
    ref_mdd = (ref.get("oos_maxdd") or 0.0) * 100.0
    if nav < 0.85 * se:
        return "RED", f"kasa %15+ dustu (${nav:.0f})"
    if days >= 3 and ref_mdd < 0 and live_mdd <= ref_mdd * 1.5:
        return "RED", f"drawdown backtest'i asti ({live_mdd:.0f}% vs {ref_mdd:.0f}%)"
    if days < 5:
        return "GREEN", f"erken ({days}g)"
    if days >= 3 and ref_mdd < 0 and live_mdd <= ref_mdd:
        return "YELLOW", f"drawdown backtest seviyesinde ({live_mdd:.0f}%)"
    if navpct < -8.0:
        return "YELLOW", f"NAV beklenti alti ({navpct:+.1f}%)"
    return "GREEN", "uyumlu"


def main():
    out = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "bots": [], "GREEN": 0, "YELLOW": 0, "RED": 0}
    for p in sorted(glob.glob(PAPER + "/*.json")):
        if p.endswith("health.json"):
            continue
        try:
            b = json.load(open(p))
        except Exception:
            continue
        lvl, reason = health(b)
        out[lvl] = out.get(lvl, 0) + 1
        out["bots"].append({"key": b.get("key"), "level": lvl, "reason": reason,
                            "navnow": (b.get("stats") or {}).get("navnow")})
    json.dump(out, open(PAPER + "/health.json", "w"), ensure_ascii=False, indent=2)
    line = (f"{out['ts']} | GREEN {out['GREEN']} YELLOW {out['YELLOW']} RED {out['RED']} | "
            + "; ".join(f"{x['key']}:{x['level']}" for x in out["bots"]))
    with open("/root/tirad/health.log", "a") as f:
        f.write(line + "\n")
    print(line)


if __name__ == "__main__":
    main()
