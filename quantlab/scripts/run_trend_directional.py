"""'tirad' YÖNSEL trend-takip stratejisini dürüstçe OOS backtest et — gerçek edge mi whipsaw mı?

tirad mantığı: çok-coin 4H, Donchian(40)+Supertrend(10,3) AYNI yön + BTC-200EMA hizalama +
BTC rejim-gate (skor≥2). SL=2ATR, TP=2.75R, long+short. Kazanç dalgasını yakalıyor ama
chop'ta whipsaw'da geri mi veriyor? Realized per-trade expectancy + yıl-bazı (rejim) + OOS.

Usage: python scripts/run_trend_directional.py
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
SL_ATR, TP_R, COST = 2.0, 2.75, 0.0007


def btc_regime_series(btc):
    c = btc["close"].to_numpy(float)
    a = adx(btc, 14)[0] if isinstance(adx(btc, 14), tuple) else adx(btc, 14)
    at = atr(btc, 14).to_numpy()
    atrp = at / c
    vov = pd.Series(atrp).rolling(30).std().to_numpy()
    mom = btc["close"].pct_change(10).to_numpy()
    ema = btc["close"].ewm(span=200, adjust=False).mean().to_numpy()
    med = np.nanmedian(vov)
    score = ((np.nan_to_num(a) > 25).astype(int) + (np.nan_to_num(vov, nan=9) < med).astype(int)
             + (np.abs(np.nan_to_num(mom)) > 0.05).astype(int))
    bdir = np.where(c > ema, 1, -1)
    return pd.Series(score, index=btc.index), pd.Series(bdir, index=btc.index)


def main():
    cfg = load_config(str(Path(__file__).resolve().parents[1] / "config" / "default.yaml"))
    root = Path(__file__).resolve().parents[1]
    frames = {}
    for s in UNIVERSE:
        csv = (root / MKTDATA / f"{s}_USDT_4h.csv").resolve()
        if csv.exists():
            frames[s] = cache.load_ohlcv(f"{s}/USDT", "4h", cache_dir=root / cfg.data.cache_dir,
                                         start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
    btc = frames["BTC"]
    reg, bdir = btc_regime_series(btc)

    trades = []   # (exit_ts, r)
    for coin, df in frames.items():
        c = df["close"].to_numpy(float)
        hi, lo = df["high"].to_numpy(float), df["low"].to_numpy(float)
        at = atr(df, 14).to_numpy()
        st = supertrend(df, period=10, multiplier=3.0)["dir"].to_numpy()
        dch = donchian(df, 40)
        up, dn = dch["upper"].to_numpy(), dch["lower"].to_numpy()
        rg = reg.reindex(df.index).to_numpy()
        bd = bdir.reindex(df.index).to_numpy()
        i = 50
        while i < len(df) - 1:
            # donchian breakout yönü
            don = 1 if c[i] >= up[i - 1] else (-1 if c[i] <= dn[i - 1] else 0)
            sti = int(st[i]) if np.isfinite(st[i]) else 0
            d = don if (don != 0 and don == sti) else 0       # agreement
            if d != 0 and rg[i] >= 2 and d == bd[i] and at[i] > 0:
                entry = c[i]
                sld = SL_ATR * at[i] / entry
                if not (0.003 < sld < 0.12):
                    i += 1
                    continue
                sl = entry - d * SL_ATR * at[i]
                tp = entry + d * TP_R * SL_ATR * at[i]
                # ileri sim: SL/TP veya 60 bar zaman-stopu
                for j in range(i + 1, min(i + 60, len(df))):
                    if d == 1:
                        hit = -sld if lo[j] <= sl else (TP_R * sld if hi[j] >= tp else None)
                    else:
                        hit = -sld if hi[j] >= sl else (TP_R * sld if lo[j] <= tp else None)
                    if hit is not None:
                        r = (hit) / sld - COST * 2 / sld
                        trades.append((df.index[j], r))
                        i = j
                        break
                else:
                    exitp = c[min(i + 60, len(df) - 1)]
                    r = d * (exitp - entry) / entry / sld - COST * 2 / sld
                    trades.append((df.index[min(i + 60, len(df) - 1)], r))
                    i += 60
            i += 1

    tr = pd.DataFrame(trades, columns=["ts", "r"]).set_index("ts").sort_index()
    is_t, oos_t = tr[tr.index < CUT]["r"], tr[tr.index >= CUT]["r"]

    def stat(x):
        return (len(x), float(x.mean()), float((x > 0).mean()),
                float(x.mean() / x.std() * np.sqrt(len(x))) if len(x) > 1 and x.std() > 0 else 0)

    lines = ["# 'tirad' YÖNSEL trend-takip — dürüst OOS backtest (realized R)", "",
             f"{len(frames)} coin, Donchian+Supertrend agreement + BTC-rejim + gate. SL2ATR/TP2.75R, "
             f"maliyet {COST*1e4:.0f}bps. Toplam {len(tr)} işlem.", "",
             "| pencere | işlem | ort R | win% | R-Sharpe |", "|---|---|---|---|---|"]
    for nm, x in (("Tüm", tr["r"]), ("IS (≤2024)", is_t), ("OOS (2025-26)", oos_t)):
        n, m, w, sh = stat(x)
        lines.append(f"| {nm} | {n} | {m:+.3f}R | {w*100:.0f}% | {sh:.2f} |")
    lines += ["", "## Yıl-bazı (realized ort R) — trend vs chop", "", "| yıl | işlem | ort R | toplam R |", "|---|---|---|---|"]
    for yr, g in tr.groupby(tr.index.year):
        lines.append(f"| {yr} | {len(g)} | {g['r'].mean():+.3f}R | {g['r'].sum():+.1f}R |")

    n, m, w, sh = stat(oos_t)
    lines += ["", "## Yorum (dürüst)", ""]
    if m > 0.05 and sh > 0.3:
        lines.append(f"**Yönsel trend-takip OOS POZİTİF (ort {m:+.3f}R, win {w*100:.0f}%).** Rejim-gate "
                     "trend'leri yakalayıp chop'ta uyuyor → 'dalga yakalama' gerçek olabilir. Combo'ya "
                     "YÖNSEL sleeve olarak eklemeye değer (DSR/PBO sonra).")
    else:
        lines.append(f"**Yönsel trend-takip OOS zayıf/dengesiz (ort {m:+.3f}R, win {w*100:.0f}%, "
                     f"R-Sharpe {sh:.2f}).** Trend yıllarında kazanıp chop'ta whipsaw'da geri veriyor "
                     "(yıl-bazı tabloya bak). +2-gün şanslı yönsel çağrıydı; sürekli edge değil. Bu yüzden "
                     "combo nötr kaldı — yönsel bahis uzun vadede dengesiz. Yine de gate'li yönsel sleeve "
                     "trend-yıllarında katkı sağlayabilir; karar yıl-bazı + maliyet sonrası.")
    report = "\n".join(lines)
    print(report)
    (root / "reports_out" / "trend_directional.md").write_text(report)


if __name__ == "__main__":
    main()
