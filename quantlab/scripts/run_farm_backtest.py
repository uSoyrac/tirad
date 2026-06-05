"""CHALLENGE-FARMING geriye-dönük backtest — son 8 ayda GERÇEK getirilerle ne olurdu?

Kullanıcı sorusu: son 8 ayda botumuzla HyroTrader 2-step challenge'ını tek tek koşsak,
kaç kez geçer, her funded olunca $200 çekip yeni fon alsak — toplam ne kâr ederdik?

Bu MONTE-CARLO değil — GERÇEK son-8-ay combo getirileri üzerinde sıralı (deterministik) bir
challenge-farming durum-makinesi. Tek bir gerçekleşme (yol), o yüzden birkaç başlangıç-ofseti
ile aralık da verilir. HyroTrader 2-step kuralları: P1 +10% / P2 +5%, günlük −5%, toplam
−10% TRAILING (EOD), min 10+5 gün. Funded'da kâr $200/0.8=$250 brüt olunca çek, döngü.

⚠️ Son 8 ay (2025-26) İYİ bir rejimdi (OOS Sharpe yüksek) → bu OPTIMIST bir tahmin.
   Survivorship + komisyon haircut'ı uygula. Gelecek bu kadar cömert olmayabilir.

Usage: python scripts/run_farm_backtest.py [account_size] [challenge_cost] [vol]
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
HAIRCUT = 0.60          # survivorship + komisyon dürüst indirimi
VOL_LOOKBACK = 20
# HyroTrader 2-step
P1, P2, DAILY, TOTAL = 0.10, 0.05, -0.05, -0.10
MIN1, MIN2 = 10, 5
SPLIT = 0.80
WITHDRAW = 200.0


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
    """Reduce the mean (edge) by (1-keep), preserve vol/shape — honest discount."""
    mu = r.mean()
    return (r - mu) + mu * keep


def farm(r, account, cost, withdraw=WITHDRAW, split=SPLIT):
    """Sequential challenge-farming state machine over the real return path r (np array)."""
    n = len(r)
    state = "buy"
    eq = peak = 1.0
    phase = 1
    dphase = 0
    n_buy = passes = fails = blowups = n_withdraw = 0
    total_cost = total_wd = 0.0
    log = []
    i = 0
    while i < n:
        if state == "buy":
            total_cost += cost
            n_buy += 1
            eq = peak = 1.0
            phase, dphase = 1, 0
            state = "challenge"
        ret = r[i]
        i += 1
        dphase += 1
        if state == "challenge":
            if ret <= DAILY:
                fails += 1
                state = "buy"
                continue
            eq *= (1 + ret)
            peak = max(peak, eq)
            if eq <= peak * (1 + TOTAL):
                fails += 1
                state = "buy"
                continue
            tgt, mind = (P1, MIN1) if phase == 1 else (P2, MIN2)
            if eq >= 1 + tgt and dphase >= mind:
                if phase == 1:
                    phase, dphase, eq, peak = 2, 0, 1.0, 1.0
                else:
                    passes += 1
                    state, eq, peak = "funded", 1.0, 1.0
                    log.append((i, "FUNDED"))
        elif state == "funded":
            if ret <= DAILY:
                blowups += 1
                state = "buy"
                log.append((i, "blowup"))
                continue
            eq *= (1 + ret)
            peak = max(peak, eq)
            if eq <= peak * (1 + TOTAL):
                blowups += 1
                state = "buy"
                log.append((i, "blowup"))
                continue
            if (eq - 1.0) * account * split >= withdraw:
                total_wd += withdraw
                n_withdraw += 1
                eq = peak = 1.0     # kârı çektik, taban'a dön
    return dict(n_buy=n_buy, passes=passes, fails=fails, blowups=blowups,
                n_withdraw=n_withdraw, withdrawn=total_wd, cost=total_cost,
                net=total_wd - total_cost, funded_log=log)


def main():
    account = float(sys.argv[1]) if len(sys.argv) > 1 else 25000.0
    cost = float(sys.argv[2]) if len(sys.argv) > 2 else 249.0
    vol = float(sys.argv[3]) if len(sys.argv) > 3 else 0.10
    keep = float(sys.argv[4]) if len(sys.argv) > 4 else HAIRCUT

    combo = crypto_combo()
    sized = vol_target(combo, vol)
    sized = haircut_returns(sized, keep)
    # son 8 ay
    end = sized.index[-1]
    start = end - pd.DateOffset(months=8)
    win = sized[(sized.index >= start) & (sized.index <= end)]

    lines = ["# Challenge-farming geriye-dönük backtest (HyroTrader 2-step, gerçek son 8 ay)", "",
             f"Hesap ${account:,.0f} | challenge ${cost:.0f} | vol-hedef %{vol*100:.0f} | "
             f"haircut ×{HAIRCUT} | pencere {win.index[0].date()}→{win.index[-1].date()} ({len(win)} gün).",
             f"Kurallar: P1 +{P1*100:.0f}% / P2 +{P2*100:.0f}%, günlük {DAILY*100:.0f}%, toplam "
             f"{TOTAL*100:.0f}% trailing, min {MIN1}+{MIN2} gün, %{SPLIT*100:.0f} split, her ${WITHDRAW:.0f}'da çek.", ""]

    # ana yol (ofset 0) + ofset aralığı
    base = farm(win.to_numpy(), account, cost)
    lines += ["## Ana senaryo (gerçek yol, baştan başla)", "",
              f"- Alınan challenge: **{base['n_buy']}** | Geçilen (funded): **{base['passes']}** | "
              f"Başarısız challenge: {base['fails']} | Funded patlama: {base['blowups']}",
              f"- Para çekme: **{base['n_withdraw']} kez × ${WITHDRAW:.0f} = ${base['withdrawn']:,.0f}**",
              f"- Challenge maliyeti: ${base['cost']:,.0f}",
              f"- **NET (8 ayda): ${base['net']:,.0f}**", ""]

    # başlangıç-ofsetli aralık (tek-yol gürültüsünü göster)
    offs = range(0, 61, 10)
    nets, passes_l, wd_l = [], [], []
    for o in offs:
        if o >= len(win):
            break
        res = farm(win.to_numpy()[o:], account, cost)
        nets.append(res["net"])
        passes_l.append(res["passes"])
        wd_l.append(res["n_withdraw"])
    lines += ["## Başlangıç-ofsetli aralık (tek-yol gürültüsü — farklı günde başlasak)", "",
              f"- Geçiş sayısı: medyan {int(np.median(passes_l))}, aralık [{min(passes_l)}–{max(passes_l)}]",
              f"- Para çekme: medyan {int(np.median(wd_l))} kez",
              f"- NET: medyan **${np.median(nets):,.0f}**, aralık [${min(nets):,.0f} – ${max(nets):,.0f}]", "",
              "## Yorum (dürüst)", "",
              f"- Son 8 ayda (gerçek getiriler, %{vol*100:.0f} vol, haircut'lı) bu farming döngüsü "
              f"medyanda ~{int(np.median(passes_l))} kez funded olur, ~${np.median(nets):,.0f} NET bırakır.",
              "- ⚠️ **2025-26 İYİ rejimdi** (OOS Sharpe yüksek) → bu OPTIMIST. Ayı/yatay rejimde "
              "geçiş oranı ve net DÜŞER; başarısız challenge maliyeti birikir.",
              "- ⚠️ Tek-yol: ofset aralığı gürültüyü gösterir; gerçek gelecek dağılım Monte-Carlo "
              "(run_propfirm_multi) ile ~%35 geçiş olasılığıydı — buradaki yüksek geçiş, pencerenin "
              "cömertliğinden.",
              "- ⚠️ Komisyon (taker ~%0.055 + spread) bu modelde haircut içinde kabaca; yüksek "
              "turnover'da ayrıca yer → gerçek net daha düşük olabilir. Paralel hesaplarla ölçeklenir "
              "ama her biri ayrı challenge maliyeti + ayrı patlama riski taşır."]
    report = "\n".join(lines)
    print(report)
    (Path(__file__).resolve().parents[1] / "reports_out" / "farm_backtest.md").write_text(report)
    print("\nSaved -> reports_out/farm_backtest.md")


if __name__ == "__main__":
    main()
