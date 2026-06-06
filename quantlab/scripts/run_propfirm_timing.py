"""PROP REJİM-ZAMANLAMASI — challenge'ı NE ZAMAN başlatmak geçiş şansını artırır?

Alfayı/sizing'i değil ZAMANLAMAYI optimize eder: geçmişteki HER başlangıç gününden 2-step
challenge'ı ileri-simüle eder (gerçek takvim, trailing DD), geçiş/başarısızlığı o günkü REJİM
sinyaliyle ilişkilendirir. Favori-rejimde başlayanlar belirgin daha çok geçiyorsa → 'yeşil ışıkta
başla' kuralı (screener ile). Overfitting değil; sinyal sabit, sadece giriş günü seçiliyor.

Rejim sinyalleri (t gününde, nedensel): combo trailing 20g getiri, trailing 20g vol.
Usage: python scripts/run_propfirm_timing.py [vol]
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
DAILY, TOTAL = -0.05, -0.10
PHASES = [(0.10, 10), (0.05, 5)]
MAXD = 120          # bir challenge için ileri pencere


def combo():
    R = pd.read_parquet(SLEEVE3)[["crypto_trend", "crypto_funding"]]
    iv = 1.0 / R[R.index < CUT].std().to_numpy()
    return pd.Series(R.to_numpy() @ (iv / iv.sum()), index=R.index)


def vol_target(r, target, lb=20):
    realized = r.rolling(lb).std().shift(1) * np.sqrt(PPY)
    return (r * (target / realized).clip(upper=3.0).fillna(0.0)).dropna()


def haircut(r, keep):
    return (r - r.mean()) + r.mean() * keep


def challenge_from(arr, start):
    """start gününden 2-step challenge ileri-simüle: geçti mi?"""
    eq = peak = 1.0
    phase = 0
    dphase = 0
    for j in range(start, min(start + MAXD * 2, len(arr))):
        dphase += 1
        ret = arr[j]
        if ret <= DAILY:
            return False
        eq *= (1 + ret)
        peak = max(peak, eq)
        if eq <= peak * (1 + TOTAL):
            return False
        tgt, mind = PHASES[phase]
        if eq >= 1 + tgt and dphase >= mind:
            phase += 1
            if phase >= len(PHASES):
                return True
            eq = peak = 1.0
            dphase = 0
    return False


def main():
    vol = float(sys.argv[1]) if len(sys.argv) > 1 else 0.15
    book = haircut(vol_target(combo(), vol), HAIRCUT)
    raw = combo()
    mom20 = raw.rolling(20).sum()          # rejim: trailing 20g toplam getiri
    vol20 = raw.rolling(20).std()          # rejim: trailing 20g vol
    arr = book.to_numpy()
    idx = book.index

    rows = []
    for t in range(25, len(arr) - 30):     # yeterli ileri-pencere olan günler
        rows.append((idx[t], challenge_from(arr, t),
                     mom20.reindex([idx[t]]).iloc[0], vol20.reindex([idx[t]]).iloc[0]))
    df = pd.DataFrame(rows, columns=["ts", "pass", "mom20", "vol20"]).dropna()

    base = df["pass"].mean()
    lines = ["# PROP REJİM-ZAMANLAMASI — challenge'ı ne zaman başlatmalı (2-step, vol %{:.0f})".format(vol * 100), "",
             f"Gerçek takvim {len(df)} başlangıç günü. Koşulsuz P(geç) = **{base*100:.0f}%**. "
             "Rejim sinyaline göre terciller:", "",
             "| sinyal | alt-tercil P(geç) | üst-tercil P(geç) | fark |", "|---|---|---|---|"]
    best = (None, 0.0)
    for sig in ("mom20", "vol20"):
        q1, q2 = df[sig].quantile(1 / 3), df[sig].quantile(2 / 3)
        lo = df[df[sig] <= q1]["pass"].mean()
        hi = df[df[sig] >= q2]["pass"].mean()
        lines.append(f"| {sig} | {lo*100:.0f}% | {hi*100:.0f}% | {(hi-lo)*100:+.0f} puan |")
        if abs(hi - lo) > abs(best[1]):
            best = (sig, hi - lo)

    # en iyi sinyalin favori yönünde başlama kuralı
    sig = best[0]
    favor_hi = best[1] > 0
    q = df[sig].quantile(2 / 3 if favor_hi else 1 / 3)
    fav = df[df[sig] >= q] if favor_hi else df[df[sig] <= q]
    lines += ["", "## Yorum (dürüst)", "",
              f"- Koşulsuz geçiş %{base*100:.0f}. En ayırt edici sinyal **{sig}**: "
              f"favori rejimde başlayınca P(geç) **%{fav['pass'].mean()*100:.0f}** "
              f"({'yüksek' if favor_hi else 'düşük'}-{sig} günlerinde başla).",
              f"- {'**Anlamlı kaldıraç:** ' if abs(best[1])>0.10 else '**Zayıf/marjinal:** '}"
              f"rejim-zamanlaması geçişi {abs(best[1])*100:.0f} puan {'artırıyor' if best[1] else 'değiştirmiyor'}. "
              + ("Screener'la o günü bekleyip challenge'ı o zaman al." if abs(best[1]) > 0.10
                 else "Zamanlama tek başına büyük fark yapmıyor; vol-seviyesi + firma-yapısı daha etkili."),
              "- ⚠️ Tek-dönem (2023-26), survivorship; gerçek takvim → örneklem sınırlı, terciller "
              "gürültülü. Yön doğru olsa da büyüklüğü temkinli oku.",
              "- **Pratik:** en yüksek-EV geçiş kaldıraçları sırayla: (1) FİRMA-YAPISI (Breakout "
              "statik-DD 1-step ~%48 > HyroTrader trailing 2-step ~%35), (2) VOL-SEVİYESİ (~%15), "
              f"(3) REJİM-ZAMANLAMASI ({sig}, {'+' if best[1]>0 else ''}{best[1]*100:.0f} puan). "
              "Akıllı de-risk ise ZARAR veriyordu."]
    report = "\n".join(lines)
    print(report)
    (Path(__file__).resolve().parents[1] / "reports_out" / "propfirm_timing.md").write_text(report)
    print("\nSaved -> reports_out/propfirm_timing.md")


if __name__ == "__main__":
    main()
