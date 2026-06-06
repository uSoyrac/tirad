"""ÇIKIŞ-OPTİMİZASYONU — 'kâr al ve çık' kuralı trend stratejisini kurtarır mı?

Kullanıcı tezi: girmek+çıkmak bizim elimizde; iyi çıkış trendde kârı kilitler. Yönsel trend
(Donchian+Supertrend+BTC-dir, ADX≥30) ENTRY'si sabit; ÇIKIŞ kuralını değiştir:
  A. fixed_2.75R      : sabit TP 2.75R (baseline)
  B. trail_3ATR       : chandelier — stop'u zirveden 3ATR geride sürükle (kazananı koştur)
  C. quick_1.5R       : hızlı TP 1.5R (erken kilitle)
  D. be_then_trail     : +1R'de stop'u girişe çek, sonra 3ATR trail
Hangisi OOS'u pozitife çevirir? Yoksa çıkış da kurtaramıyor mu?

Usage: python scripts/run_trend_exits.py
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
SL_ATR, COST, ADX_MIN, MAXBARS = 2.0, 0.0007, 30, 90


def run_exit(df, bd, mode):
    c = df["close"].to_numpy(float); hi = df["high"].to_numpy(float); lo = df["low"].to_numpy(float)
    at = atr(df, 14).to_numpy()
    st = supertrend(df, period=10, multiplier=3.0)["dir"].to_numpy()
    dch = donchian(df, 40); up, dn = dch["upper"].to_numpy(), dch["lower"].to_numpy()
    ax = adx(df, 14); ax = (ax[0] if isinstance(ax, tuple) else ax)
    ax = ax.to_numpy() if hasattr(ax, "to_numpy") else np.asarray(ax)
    rows = []; i = 50
    while i < len(df) - 1:
        don = 1 if c[i] >= up[i-1] else (-1 if c[i] <= dn[i-1] else 0)
        sti = int(st[i]) if np.isfinite(st[i]) else 0
        d = don if (don != 0 and don == sti) else 0
        if d != 0 and d == bd[i] and at[i] > 0 and np.isfinite(ax[i]) and ax[i] >= ADX_MIN:
            entry = c[i]; a0 = at[i]; sld = SL_ATR*a0/entry
            if not (0.003 < sld < 0.12): i += 1; continue
            sl = entry - d*SL_ATR*a0
            tp = entry + d*(2.75 if mode == "A" else 1.5)*SL_ATR*a0   # A/C sabit TP
            ext = entry; moved_be = False; r = None
            for j in range(i+1, min(i+MAXBARS, len(df))):
                ext = max(ext, hi[j]) if d == 1 else min(ext, lo[j])
                if mode in ("B", "D"):                     # trailing 3ATR
                    if mode == "D" and not moved_be and d*(c[j]-entry) >= SL_ATR*a0:
                        sl = entry; moved_be = True         # +1R → breakeven
                    if mode == "D" and moved_be or mode == "B":
                        sl = max(sl, ext - 3*a0) if d == 1 else min(sl, ext + 3*a0)
                hit_sl = (lo[j] <= sl) if d == 1 else (hi[j] >= sl)
                hit_tp = (mode in ("A", "C")) and ((hi[j] >= tp) if d == 1 else (lo[j] <= tp))
                if hit_sl:
                    r = (d*(sl-entry)/entry)/sld - COST*2/sld; i = j; break
                if hit_tp:
                    r = (d*(tp-entry)/entry)/sld - COST*2/sld; i = j; break
            if r is None:
                k = min(i+MAXBARS, len(df)-1)
                r = d*(c[k]-entry)/entry/sld - COST*2/sld; i = k
            rows.append((df.index[i], r))
        i += 1
    return rows


def main():
    cfg = load_config(str(Path(__file__).resolve().parents[1] / "config" / "default.yaml"))
    root = Path(__file__).resolve().parents[1]
    frames = {}
    for s in UNIVERSE:
        csv = (root / MKTDATA / f"{s}_USDT_4h.csv").resolve()
        if csv.exists():
            frames[s] = cache.load_ohlcv(f"{s}/USDT", "4h", cache_dir=root/cfg.data.cache_dir,
                                         start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
    bd = np.where(frames["BTC"]["close"].to_numpy(float) >
                  frames["BTC"]["close"].ewm(span=200, adjust=False).mean().to_numpy(), 1, -1)
    names = {"A": "fixed 2.75R", "B": "trail 3ATR", "C": "quick 1.5R", "D": "BE+trail"}
    lines = ["# ÇIKIŞ-OPTİMİZASYONU — yönsel trend (ADX≥30), entry sabit, çıkış değişken", "",
             f"{len(frames)} coin. 'Kâr al ve çık' kuralı OOS'u kurtarır mı?", "",
             "| çıkış | işlem | IS ort R | OOS ort R | OOS win% | 2025 toplam R | 2026 ort R |", "|---|---|---|---|---|---|---|"]
    for m in ("A", "B", "C", "D"):
        rows = []
        for coin, df in frames.items():
            rows += run_exit(df, bd, m)
        tr = pd.DataFrame(rows, columns=["ts", "r"]).set_index("ts").sort_index()
        is_t, oos = tr[tr.index < CUT]["r"], tr[tr.index >= CUT]["r"]
        y25 = tr[(tr.index >= "2025-01-01") & (tr.index < "2026-01-01")]["r"]
        y26 = tr[tr.index >= "2026-01-01"]["r"]
        lines.append(f"| {names[m]} | {len(tr)} | {is_t.mean():+.3f}R | {oos.mean():+.3f}R | "
                     f"{(oos>0).mean()*100:.0f}% | {y25.sum():+.1f}R | {y26.mean():+.3f}R |")
    lines += ["", "## Yorum (dürüst)", "",
              "- Bir çıkış-kuralı OOS ort-R'yi belirgin POZİTİFE çevirir + 2025'i toparlarsa → çıkış-zamanlaması "
              "gerçek kaldıraç (kullanıcı haklı). Hepsi ~0/negatif kalırsa → çıkış da kurtaramıyor; trend'in "
              "chop-bedeli çıkış-kuralından bağımsız.",
              "- trail (B/D) büyük trendleri koşturur ama dönüşte geri verir; quick (C) erken kilitler ama "
              "büyük trendi kaçırır — klasik trade-off. 2025 (chop) sütunu belirleyici."]
    report = "\n".join(lines)
    print(report)
    (root / "reports_out" / "trend_exits.md").write_text(report)


if __name__ == "__main__":
    main()
