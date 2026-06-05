"""ADX-filtreli YÖNSEL TREND sleeve'ini combo'ya ekle — kombine kitaba değer katıyor mu?

Yönsel trend (Donchian+Supertrend+BTC-dir, ADX≥30) per-trade R'lerini günlük getiri akışına
çevir; combo (crypto-trend Top-3 + funding) ile inverse-vol harmanla. combo vs combo+trend:
OOS Sharpe + yıl-bazı + MaxDD. Trend getiriyi mi katıyor yoksa varyans mı?

Usage: python scripts/run_trend_combine.py [risk_frac]
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
from quantlab.indicators import atr, adx, supertrend, donchian, efficiency_ratio  # noqa: E402

MKTDATA = Path("../uyg/src/mktdata")
SLEEVE3 = Path(__file__).resolve().parents[1] / "reports_out" / "_sleeves3.parquet"
UNIVERSE = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LTC", "ATOM", "DOT",
            "LINK", "DOGE", "ETC", "FIL", "INJ", "NEAR", "UNI", "APT", "ARB", "OP"]
CUT = pd.Timestamp("2025-01-01")
PPY = 252
SL_ATR, TP_R, COST = 2.0, 2.75, 0.0007
ADX_MIN = 30
RISK_FRAC = float(sys.argv[1]) if len(sys.argv) > 1 else 0.005   # trade başına risk (sleeve içi)


def trend_daily(frames):
    """ADX≥30 yönsel trend → günlük getiri akışı (per-trade R'leri exit gününde topla)."""
    bd = np.where(frames["BTC"]["close"].to_numpy(float) >
                  frames["BTC"]["close"].ewm(span=200, adjust=False).mean().to_numpy(), 1, -1)
    rows = []
    for coin, df in frames.items():
        c = df["close"].to_numpy(float)
        hi, lo = df["high"].to_numpy(float), df["low"].to_numpy(float)
        at = atr(df, 14).to_numpy()
        st = supertrend(df, period=10, multiplier=3.0)["dir"].to_numpy()
        dch = donchian(df, 40)
        up, dn = dch["upper"].to_numpy(), dch["lower"].to_numpy()
        ax = adx(df, 14)
        ax = (ax[0] if isinstance(ax, tuple) else ax)
        ax = ax.to_numpy() if hasattr(ax, "to_numpy") else np.asarray(ax)
        _ = efficiency_ratio(df, 20)
        i = 50
        while i < len(df) - 1:
            don = 1 if c[i] >= up[i - 1] else (-1 if c[i] <= dn[i - 1] else 0)
            sti = int(st[i]) if np.isfinite(st[i]) else 0
            d = don if (don != 0 and don == sti) else 0
            if d != 0 and d == bd[i] and at[i] > 0 and np.isfinite(ax[i]) and ax[i] >= ADX_MIN:
                entry = c[i]
                sld = SL_ATR * at[i] / entry
                if not (0.003 < sld < 0.12):
                    i += 1
                    continue
                sl, tp = entry - d * SL_ATR * at[i], entry + d * TP_R * SL_ATR * at[i]
                for j in range(i + 1, min(i + 60, len(df))):
                    if d == 1:
                        hit = -sld if lo[j] <= sl else (TP_R * sld if hi[j] >= tp else None)
                    else:
                        hit = -sld if hi[j] >= sl else (TP_R * sld if lo[j] <= tp else None)
                    if hit is not None:
                        rows.append((df.index[j], hit / sld - COST * 2 / sld))
                        i = j
                        break
                else:
                    k = min(i + 60, len(df) - 1)
                    rows.append((df.index[k], d * (c[k] - entry) / entry / sld - COST * 2 / sld))
                    i = k
            i += 1
    tr = pd.DataFrame(rows, columns=["ts", "r"])
    tr["date"] = tr["ts"].dt.normalize()
    daily_r = tr.groupby("date")["r"].sum() * RISK_FRAC      # günlük R-toplamı × risk
    return daily_r


def _stats(r):
    eq = (1 + r).cumprod()
    sh = float(r.mean() / r.std() * np.sqrt(PPY)) if r.std() > 0 else float("nan")
    cg = eq.iloc[-1] ** (PPY / len(r)) - 1 if len(r) else np.nan
    md = float((eq / eq.cummax() - 1).min()) if len(r) else np.nan
    return sh, cg, md


def main():
    cfg = load_config(str(Path(__file__).resolve().parents[1] / "config" / "default.yaml"))
    root = Path(__file__).resolve().parents[1]
    frames = {}
    for s in UNIVERSE:
        csv = (root / MKTDATA / f"{s}_USDT_4h.csv").resolve()
        if csv.exists():
            frames[s] = cache.load_ohlcv(f"{s}/USDT", "4h", cache_dir=root / cfg.data.cache_dir,
                                         start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
    td = trend_daily(frames)
    td.index = pd.DatetimeIndex(td.index).tz_localize(None)

    R = pd.read_parquet(SLEEVE3)[["crypto_trend", "crypto_funding"]]
    R = R.join(td.rename("trend_dir"), how="left").fillna({"trend_dir": 0.0})

    def book(cols):
        Rtr = R[R.index < CUT][cols]
        iv = 1.0 / Rtr.std()
        w = iv / iv.sum()
        return (R[cols] * w).sum(axis=1), {k: round(float(v), 2) for k, v in w.items()}

    combo, wc = book(["crypto_trend", "crypto_funding"])
    combo3, w3 = book(["crypto_trend", "crypto_funding", "trend_dir"])

    lines = [f"# YÖNSEL TREND sleeve combo'ya eklenince (ADX≥30, risk-frac {RISK_FRAC})", "",
             f"trend_dir sleeve tek-başına: OOS Sharpe {_stats(td[td.index>=CUT])[0]:.2f}. "
             f"Korelasyon (full):", "",
             "```", R.corr().round(2).to_string(), "```", "",
             "## Kombine kitap — OOS (2025-26)", "",
             "| Kitap | ağırlık | OOS Sharpe | CAGR | MaxDD |", "|---|---|---|---|---|"]
    for nm, b, w in (("combo (trend+funding)", combo, wc), ("combo + YÖNSEL-trend", combo3, w3)):
        o = b[b.index >= CUT]
        sh, cg, md = _stats(o)
        lines.append(f"| {nm} | {w} | {sh:.2f} | {cg*100:.0f}% | {md*100:.0f}% |")

    lines += ["", "## Yıl-bazı (combo vs combo+trend, Sharpe)", "", "| yıl | combo | combo+trend |", "|---|---|---|"]
    for yr in sorted(set(R.index.year)):
        cm = combo[combo.index.year == yr]
        c3 = combo3[combo3.index.year == yr]
        lines.append(f"| {yr} | {_stats(cm)[0]:.2f} | {_stats(c3)[0]:.2f} |")

    s_combo = _stats(combo[combo.index >= CUT])[0]
    s_3 = _stats(combo3[combo3.index >= CUT])[0]
    lines += ["", "## Yorum (dürüst)", ""]
    if s_3 > s_combo + 0.1:
        lines.append(f"**Yönsel trend sleeve combo'yu İYİLEŞTİRDİ: OOS Sharpe {s_combo:.2f}→{s_3:.2f}.** "
                     "Trend getirisi çeşitlendirme içinde değer katıyor — trend-yıllarında ekstra, "
                     "chop'ta combo taşıyor. 4-sleeve kitaba ekle (küçük ağırlıkla). DSR/PBO sonra.")
    elif s_3 > s_combo - 0.1:
        lines.append(f"**~Nötr: OOS Sharpe {s_combo:.2f}→{s_3:.2f}.** Trend sleeve ne belirgin katıyor "
                     "ne bozuyor — getirisini ekliyor ama Sharpe'ı oynatmıyor. Küçük ağırlıkla 'trend "
                     "maruziyeti' isteniyorsa eklenebilir; risk-ayarlı zorunluluk değil.")
    else:
        lines.append(f"**Trend sleeve BOZDU: OOS Sharpe {s_combo:.2f}→{s_3:.2f}.** Chop-varyansı "
                     "çeşitlendirme faydasını aşıyor — combo nötr kalması daha iyi. Trend getirisi "
                     "cazip ama risk-ayarlı olarak kombine kitaba zarar veriyor. Eklenmemeli.")
    lines.append(f"- risk-frac {RISK_FRAC} ile; yıl-bazı tablo trend-yıl katkısı vs chop-yıl bedelini gösterir. "
                 "Tek-dönem; DSR/PBO + maliyet sonrası nihai karar.")
    report = "\n".join(lines)
    print(report)
    (root / "reports_out" / "trend_combine.md").write_text(report)


if __name__ == "__main__":
    main()
