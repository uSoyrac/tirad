"""HH/LL PİYASA YAPISI (swing pivot + break-of-structure) — dip/tepe yakalama testi.

Kullanıcı fikri: HH/LL tespit edersek dip ve tepeleri yakalarız. Sistematik karşılığı:
swing-pivot'lar (k bar her iki yanda ekstrem) → son pivot-high kırılırsa yukarı-yapı (LONG),
son pivot-low kırılırsa aşağı-yapı (SHORT). Çıkış = ters yapı-kırılımı (BoS) = "tepeyi sezip çık".
Stop'u YAPI belirler (ATR değil). Long+short, her bar pozisyon.

Test: tek-başına OOS Sharpe + yıl-bazı + combo'ya sleeve olarak (Donchian trend combo'yu bozmuştu —
yapı farklı mı?). pivot k-bar GECİKMELİ doğrulanır (nedensel: gelecek bar sızıntısı yok).

Usage: python scripts/run_hhll.py [pivot_k]
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

MKTDATA = Path("../uyg/src/mktdata")
SLEEVE3 = Path(__file__).resolve().parents[1] / "reports_out" / "_sleeves3.parquet"
UNIVERSE = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LTC", "ATOM", "DOT",
            "LINK", "DOGE", "ETC", "FIL", "INJ", "NEAR", "UNI", "APT", "ARB", "OP"]
CUT = pd.Timestamp("2025-01-01")
PPY = 365
COST = 0.0007
PIVOT_K = int(sys.argv[1]) if len(sys.argv) > 1 else 5


def structure_position(df, k=PIVOT_K):
    """Swing-pivot + BoS → pozisyon serisi (+1 long / -1 short). Pivot k-bar gecikmeli doğrulanır."""
    h, low, c = df["high"].to_numpy(float), df["low"].to_numpy(float), df["close"].to_numpy(float)
    n = len(c)
    last_ph = np.nan
    last_pl = np.nan
    pos = np.zeros(n)
    cur = 0
    for i in range(n):
        # i-k barında pivot oluştu mu? (i-k, çevresindeki ±k içinde ekstrem) — yalnız <=i veriyle
        j = i - k
        if j - k >= 0:
            win_h = h[j - k:j + k + 1]
            win_l = low[j - k:j + k + 1]
            if h[j] == win_h.max():
                last_ph = h[j]            # onaylanmış pivot-high (k bar gecikmeli)
            if low[j] == win_l.min():
                last_pl = low[j]
        # break-of-structure: kapanış son pivotu kırarsa yön
        if np.isfinite(last_ph) and c[i] > last_ph:
            cur = 1
        elif np.isfinite(last_pl) and c[i] < last_pl:
            cur = -1
        pos[i] = cur
    return pd.Series(pos, index=df.index)


def daily_returns(frames):
    streams = []
    for coin, df in frames.items():
        pos = structure_position(df)
        ret = df["close"].pct_change()
        pnl = pos.shift(1) * ret - COST * pos.diff().abs().fillna(0)
        streams.append(pnl.rename(coin))
    R = pd.concat(streams, axis=1)
    daily4h = R.mean(axis=1)                       # eşit-ağırlık long+short
    return daily4h.resample("1D").apply(lambda x: (1 + x).prod() - 1).dropna()


def _stats(r):
    if len(r) < 3:
        return float("nan"), float("nan"), float("nan")
    eq = (1 + r).cumprod()
    sh = float(r.mean() / r.std() * np.sqrt(PPY)) if r.std() > 0 else 0.0
    cg = eq.iloc[-1] ** (PPY / len(r)) - 1
    md = float((eq / eq.cummax() - 1).min())
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
    hhll = daily_returns(frames)
    hhll.index = pd.DatetimeIndex(hhll.index).tz_localize(None)

    lines = [f"# HH/LL PİYASA YAPISI (pivot k={PIVOT_K}, BoS) — dip/tepe yakalama", "",
             f"{len(frames)} coin, swing-pivot + break-of-structure, long+short. Maliyet {COST*1e4:.0f}bps.", "",
             "## Tek başına", "", "| pencere | Sharpe | CAGR | MaxDD |", "|---|---|---|---|"]
    for nm, seg in (("Tüm", hhll), ("IS (≤2024)", hhll[hhll.index < CUT]), ("OOS (2025-26)", hhll[hhll.index >= CUT])):
        sh, cg, md = _stats(seg)
        lines.append(f"| {nm} | {sh:.2f} | {cg*100:+.0f}% | {md*100:.0f}% |")
    lines += ["", "## Yıl-bazı", "", "| yıl | Sharpe | getiri |", "|---|---|---|"]
    for yr, g in hhll.groupby(hhll.index.year):
        sh, _, _ = _stats(g)
        lines.append(f"| {yr} | {sh:.2f} | {((1+g).prod()-1)*100:+.0f}% |")

    # combo'ya sleeve olarak ekle
    R = pd.read_parquet(SLEEVE3)[["crypto_trend", "crypto_funding"]]
    R = R.join(hhll.rename("hhll"), how="left").fillna({"hhll": 0.0})

    def book(cols):
        iv = 1.0 / R[R.index < CUT][cols].std()
        w = iv / iv.sum()
        return (R[cols] * w).sum(axis=1)

    combo = book(["crypto_trend", "crypto_funding"])
    combo3 = book(["crypto_trend", "crypto_funding", "hhll"])
    sc = _stats(combo[combo.index >= CUT])[0]
    s3 = _stats(combo3[combo3.index >= CUT])[0]
    corr = R.corr()["hhll"].round(2).to_dict()
    lines += ["", "## Combo'ya sleeve olarak (Donchian trend bozmuştu — yapı farklı mı?)", "",
              f"- hhll korelasyon: {corr}",
              f"- combo OOS Sharpe: **{sc:.2f}** → +hhll: **{s3:.2f}**", "",
              "## Yorum (dürüst)", ""]
    osh = _stats(hhll[hhll.index >= CUT])[0]
    if osh > 0.5 and s3 > sc + 0.1:
        lines.append(f"**HH/LL yapı İŞE YARADI: tek-başına OOS {osh:.2f}, combo'yu {sc:.2f}→{s3:.2f} "
                     "iyileştirdi.** Yapı-lensi momentum-trend'in aksine combo'ya değer katıyor — dip/tepe "
                     "yakalama gerçek. compound motorunun giriş/çıkış mekanizması olabilir.")
    elif osh > 0.3:
        lines.append(f"**Kısmi: tek-başına OOS {osh:.2f} (pozitif) ama combo'yu {sc:.2f}→{s3:.2f}.** "
                     "Yapı bir edge taşıyor ama combo'ya net katkı sınırlı/karışık — yıl-bazı + korelasyona bak.")
    else:
        lines.append(f"**HH/LL zayıf: tek-başına OOS {osh:.2f}, combo {sc:.2f}→{s3:.2f}.** Yapı-takibi de "
                     "trend-takip ailesinden — chop'ta sahte-kırılım whipsaw'ı. Donchian/Supertrend ile "
                     "aynı kader. Dip/tepe 'yakalama' gecikmeli pivot yüzünden geç + chop'ta yanıltıcı.")
    lines.append(f"- ⚠️ pivot k={PIVOT_K} bar gecikmeli (tepeyi k-bar sonra onaylar). Farklı k denenebilir; "
                 "tek-dönem; yapı-takibi de rejim-bağımlı olabilir.")
    report = "\n".join(lines)
    print(report)
    (root / "reports_out" / "hhll.md").write_text(report)


if __name__ == "__main__":
    main()
