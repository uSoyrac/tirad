"""GÜVENLİ TREND GİRİŞİ — chop-filtresi (Efficiency Ratio / ADX) trend-takibi kurtarır mı?

Yönsel trend (Donchian+Supertrend+BTC-rejim) 2025 chop'unda whipsaw'da kanadı (-36R). İLKESEL
chop-filtreleri ekle: (A) coin Efficiency-Ratio>eşik (temiz trend), (B) coin ADX>eşik (güçlü),
(C) ikisi. Filtre IS'i korurken OOS'u (2025) düzeltiyor + çoğu yıl + ise GERÇEK; sadece OOS'u
şansla düzeltirse overfit → reddet.

Usage: python scripts/run_trend_filtered.py
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
UNIVERSE = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LTC", "ATOM", "DOT",
            "LINK", "DOGE", "ETC", "FIL", "INJ", "NEAR", "UNI", "APT", "ARB", "OP"]
CUT = pd.Timestamp("2025-01-01")
SL_ATR, TP_R, COST = 2.0, 2.75, 0.0007


def btc_dir_series(btc):
    ema = btc["close"].ewm(span=200, adjust=False).mean().to_numpy()
    return np.where(btc["close"].to_numpy(float) > ema, 1, -1)


def simulate(frames, bdir, er_min, adx_min):
    trades = []
    for coin, df in frames.items():
        c = df["close"].to_numpy(float)
        hi, lo = df["high"].to_numpy(float), df["low"].to_numpy(float)
        at = atr(df, 14).to_numpy()
        st = supertrend(df, period=10, multiplier=3.0)["dir"].to_numpy()
        dch = donchian(df, 40)
        up, dn = dch["upper"].to_numpy(), dch["lower"].to_numpy()
        er = efficiency_ratio(df, 20).to_numpy()
        ax = adx(df, 14)
        ax = (ax[0] if isinstance(ax, tuple) else ax)
        ax = ax.to_numpy() if hasattr(ax, "to_numpy") else np.asarray(ax)
        bd = bdir[coin]
        i = 50
        while i < len(df) - 1:
            don = 1 if c[i] >= up[i - 1] else (-1 if c[i] <= dn[i - 1] else 0)
            sti = int(st[i]) if np.isfinite(st[i]) else 0
            d = don if (don != 0 and don == sti) else 0
            chop_ok = (np.isfinite(er[i]) and er[i] >= er_min) and (np.isfinite(ax[i]) and ax[i] >= adx_min)
            if d != 0 and d == bd[i] and at[i] > 0 and chop_ok:
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
                        trades.append((df.index[j], hit / sld - COST * 2 / sld))
                        i = j
                        break
                else:
                    k = min(i + 60, len(df) - 1)
                    trades.append((df.index[k], d * (c[k] - entry) / entry / sld - COST * 2 / sld))
                    i = k
            i += 1
    return pd.DataFrame(trades, columns=["ts", "r"]).set_index("ts").sort_index() if trades else pd.DataFrame()


def stat(x):
    if len(x) < 2 or x.std() == 0:
        return len(x), float(x.mean()) if len(x) else 0, 0.0
    return len(x), float(x.mean()), float(x.mean() / x.std() * np.sqrt(len(x)))


def main():
    cfg = load_config(str(Path(__file__).resolve().parents[1] / "config" / "default.yaml"))
    root = Path(__file__).resolve().parents[1]
    frames = {}
    for s in UNIVERSE:
        csv = (root / MKTDATA / f"{s}_USDT_4h.csv").resolve()
        if csv.exists():
            frames[s] = cache.load_ohlcv(f"{s}/USDT", "4h", cache_dir=root / cfg.data.cache_dir,
                                         start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
    bdir = {coin: btc_dir_series(frames["BTC"]) for coin in frames}  # tüm coinler BTC yönüne hizalı
    # not: hizalama için her coin'in kendi index'ine reindex etmeye gerek yok — aynı 4h takvim

    variants = [("Filtre YOK (baz)", 0.0, 0), ("ER≥0.3", 0.3, 0), ("ADX≥30", 0.0, 30),
                ("ER≥0.3 + ADX≥30", 0.3, 30), ("ER≥0.4 + ADX≥35 (sıkı)", 0.4, 35)]
    lines = ["# GÜVENLİ TREND GİRİŞİ — chop-filtresi testi (yönsel Donchian+Supertrend, realized R)", "",
             f"{len(frames)} coin. ER=efficiency ratio (trend temizliği), ADX=trend gücü. "
             "Filtre 2025 whipsaw'ını kesip trend-yıllarını koruyabiliyor mu?", "",
             "| filtre | IS işlem | IS ort R | OOS işlem | OOS ort R | 2025 ort R | 2025 toplam R |",
             "|---|---|---|---|---|---|---|"]
    for name, erm, axm in variants:
        tr = simulate(frames, bdir, erm, axm)
        if len(tr) == 0:
            lines.append(f"| {name} | 0 | — | 0 | — | — | — |")
            continue
        is_t, oos = tr[tr.index < CUT]["r"], tr[tr.index >= CUT]["r"]
        y25 = tr[(tr.index >= pd.Timestamp("2025-01-01")) & (tr.index < pd.Timestamp("2026-01-01"))]["r"]
        ni, mi, _ = stat(is_t)
        no, mo, _ = stat(oos)
        lines.append(f"| {name} | {ni} | {mi:+.3f}R | {no} | {mo:+.3f}R | {y25.mean():+.3f}R | {y25.sum():+.1f}R |")

    lines += ["", "## Yorum (dürüst)", "",
              "- Filtre OOS ort-R'yi POZİTİFE çevirir + IS pozitif kalır + 2025 toplam-R artarsa → "
              "chop-filtresi trend-takibi GERÇEKTEN kurtarıyor (combo'ya yönsel-trend sleeve eklenebilir).",
              "- Eğer sıkı filtre 2025'i düzeltiyor ama işlem sayısı çok düşüyor / IS de düşüyorsa → "
              "az-işlem + overfit; güvenilmez.",
              "- ⚠️ ER/ADX eşikleri İLKESEL (chop'tan kaç), 2025'e uydurulmadı. Yine de tek-dönem; "
              "DSR/PBO + maliyet sonrası karar. Whipsaw kalıntısı silinmeyebilir (trend-takibin doğası)."]
    report = "\n".join(lines)
    print(report)
    (root / "reports_out" / "trend_filtered.md").write_text(report)


if __name__ == "__main__":
    main()
