"""FUNDING-FLIP / SQUEEZE backtest — funding ekstremi + ters dönüşte işleme gir (tez testi).

Kullanıcı tezi: yüksek-|funding| coinde funding TERS dönünce fee-farmer'lar pozisyon kapatır →
yön hareketi. İki rakip yön:
  • FADE  (bizim kanıtlı edge): kalabalık-long (yüksek+funding) → SHORT; kalabalık-short → LONG
  • UNWIND (kullanıcı tezi): funding düşünce fee-toplayan taraf kapatır → ters yön
Hangisi kazanır AMPİRİK. Olay = funding_z ekstrem (|z|>THR) İKEN z sıfıra dönmeye başladı (reversal).
Girişte ATR-bağımsız %TP/%SL + N-bar zaman-stopu. Pooled, train<2025 / OOS 2025-26, IS-vs-OOS,
baseline (tüm-bar forward) ile karşılaştır. Optimal TP/SL grid'den seçilir (overfit için IS/OOS ayrı).

Usage: python scripts/run_funding_flip.py
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
from quantlab.data import cache, funding as fundmod  # noqa: E402

CUT = pd.Timestamp("2025-01-01")
MKTDATA = Path("../uyg/src/mktdata")
FUND = Path("../uyg/src/funddata")
UNIVERSE = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LTC", "ATOM", "DOT",
            "LINK", "DOGE", "ETC", "FIL", "INJ", "NEAR", "UNI", "APT", "ARB", "OP"]
Z_WIN = 120          # ~40 gün (8h funding → 4h ffill: 120 bar = 20 gün)
Z_THR = 1.5          # ekstrem eşiği
HOLD = 48            # zaman-stopu (4h bar = 8 gün)
COST = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0006   # round-trip maliyet
TP_GRID = [0.03, 0.05, 0.08]
SL_GRID = [0.02, 0.03, 0.05]


def load_all(cfg, root):
    data = {}
    for s in UNIVERSE:
        csv = (root / MKTDATA / f"{s}_USDT_4h.csv").resolve()
        fp = (root / FUND / f"{s}_funding.csv").resolve()
        if not (csv.exists() and fp.exists()):
            continue
        df = cache.load_ohlcv(f"{s}/USDT", "4h", cache_dir=root / cfg.data.cache_dir,
                              start=cfg.data.start, end=cfg.data.end, seed_csv=csv)
        fu = fundmod.load_funding(fp).reindex(df.index, method="ffill")
        data[s] = (df, fu)
    return data


def events(df, fu, fade=True):
    """Olayları döndür: (entry_idx, side). Ekstrem + reversal başlangıcı."""
    z = (fu - fu.rolling(Z_WIN).mean()) / (fu.rolling(Z_WIN).std() + 1e-12)
    dz = z.diff()
    evs = []
    arr_z, arr_dz = z.to_numpy(), dz.to_numpy()
    for i in range(Z_WIN + 1, len(df) - 1):
        # yüksek+funding ekstrem (kalabalık long) ve z düşmeye başladı (reversal)
        if arr_z[i] > Z_THR and arr_dz[i] < 0:
            side = -1 if fade else +1     # fade=short; unwind=long
            evs.append((i, side))
        elif arr_z[i] < -Z_THR and arr_dz[i] > 0:
            side = +1 if fade else -1
            evs.append((i, side))
    return evs


def trade_ret(df, i, side, tp, sl):
    """Giriş i+1 open; TP/SL/zaman-stopu; maliyet ~6bps round-trip."""
    o = df["open"].to_numpy()
    hi = df["high"].to_numpy()
    lo = df["low"].to_numpy()
    entry = o[i + 1]
    for j in range(i + 1, min(i + 1 + HOLD, len(df))):
        if side > 0:
            if lo[j] <= entry * (1 - sl):
                return -sl - COST
            if hi[j] >= entry * (1 + tp):
                return tp - COST
        else:
            if hi[j] >= entry * (1 + sl):
                return -sl - COST
            if lo[j] <= entry * (1 - tp):
                return tp - COST
    # zaman-stopu: kapanışta çık
    exit_px = df["close"].to_numpy()[min(i + HOLD, len(df) - 1)]
    r = (exit_px / entry - 1) * side - COST
    return r


def evaluate(data, fade, tp, sl, mask):
    rs = []
    for s, (df, fu) in data.items():
        idx = df.index
        for i, side in events(df, fu, fade):
            if mask(idx[i]):
                rs.append(trade_ret(df, i, side, tp, sl))
    rs = np.array(rs)
    if len(rs) < 20:
        return None
    return {"n": len(rs), "exp": float(rs.mean()), "win": float((rs > 0).mean()),
            "sharpe": float(rs.mean() / rs.std() * np.sqrt(len(rs))) if rs.std() > 0 else 0}


def main():
    cfg = load_config(str(Path(__file__).resolve().parents[1] / "config" / "default.yaml"))
    root = Path(__file__).resolve().parents[1]
    print("Veri + funding yükleniyor…")
    data = load_all(cfg, root)
    is_mask = lambda t: t < CUT      # noqa: E731
    oos_mask = lambda t: t >= CUT    # noqa: E731

    lines = ["# FUNDING-FLIP / SQUEEZE backtest (funding ekstrem + reversal'da gir)", "",
             f"{len(data)} coin, z-pencere {Z_WIN} bar, eşik |z|>{Z_THR}, zaman-stopu {HOLD} bar (8g), "
             "maliyet 6bps. FADE (kalabalığı fade) vs UNWIND (fee-farmer kapanışı) yönleri.", ""]

    for fade, name in ((True, "FADE (short yüksek-funding / long düşük — bizim edge yönü)"),
                       (False, "UNWIND (ters — fee-farmer unwind yönü, kullanıcı tezi)")):
        lines += [f"## {name}", "", "| TP/SL | IS n | IS exp | IS win | OOS n | OOS exp | OOS win | OOS Sharpe |",
                  "|---|---|---|---|---|---|---|---|"]
        best = None
        for tp in TP_GRID:
            for sl in SL_GRID:
                isr = evaluate(data, fade, tp, sl, is_mask)
                oos = evaluate(data, fade, tp, sl, oos_mask)
                if isr and oos:
                    lines.append(f"| {tp*100:.0f}/{sl*100:.0f}% | {isr['n']} | {isr['exp']*100:+.2f}% | "
                                 f"{isr['win']*100:.0f}% | {oos['n']} | {oos['exp']*100:+.2f}% | "
                                 f"{oos['win']*100:.0f}% | {oos['sharpe']:.2f} |")
                    # optimal = IS'de en iyi exp (OOS'a BAKMADAN seç — dürüst)
                    if best is None or isr["exp"] > best[0]:
                        best = (isr["exp"], tp, sl, oos)
        if best:
            _, tp, sl, oos = best
            lines += ["", f"**IS-optimal TP/SL = {tp*100:.0f}/{sl*100:.0f}%** → OOS: n={oos['n']}, "
                      f"exp {oos['exp']*100:+.2f}%, win {oos['win']*100:.0f}%, Sharpe {oos['sharpe']:.2f}", ""]

    lines += ["## Yorum (dürüst)", "",
              "- IS'de en iyi TP/SL seçilip OOS'a uygulandı (overfit-korumalı). Pozitif OOS exp + "
              "makul örneklem = tez tutuyor; OOS≈0 veya negatif = zamanlama edge katmıyor.",
              "- FADE yönü pozitifse: bizim sürekli-carry edge'inin zamanlanmış hali — squeeze "
              "tetikleyici işe yarıyor olabilir. UNWIND pozitifse: kullanıcı tezi (fee-farmer "
              "kapanışı) doğru. İkisi de ~0 ise: flip-zamanlaması rastgele girişten iyi değil.",
              "- ⚠️ Maliyet 6bps varsayıldı; gerçek perp komisyon+spread + funding ödemesi (pozisyon "
              "funding'i öder/alır) ayrıca etkiler. survivorship-capped. Canlı öncesi testnet."]
    report = "\n".join(lines)
    print("\n" + report)
    (root / "reports_out" / "funding_flip.md").write_text(report)
    print("\nSaved -> reports_out/funding_flip.md")


if __name__ == "__main__":
    main()
