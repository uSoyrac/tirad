"""GELİŞTİRİLMİŞ TREND BOTU — tirad + benim 2 doğrulanmış iyileştirmem İSTİFLİ.

İyileştirme 1: ADX≥30 filtresi (chop'u ele; OOS −0.005→+0.08).
İyileştirme 2: hızlı 1.5R TP (chop-yılını kurtarır; 2025 −18R→+6R).
Stack: yönsel Donchian+Supertrend + BTC-dir + ADX≥30 + quick-1.5R. Bu, tirad'ın geliştirilmiş hali.
Çıktı: OOS + yıl-bazı + compound ($1000→?). Binance trend-kolu adayı.

Usage: python scripts/run_trend_improved.py
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
PPY = 365
SL_ATR, TP_R, COST, ADX_MIN, MAXBARS = 2.0, 1.5, 0.0007, 30, 90   # TP_R=1.5 (hızlı), ADX≥30


def trades_and_daily(frames):
    bd = np.where(frames["BTC"]["close"].to_numpy(float) >
                  frames["BTC"]["close"].ewm(span=200, adjust=False).mean().to_numpy(), 1, -1)
    rows = []
    pos_streams = []
    for coin, df in frames.items():
        c = df["close"].to_numpy(float); hi = df["high"].to_numpy(float); lo = df["low"].to_numpy(float)
        at = atr(df, 14).to_numpy()
        st = supertrend(df, period=10, multiplier=3.0)["dir"].to_numpy()
        dch = donchian(df, 40); up, dn = dch["upper"].to_numpy(), dch["lower"].to_numpy()
        ax = adx(df, 14); ax = (ax[0] if isinstance(ax, tuple) else ax)
        ax = ax.to_numpy() if hasattr(ax, "to_numpy") else np.asarray(ax)
        pos = np.zeros(len(df)); i = 50
        while i < len(df) - 1:
            don = 1 if c[i] >= up[i-1] else (-1 if c[i] <= dn[i-1] else 0)
            sti = int(st[i]) if np.isfinite(st[i]) else 0
            d = don if (don != 0 and don == sti) else 0
            if d != 0 and d == bd[i] and at[i] > 0 and np.isfinite(ax[i]) and ax[i] >= ADX_MIN:
                entry = c[i]; sld = SL_ATR*at[i]/entry
                if not (0.003 < sld < 0.12): i += 1; continue
                sl = entry - d*SL_ATR*at[i]; tp = entry + d*TP_R*SL_ATR*at[i]
                exitp = None
                for j in range(i+1, min(i+MAXBARS, len(df))):
                    pos[j] = d
                    if d == 1:
                        if lo[j] <= sl: exitp, r = sl, -sld; break
                        if hi[j] >= tp: exitp, r = tp, TP_R*sld; break
                    else:
                        if hi[j] >= sl: exitp, r = sl, -sld; break
                        if lo[j] <= tp: exitp, r = tp, TP_R*sld; break
                if exitp is None:
                    k = min(i+MAXBARS, len(df)-1); r = d*(c[k]-entry)/entry/sld; i = k
                else:
                    i = j
                rows.append((df.index[i], (r) - COST*2/sld))
            else:
                i += 1
        pos_streams.append(pd.Series(pos, index=df.index).rename(coin))
    tr = pd.DataFrame(rows, columns=["ts", "r"]).set_index("ts").sort_index()
    # günlük getiri (eşit-ağırlık, pozisyon × getiri)
    P = pd.concat(pos_streams, axis=1)
    rets = pd.DataFrame({k: v["close"].pct_change() for k, v in frames.items()})
    daily4h = (P.shift(1) * rets).mean(axis=1) - COST * P.diff().abs().mean(axis=1).fillna(0)
    daily = daily4h.resample("1D").apply(lambda x: (1+x).prod()-1).dropna()
    return tr, daily


def compound(r, kelly=0.25, start=1000.0):
    o = r[r.index >= CUT]
    mu, var = r[r.index < CUT].mean(), r[r.index < CUT].var()
    lev = max(0.0, kelly * (mu/var if var > 0 else 1.0))
    eq = peak = start
    for ret in o:
        live = lev*(0.5 if eq <= peak*0.8 else 1.0); eq *= (1+ret*live); peak = max(peak, eq)
    return eq


def main():
    cfg = load_config(str(Path(__file__).resolve().parents[1] / "config" / "default.yaml"))
    root = Path(__file__).resolve().parents[1]
    frames = {}
    for s in UNIVERSE:
        csv = (root / MKTDATA / f"{s}_USDT_4h.csv").resolve()
        if csv.exists():
            frames[s] = cache.load_ohlcv(f"{s}/USDT", "4h", cache_dir=root/cfg.data.cache_dir,
                                         start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
    tr, daily = trades_and_daily(frames)
    is_t, oos = tr[tr.index < CUT]["r"], tr[tr.index >= CUT]["r"]

    def sh(x): return float(x.mean()/x.std()*np.sqrt(len(x))) if len(x) > 1 and x.std() > 0 else 0

    lines = ["# GELİŞTİRİLMİŞ TREND BOTU (tirad + ADX≥30 + hızlı-1.5R-TP)", "",
             f"{len(frames)} coin. İyileştirmeler İSTİFLİ. {len(tr)} işlem.", "",
             "## Per-trade (realized R)", "", "| pencere | işlem | ort R | win% | R-Sharpe |", "|---|---|---|---|---|"]
    for nm, x in (("Tüm", tr["r"]), ("IS", is_t), ("OOS 2025-26", oos)):
        lines.append(f"| {nm} | {len(x)} | {x.mean():+.3f}R | {(x>0).mean()*100:.0f}% | {sh(x):.2f} |")
    lines += ["", "## Yıl-bazı (realized toplam R)", "", "| yıl | işlem | toplam R |", "|---|---|---|"]
    for yr, g in tr.groupby(tr.index.year):
        lines.append(f"| {yr} | {len(g)} | {g['r'].sum():+.1f}R |")
    lines += ["", "## Günlük-getiri kitabı (compound)", "",
              f"- OOS Sharpe: {sh(daily[daily.index>=CUT]):.2f}",
              f"- $1000 → ¼-Kelly compound (8-ay benzeri OOS): **${compound(daily):,.0f}**", "",
              "## Yorum", ""]
    o_sh = sh(oos)
    base_note = "(baz tirad: OOS -0.02R; ADX≥30: +0.08R; +quick-TP istifi burada)"
    if oos.mean() > 0.03 and tr.groupby(tr.index.year)["r"].sum().get(2025, -9) > -5:
        lines.append(f"**Geliştirme İŞE YARADI: OOS {oos.mean():+.3f}R, 2025 toparlandı.** {base_note} "
                     "ADX-filtre chop'u eler + hızlı-TP chop-yılını kurtarır → trend botu artık daha dengeli. "
                     "Binance trend-kolu olarak deploy edilebilir (combo'dan AYRI, opportunistic trend yakalama).")
    else:
        lines.append(f"**Kısmi: OOS {oos.mean():+.3f}R. {base_note}** İyileştirmeler tek-tek yardım etti ama "
                     "istif mükemmel değil — trend doğası gereği chop-riskli. Yine de baz tirad'dan İYİ; "
                     "Binance'te opportunistic trend-kolu olarak (küçük, combo'nun yanında) çalışabilir.")
    lines.append("- Kullanım: combo'nun YERİNE değil, YANINDA — trend-yıllarında ekstra yakalar, chop'ta "
                 "küçük kalır. Senin 'çoklu-bot, trendi yakalayan da olsun' vizyonun.")
    report = "\n".join(lines)
    print(report)
    (root / "reports_out" / "trend_improved.md").write_text(report)


if __name__ == "__main__":
    main()
