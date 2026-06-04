"""Build & cache the pooled candidate feature panel for the order-flow research.

Pools long-entry candidates across 20 coins with: base meta-label features +
the full order-flow velocity/acceleration bank + triple-barrier label. Saved once to
parquet so feature_lab.py (and the workflow agents) can test families fast.

Usage: python scripts/build_feature_panel.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from quantlab.config import load_config  # noqa: E402
from quantlab.data import cache, funding as fundmod, altdata  # noqa: E402
from quantlab.ml import dataset, features as featmod  # noqa: E402
from quantlab.ml.labels import triple_barrier_labels  # noqa: E402
from quantlab.research.orderflow import build_orderflow_features  # noqa: E402

MKTDATA = Path("../uyg/src/mktdata")
FUND = Path("../uyg/src/funddata")
FUNDX = Path("../uyg/src/xfunddata")
METRICS = Path("../uyg/src/metricsdata")
UNIVERSE = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LTC", "ATOM", "DOT",
            "LINK", "DOGE", "ETC", "FIL", "INJ", "NEAR", "UNI", "APT", "ARB", "OP"]


def main() -> None:
    cfg = load_config(str(Path(__file__).resolve().parents[1] / "config" / "default.yaml"))
    root = Path(__file__).resolve().parents[1]
    parts, families, base_cols = [], None, None
    for sym in UNIVERSE:
        csv = (root / MKTDATA / f"{sym}_USDT_4h.csv").resolve()
        if not csv.exists():
            continue
        df = cache.load_ohlcv(f"{sym}/USDT", "4h", cache_dir=root / cfg.data.cache_dir,
                              start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
        hd = cache.load_ohlcv(f"{sym}/USDT", "1d", cache_dir=root / cfg.data.cache_dir,
                              start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
        fundings = {}
        for exch, base in (("binance", FUND), ("bybit", FUNDX), ("okx", FUNDX)):
            fp = ((root / base / f"{sym}_funding.csv") if exch == "binance"
                  else (root / base / f"{exch}_{sym}_funding.csv")).resolve()
            if fp.exists():
                fundings[exch] = fundmod.load_funding(fp)
        oip = (root / METRICS / f"{sym}_metrics_4h.csv").resolve()
        oi_df = altdata.load_oi_metrics(oip) if oip.exists() else None

        base_feat = featmod.build_features(df, cfg, hd)
        of_feat, fam = build_orderflow_features(df, fundings, oi_df)
        X = pd.concat([base_feat, of_feat], axis=1)
        X = X.loc[:, ~X.columns.duplicated()]
        y = triple_barrier_labels(df, cfg)
        mask = dataset.candidate_long_mask(df, cfg, hd)
        sel = mask & y.notna()
        rows = X[sel].copy()
        rows["__y"] = y[sel].astype(int)
        rows["__ts"] = rows.index
        rows["__coin"] = sym
        parts.append(rows)
        base_cols = list(base_feat.columns)
        families = fam
        print(f"  {sym}: {int(sel.sum())} candidates")

    pooled = pd.concat(parts, ignore_index=True)
    out_dir = root / "reports_out"
    out_dir.mkdir(exist_ok=True)
    pooled.to_parquet(out_dir / "feature_panel.parquet")
    families["base"] = base_cols
    (out_dir / "feature_families.json").write_text(json.dumps(families, indent=2))
    print(f"\nSaved {len(pooled)} pooled candidates, "
          f"{pooled.shape[1]} cols -> {out_dir / 'feature_panel.parquet'}")
    print(f"Families: { {k: len(v) for k, v in families.items()} }")


if __name__ == "__main__":
    main()
