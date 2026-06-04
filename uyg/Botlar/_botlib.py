"""Shared loader for the Botlar/ strategies.

Each bot imports the quantlab research package (same checkout, repo-root /quantlab) and
loads the 20-coin 4h OHLCV + funding universe from uyg/src. Data files are gitignored,
so these run on a machine that has the local data (yours) — exactly as built/validated.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # repo root (…/trade)
sys.path.insert(0, str(ROOT / "quantlab"))          # make `quantlab` importable

MKTDATA = ROOT / "uyg/src/mktdata"
FUND = ROOT / "uyg/src/funddata"
CONFIG = ROOT / "quantlab/config/default.yaml"
CACHE = ROOT / "quantlab/data_cache"
UNIVERSE = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LTC", "ATOM", "DOT",
            "LINK", "DOGE", "ETC", "FIL", "INJ", "NEAR", "UNI", "APT", "ARB", "OP"]


def load_universe():
    """Return (cfg, frames, higher, targets, momentum, fundings) for the universe."""
    from quantlab.config import load_config
    from quantlab.data import cache, funding as fundmod
    from quantlab import orchestrator

    cfg = load_config(str(CONFIG))
    frames, higher, targets, momentum, fundings = {}, {}, {}, {}, {}
    for sym in UNIVERSE:
        csv = MKTDATA / f"{sym}_USDT_4h.csv"
        fp = FUND / f"{sym}_funding.csv"
        if not (csv.exists() and fp.exists()):
            continue
        df = cache.load_ohlcv(f"{sym}/USDT", "4h", cache_dir=CACHE,
                              start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
        hd = cache.load_ohlcv(f"{sym}/USDT", "1d", cache_dir=CACHE,
                              start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
        frames[sym], higher[sym] = df, hd
        targets[sym] = orchestrator.build_target(df, cfg, hd)
        momentum[sym] = df["close"].pct_change(60)
        fundings[sym] = fundmod.load_funding(fp)
    if not frames:
        raise SystemExit("No data found under uyg/src/mktdata + funddata. "
                         "These bots need the local data files (gitignored).")
    return cfg, frames, higher, targets, momentum, fundings
