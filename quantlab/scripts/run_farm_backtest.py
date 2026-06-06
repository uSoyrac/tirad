"""CHALLENGE-FARMING geriye-dönük backtest — HyroTrader $5K, $59 İADE-EDİLEBİLİR ücret.

Gerçek ekran: Two-Step 5,000 USDT = $59, "fully refundable challenge fee" (ilk ödemede ücret
GERİ İADE), up to 90% split, avg payout $206. One-Step: 5 gün + %10 hedef, doğrulama yok.

İADE mantığı oyunu değiştirir: GEÇİLEN challenge'ın $59'u geri gelir → yalnız BAŞARISIZ
denemeler net maliyet. Bunu modelleyip son-8-ay GERÇEK getirilerde sıralı simüle eder.

Modlar:
  one_step : tek faz, hedef +10%, DD %6 trailing, günlük %4, min 5 gün
  two_step : P1 +10% / P2 +5%, DD %10 trailing, günlük %5, min 10+5 gün

⚠️ 2025-26 İYİ rejimdi → optimist. Survivorship + komisyon haircut. Tek-yol + ofset aralığı.

Usage: python scripts/run_farm_backtest.py [mode] [vol] [keep] [withdraw]
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
VOL_LOOKBACK = 20
ACCOUNT = 5000.0
FEE = 59.0
SPLIT = 0.80          # default (up to 90%); konservatif
WITHDRAW = 200.0
MODES = {
    "one_step": {"phases": [(0.10, 5)], "daily": -0.04, "total": -0.06},
    "two_step": {"phases": [(0.10, 10), (0.05, 5)], "daily": -0.05, "total": -0.10},
}


def crypto_combo():
    R = pd.read_parquet(SLEEVE3)[["crypto_trend", "crypto_funding"]]
    Rtr = R[R.index < CUT]
    iv = 1.0 / Rtr.std().to_numpy()
    w = iv / iv.sum()
    return pd.Series(R.to_numpy() @ w, index=R.index)


def vol_target(r, target, lookback=VOL_LOOKBACK, maxlev=3.0):
    realized = r.rolling(lookback).std().shift(1) * np.sqrt(PPY)
    lev = (target / realized).clip(upper=maxlev).fillna(0.0)
    return (r * lev).dropna()


def haircut_returns(r, keep):
    mu = r.mean()
    return (r - mu) + mu * keep


def farm(r, phases, daily, total, account=ACCOUNT, fee=FEE, refundable=True,
         withdraw=WITHDRAW, split=SPLIT):
    n = len(r)
    state = "buy"
    eq = peak = 1.0
    pidx = dphase = 0
    refunded = False
    n_buy = passes = fails = blowups = n_wd = 0
    total_fee = total_wd = total_refund = 0.0
    i = 0
    while i < n:
        if state == "buy":
            total_fee += fee
            n_buy += 1
            eq = peak = 1.0
            pidx = dphase = 0
            refunded = False
            state = "challenge"
        ret = r[i]
        i += 1
        dphase += 1
        if state == "challenge":
            if ret <= daily:
                fails += 1
                state = "buy"
                continue
            eq *= (1 + ret)
            peak = max(peak, eq)
            if eq <= peak * (1 + total):
                fails += 1
                state = "buy"
                continue
            tgt, mind = phases[pidx]
            if eq >= 1 + tgt and dphase >= mind:
                pidx += 1
                if pidx >= len(phases):
                    passes += 1
                    state, eq, peak = "funded", 1.0, 1.0
                else:
                    eq, peak, dphase = 1.0, 1.0, 0
        elif state == "funded":
            if ret <= daily:
                blowups += 1
                state = "buy"
                continue
            eq *= (1 + ret)
            peak = max(peak, eq)
            if eq <= peak * (1 + total):
                blowups += 1
                state = "buy"
                continue
            if (eq - 1.0) * account * split >= withdraw:
                total_wd += withdraw
                n_wd += 1
                if refundable and not refunded:   # ücret ilk ödemede iade
                    total_refund += fee
                    refunded = True
                eq = peak = 1.0
    return dict(n_buy=n_buy, passes=passes, fails=fails, blowups=blowups, n_wd=n_wd,
                withdrawn=total_wd, refund=total_refund, fee=total_fee,
                net=total_wd + total_refund - total_fee)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "two_step"
    vol = float(sys.argv[2]) if len(sys.argv) > 2 else 0.20
    keep = float(sys.argv[3]) if len(sys.argv) > 3 else HAIRCUT
    withdraw = float(sys.argv[4]) if len(sys.argv) > 4 else WITHDRAW
    cfg = MODES[mode]

    sized = haircut_returns(vol_target(crypto_combo(), vol), keep)
    end = sized.index[-1]
    win = sized[(sized.index >= end - pd.DateOffset(months=8)) & (sized.index <= end)]
    arr = win.to_numpy()

    base = farm(arr, cfg["phases"], cfg["daily"], cfg["total"], withdraw=withdraw)
    offs = [o for o in range(0, 61, 10) if o < len(arr)]
    runs = [farm(arr[o:], cfg["phases"], cfg["daily"], cfg["total"], withdraw=withdraw) for o in offs]
    nets = [x["net"] for x in runs]
    passes = [x["passes"] for x in runs]
    wds = [x["n_wd"] for x in runs]

    lines = [f"# Challenge-farming — HyroTrader {mode}, $5K, $59 İADE-edilebilir (gerçek son 8 ay)", "",
             f"Mod {mode} | hedef {cfg['phases']} | günlük {cfg['daily']*100:.0f}% | toplam "
             f"{cfg['total']*100:.0f}% trailing | vol %{vol*100:.0f} | haircut ×{keep} | split %{SPLIT*100:.0f} | "
             f"çek ${withdraw:.0f} | pencere {win.index[0].date()}→{win.index[-1].date()} ({len(win)} gün).", "",
             "## Ana senaryo (baştan)", "",
             f"- Challenge: **{base['n_buy']}** | Funded: **{base['passes']}** | Başarısız: {base['fails']} | "
             f"Funded patlama: {base['blowups']}",
             f"- Para çekme: {base['n_wd']}× = ${base['withdrawn']:.0f} | Ücret iadesi: ${base['refund']:.0f} | "
             f"Ücret ödenen: ${base['fee']:.0f}",
             f"- **NET (8 ay): ${base['net']:,.0f}**", "",
             "## Ofset aralığı (tek-yol gürültüsü)", "",
             f"- Funded: medyan {int(np.median(passes))} [{min(passes)}–{max(passes)}] | "
             f"çekme medyan {int(np.median(wds))}×",
             f"- **NET: medyan ${np.median(nets):,.0f}, aralık [${min(nets):,.0f} – ${max(nets):,.0f}]**", "",
             "## Yorum (dürüst)", "",
             "- İADE-edilebilir ücret oyunu değiştirir: geçilen challenge'ın $59'u geri gelir → "
             "yalnız BAŞARISIZ denemeler net maliyet. Yine de net, geçiş+funded-hayatta-kalmaya bağlı.",
             f"- Medyan NET ${np.median(nets):,.0f}: " + (
                 "POZİTİF — iade + çekimler başarısız maliyetini aşıyor." if np.median(nets) > 0
                 else "NEGATİF — funded'da $200 biriktirmeden trailing-DD patlaması + başarısız ücretler."),
             "- ⚠️ 2025-26 cömert rejim (optimist). One-Step DD %6 trailing daha sıkı ama tek-faz+5gün "
             "hızlı; two-step %10 DD daha gevşek ama 2 faz. $5K'da $200 çekmek +%5 gerektirir (zor).",
             "- ⚠️ Komisyon haircut'ta kabaca; gerçek net daha düşük olabilir. Önce TESTNET doğrula."]
    report = "\n".join(lines)
    print(report)
    (Path(__file__).resolve().parents[1] / "reports_out" / "farm_backtest.md").write_text(report)
    print("\nSaved -> reports_out/farm_backtest.md")


if __name__ == "__main__":
    main()
