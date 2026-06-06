"""REJİM-ANAHTARLAMA — trend rejiminde trend-takip, chop rejiminde mean-reversion.

Kullanıcı tezi: trend hacimliyse trend-botu, chop'ta chop-stratejisi (MR). Boş durmak da seçenek.
Per-coin per-bar rejim: ADX>25 → TREND (Donchian+Supertrend yönsel), ADX≤25 → CHOP (z-score fade, MR).
Karşılaştır: always-trend (chop'ta flat) · always-MR · SWITCHED (trend+MR) · flat-in-chop.
Switched, parçaları ve özellikle chop-yılı (2025) kanamasını telafi ediyor mu?

Usage: python scripts/run_regime_switch.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from quantlab.config import load_config  # noqa: E402
from quantlab.data import cache  # noqa: E402
from quantlab.indicators import atr, adx, supertrend, donchian  # noqa: E402

MKTDATA = Path("../uyg/src/mktdata")
UNIVERSE = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LTC", "ATOM", "DOT",
            "LINK", "DOGE", "ETC", "FIL", "INJ", "NEAR", "UNI", "APT", "ARB", "OP"]
CUT = pd.Timestamp("2025-01-01")
PPY = 252
ADX_TREND = 25
COST = 0.0007
RISK = 0.004


def coin_trades(df, btc_dir_at, mode):
    """mode: 'trend' (ADX>25 yönsel) | 'mr' (ADX≤25 fade) | 'switch' (her ikisi rejime göre)."""
    c = df["close"].to_numpy(float)
    hi, lo = df["high"].to_numpy(float), df["low"].to_numpy(float)
    at = atr(df, 14).to_numpy()
    st = supertrend(df, period=10, multiplier=3.0)["dir"].to_numpy()
    dch = donchian(df, 40)
    up, dn = dch["upper"].to_numpy(), dch["lower"].to_numpy()
    ax = adx(df, 14)
    ax = (ax[0] if isinstance(ax, tuple) else ax)
    ax = ax.to_numpy() if hasattr(ax, "to_numpy") else np.asarray(ax)
    ma = pd.Series(c).rolling(20).mean().to_numpy()
    sd = pd.Series(c).rolling(20).std().to_numpy()
    rows = []
    i = 50
    while i < len(df) - 1:
        is_trend = np.isfinite(ax[i]) and ax[i] > ADX_TREND
        entry = c[i]
        d = 0
        sl_dist = tp_dist = 0.0
        if mode in ("trend", "switch") and is_trend and at[i] > 0:
            don = 1 if c[i] >= up[i - 1] else (-1 if c[i] <= dn[i - 1] else 0)
            sti = int(st[i]) if np.isfinite(st[i]) else 0
            dd = don if (don != 0 and don == sti) else 0
            if dd != 0 and dd == btc_dir_at[i]:
                d, sl_dist, tp_dist = dd, 2.0 * at[i] / entry, 2.75 * 2.0 * at[i] / entry
        if d == 0 and mode in ("mr", "switch") and (not is_trend) and np.isfinite(sd[i]) and sd[i] > 0:
            z = (c[i] - ma[i]) / sd[i]
            if z > 1.5:
                d, sl_dist, tp_dist = -1, 0.02, abs(c[i] - ma[i]) / entry   # short, hedef=ortalama
            elif z < -1.5:
                d, sl_dist, tp_dist = 1, 0.02, abs(ma[i] - c[i]) / entry
            tp_dist = max(min(tp_dist, 0.06), 0.01)
        if d != 0 and 0.003 < sl_dist < 0.12:
            sl = entry - d * sl_dist * entry
            tp = entry + d * tp_dist * entry
            for j in range(i + 1, min(i + 60, len(df))):
                if d == 1:
                    hit = -sl_dist if lo[j] <= sl else (tp_dist if hi[j] >= tp else None)
                else:
                    hit = -sl_dist if hi[j] >= sl else (tp_dist if lo[j] <= tp else None)
                if hit is not None:
                    rows.append((df.index[j], (hit / sl_dist) - COST * 2 / sl_dist))
                    i = j
                    break
            else:
                k = min(i + 60, len(df) - 1)
                rows.append((df.index[k], d * (c[k] - entry) / entry / sl_dist - COST * 2 / sl_dist))
                i = k
        i += 1
    return rows


def daily_stream(frames, bdir, mode):
    rows = []
    for coin, df in frames.items():
        rows += coin_trades(df, bdir, mode)
    tr = pd.DataFrame(rows, columns=["ts", "r"])
    if tr.empty:
        return pd.Series(dtype=float)
    tr["date"] = tr["ts"].dt.normalize()
    return (tr.groupby("date")["r"].sum() * RISK)


def _stats(r):
    if len(r) < 2:
        return float("nan"), float("nan")
    eq = (1 + r).cumprod()
    return float(r.mean() / r.std() * np.sqrt(PPY)) if r.std() > 0 else 0.0, float((eq / eq.cummax() - 1).min())


def main():
    cfg = load_config(str(Path(__file__).resolve().parents[1] / "config" / "default.yaml"))
    root = Path(__file__).resolve().parents[1]
    frames = {}
    for s in UNIVERSE:
        csv = (root / MKTDATA / f"{s}_USDT_4h.csv").resolve()
        if csv.exists():
            frames[s] = cache.load_ohlcv(f"{s}/USDT", "4h", cache_dir=root / cfg.data.cache_dir,
                                         start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
    bdir = np.where(frames["BTC"]["close"].to_numpy(float) >
                    frames["BTC"]["close"].ewm(span=200, adjust=False).mean().to_numpy(), 1, -1)
    streams = {m: daily_stream(frames, bdir, m) for m in ("trend", "mr", "switch")}

    lines = ["# REJİM-ANAHTARLAMA — trend(ADX>25) + mean-reversion(ADX≤25)", "",
             f"{len(frames)} coin. ADX>25→trend yönsel, ADX≤25→z-fade MR. risk-frac {RISK}.", "",
             "| strateji | OOS Sharpe | OOS MaxDD | 2024 Sh | 2025 Sh | 2026 Sh |", "|---|---|---|---|---|---|"]
    for m, s in streams.items():
        o = s[s.index >= CUT]
        sh, md = _stats(o)
        def ysh(yr): return _stats(s[s.index.year == yr])[0]
        lines.append(f"| {m} | {sh:.2f} | {md*100:.0f}% | {ysh(2024):.2f} | {ysh(2025):.2f} | {ysh(2026):.2f} |")

    st_sh = _stats(streams["switch"][streams["switch"].index >= CUT])[0]
    tr_sh = _stats(streams["trend"][streams["trend"].index >= CUT])[0]
    mr_sh = _stats(streams["mr"][streams["mr"].index >= CUT])[0]
    lines += ["", "## Yorum (dürüst)", ""]
    if st_sh > max(tr_sh, mr_sh) + 0.1:
        lines.append(f"**REJİM-ANAHTARLAMA İŞE YARADI: switch OOS Sharpe {st_sh:.2f} > trend {tr_sh:.2f} / "
                     f"MR {mr_sh:.2f}.** Trendde trend + chop'ta MR, parçaları geçti — senin tezin DOĞRU. "
                     "2025 (chop) MR ile telafi edildiyse (tabloya bak) bu gerçek bir gelişme.")
    else:
        lines.append(f"**Anahtarlama parçaları GEÇMEDİ: switch {st_sh:.2f} vs trend {tr_sh:.2f} / MR {mr_sh:.2f}.** "
                     "Rejim-tespiti (ADX) GECİKMELİ — chop'a 'trend' derken whipsaw, trend'e 'chop' derken "
                     "MR ters trende girer. 2025 tablosu telafi olup olmadığını gösterir. Sorun: ADX rejimi "
                     "gerçek-zamanda temiz ayıramıyor (lagging). Combo nötrlüğü hâlâ daha iyi.")
    lines.append("- ⚠️ Rejim eşiği (ADX25) ilkesel; MR tek-bacak basit. Tek-dönem. Asıl mesaj: rejim-tespiti "
                 "yeterince keskin mi? 2025 sütununa bak — switch orada pozitifse tez güçlü.")
    report = "\n".join(lines)
    print(report)
    (root / "reports_out" / "regime_switch.md").write_text(report)


if __name__ == "__main__":
    main()
