"""Read the TIRAD live dashboard (server-rendered) and parse per-bot status.

READ-ONLY. Credentials come from env (TIRAD_URL / TIRAD_USER / TIRAD_PASS) — never
hardcode a password in the repo. The dashboard has no JSON API (Flask HTML), so we parse
the rendered text: each bot row carries NAV, Sharpe, MaxDD, as-of date, and target
positions. Used by scripts/watch_live.py to report live decisions + health.
"""

from __future__ import annotations

import os
import re
import warnings
from dataclasses import dataclass

warnings.filterwarnings("ignore")

_METRIC = re.compile(
    r"\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})\s*→?\s*NAV\s+([+-][\d.]+)%\s+"
    r"Sharpe\s+([\d.]+)\s+MaxDD\s+([+-][\d.]+)%\s+as-of\s+(\d{4}-\d{2}-\d{2})"
    r"(.*?)(?=\$[\d,]+\.\d{2}\s+\$[\d,]+\.\d{2}|$)", re.S)


@dataclass
class BotLive:
    label: str
    nav: float
    start: float
    nav_pct: float
    sharpe: float
    maxdd: float
    as_of: str
    targets: str
    stale_days: int  # days since as-of vs the latest as-of seen (proxy for "not updating")


def _to_text(html: str) -> str:
    h = re.sub(r"<(script|style).*?</\1>", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h)).strip()


def fetch_dashboard(url: str | None = None, user: str | None = None, pw: str | None = None) -> str:
    import requests
    url = url or os.environ.get("TIRAD_URL", "https://tirad.45.143.11.97.nip.io/")
    user = user or os.environ.get("TIRAD_USER", "")
    pw = pw or os.environ.get("TIRAD_PASS", "")
    r = requests.get(url, auth=(user, pw), verify=False, timeout=25,
                     allow_redirects=True)
    r.raise_for_status()
    return r.text


# Cards render in a stable order — map by index (far more robust than slicing names out
# of the flattened text). Update if the dashboard reorders/adds bots.
_ORDER = [
    "Combo (Trend+Funding) [quantlab]", "Dengeli 1.25x [compound]",
    "Market-Nötr Funding [quantlab]", "Kararlı %60 [compound]",
    "Dinamik Kelly ≤10x [Gemini]", "Optimal ≤2.5x [compound]",
    "Rejim oto-ayar [compound]", "Çapraz-Varlık 3-kol ★ [quantlab]",
    "Cross-Sectional Momentum [quantlab]",
]


def parse_bots(html: str) -> list[BotLive]:
    text = _to_text(html)
    bots: list[BotLive] = []
    matches = list(_METRIC.finditer(text))
    for i, m in enumerate(matches):
        nav, start, navp, shp, mdd, asof, tail = m.groups()
        label = _ORDER[i] if i < len(_ORDER) else f"bot_{i}"
        if "yok" in tail.lower():
            tgt = "(pozisyon yok)"
        else:
            ticks = re.findall(r"\b[A-Z]{2,6}\b", tail.split("Hedefler:")[-1])
            tgt = " ".join(ticks[:6]) if ticks else "—"
        bots.append(BotLive(label=label, nav=float(nav.replace(",", "")),
                            start=float(start.replace(",", "")), nav_pct=float(navp),
                            sharpe=float(shp), maxdd=float(mdd), as_of=asof,
                            targets=tgt, stale_days=0))
    # stale_days: relative to the freshest as-of on the board
    if bots:
        latest = max(b.as_of for b in bots)
        ly, lm, ld = (int(x) for x in latest.split("-"))
        for b in bots:
            y, mo, d = (int(x) for x in b.as_of.split("-"))
            b.stale_days = (ly - y) * 365 + (lm - mo) * 30 + (ld - d)
    return bots
