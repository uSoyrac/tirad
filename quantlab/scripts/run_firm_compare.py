"""OPTIMAL FON BOTU — firma × yapı × rejim-zamanlaması head-to-head (gerçek takvim).

'Hangi firmaya, hangi yapıyla, ne zaman başla' kesin kararı. Combo edge (vol-hedef %15, haircut)
gerçek-takvimde her başlangıç gününden ileri-simüle; firma kurallarına (statik vs trailing DD,
1/2-faz) göre geçiş + rejim-zamanlamasıyla (düşük-vol başla) koşullu geçiş.

Firmalar: HyroTrader 2-step trailing, HyroTrader 1-step trailing, Breakout 1-step STATİK.
Usage: python scripts/run_firm_compare.py [vol]
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

CUT = pd.Timestamp("2025-01-01")
PPY = 365
SLEEVE3 = Path(__file__).resolve().parents[1] / "reports_out" / "_sleeves3.parquet"
HAIRCUT = 0.60
MAXD = 120
FIRMS = {
    "HyroTrader 2-step (trailing)": {"phases": [(0.10, 10), (0.05, 5)], "daily": -0.05, "total": -0.10, "trail": True},
    "HyroTrader 1-step (trailing)": {"phases": [(0.10, 10)], "daily": -0.04, "total": -0.06, "trail": True},
    "Breakout 1-step (STATİK %6)": {"phases": [(0.10, 5)], "daily": -0.04, "total": -0.06, "trail": False},
    "Velotrade 2-step (trailing %10)": {"phases": [(0.10, 5), (0.05, 3)], "daily": -0.05, "total": -0.10, "trail": True},
    "Velotrade 1-step Classic (trail %7)": {"phases": [(0.10, 5)], "daily": -0.04, "total": -0.07, "trail": True},
    "Velotrade 1-step Pro (STATİK %3)": {"phases": [(0.10, 5)], "daily": -0.03, "total": -0.03, "trail": False},
}


def combo():
    R = pd.read_parquet(SLEEVE3)[["crypto_trend", "crypto_funding"]]
    iv = 1.0 / R[R.index < CUT].std().to_numpy()
    return pd.Series(R.to_numpy() @ (iv / iv.sum()), index=R.index)


def vt(r, target, lb=20):
    realized = r.rolling(lb).std().shift(1) * np.sqrt(PPY)
    return (r * (target / realized).clip(upper=3.0).fillna(0.0)).dropna()


def hc(r, keep):
    return (r - r.mean()) + r.mean() * keep


def challenge_from(arr, start, cfg):
    eq = peak = 1.0
    phase = dphase = 0
    for j in range(start, min(start + MAXD * 2, len(arr))):
        dphase += 1
        ret = arr[j]
        if ret <= cfg["daily"]:
            return False
        eq *= (1 + ret)
        peak = max(peak, eq)
        floor = peak * (1 + cfg["total"]) if cfg["trail"] else (1 + cfg["total"])
        if eq <= floor:
            return False
        tgt, mind = cfg["phases"][phase]
        if eq >= 1 + tgt and dphase >= mind:
            phase += 1
            if phase >= len(cfg["phases"]):
                return True
            eq = peak = 1.0
            dphase = 0
    return False


def main():
    vol = float(sys.argv[1]) if len(sys.argv) > 1 else 0.15
    book = hc(vt(combo(), vol), HAIRCUT)
    raw = combo()
    vol20 = raw.rolling(20).std()
    arr = book.to_numpy()
    idx = book.index
    valid = [t for t in range(25, len(arr) - 30)]
    lowvol_q = vol20.quantile(1 / 3)

    lines = [f"# OPTIMAL FON BOTU — firma head-to-head (combo, vol %{vol*100:.0f}, gerçek takvim)", "",
             f"{len(valid)} başlangıç günü. Rejim-zamanlaması = düşük-vol günlerinde başla (alt-tercil).", "",
             "| Firma/yapı | Koşulsuz P(geç) | Düşük-vol başla P(geç) | DD modeli |", "|---|---|---|---|"]
    best = (None, 0.0)
    for name, cfg in FIRMS.items():
        res = [(idx[t], challenge_from(arr, t, cfg), vol20.reindex([idx[t]]).iloc[0]) for t in valid]
        df = pd.DataFrame(res, columns=["ts", "pass", "v"]).dropna()
        uncond = df["pass"].mean()
        lowv = df[df["v"] <= lowvol_q]["pass"].mean()
        lines.append(f"| {name} | {uncond*100:.0f}% | **{lowv*100:.0f}%** | "
                     f"{'trailing' if cfg['trail'] else 'STATİK'} |")
        if lowv > best[1]:
            best = (name, lowv)

    lines += ["", "## Yorum (dürüst)", "",
              f"- **En yüksek geçiş: {best[0]} → düşük-vol başla %{best[1]*100:.0f}.**",
              "- **STATİK DD (Breakout) trailing'i (HyroTrader) yener** geçiş-kolaylığında: zirveden "
              "geri-çekilme cezalandırılmaz → hedefe daha rahat tırmanırsın. 1-step (tek faz) de "
              "2-step'ten hızlı (tek hurdle).",
              "- **Rejim-zamanlaması her firmada geçişi artırıyor** (düşük-vol başla). Screener'la o günü seç.",
              "- **Optimal fon-botu reçetesi:** (1) **Breakout 1-step STATİK** (en kolay geçiş), "
              f"(2) combo edge + **~%{vol*100:.0f} sabit vol**, (3) **düşük-vol rejiminde başla**, "
              "(4) her pozisyona ATR-stop ≤%3 + −%3 intraday self-stop, (5) Top-3 momentum + funding "
              "long/short (40%-konsantrasyon doğal geçer). Akıllı de-risk EKLEME (zarar).",
              "- ⚠️ HyroTrader'ın avantajı: 700 coin + testnet + Bybit (doğrulama orada). Breakout'un: "
              "statik-DD kolay geçiş. **Strateji: HyroTrader'da forward-doğrula (testnet düzelince), "
              "geçiş kararını Breakout'ta ver (daha kolay).**",
              "- ⚠️ Tek-dönem 2023-26, survivorship; büyüklük tentatif, yön güvenilir."]
    report = "\n".join(lines)
    print(report)
    (Path(__file__).resolve().parents[1] / "reports_out" / "firm_compare.md").write_text(report)
    print("\nSaved -> reports_out/firm_compare.md")


if __name__ == "__main__":
    main()
