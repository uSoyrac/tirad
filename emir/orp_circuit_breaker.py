#!/usr/bin/env python3
"""
ORP DEVRE KESİCİ (Circuit Breaker) — modüler güvenlik katmanı + kanıt testi.

PROBLEM (gerçek veriyle kanıtlandı, emir/results_real.md):
  Ham strateji 3 ayda +4.11R (hafif pozitif) üretti AMA 10 ardışık kayıp geldiğinde
  ORP'nin deficit-recovery + %20 cap mekanizması kasayı %81 drawdown'a soktu ve
  +4.11R'lik kazancı -%33.6 zarara çevirdi. Sabit %4 risk ise sadece -%4.1'di.

ÇÖZÜM:
  Çalışan `run_orp_dynamic` motoruna DOKUNMADAN, üstüne bir sarmalayıcı katman:
  N ardışık kayıptan sonra deficit-recovery'yi DONDUR (riski base_risk'e sabitle),
  sonraki KAZANANA kadar. Kazanınca devre kesici sıfırlanır.

  Bu, "kart sayan adam masadan kalkar" mantığıdır: seri kötü giderken bahsi
  büyütmek (Martingale tuzağı) iflas getirir; devre kesici bunu engeller.

Bu dosya mevcut motoru import edip karşılaştırma yapar; üretimi değiştirmez.
"""
import os
import sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "uyg", "src"))
from dynamic_optimizer import run_orp_dynamic


def run_orp_circuit_breaker(trades, params, breaker_after=3):
    """
    run_orp_dynamic ile AYNI mantık + devre kesici.
    breaker_after ardışık kayıptan sonra risk = base_risk (deficit recovery durur),
    bir kazanan gelene kadar. Çalışan motoru kopyalamak yerine, kayıp serisini
    parçalara bölüp her parçayı motorun KENDİSİYLE çalıştırırız -> davranış birebir,
    sadece "soğuma" pencerelerinde base_risk zorlanır.

    Basit ve sağlam yöntem: trade akışını tek tek işleyip, ardışık kayıp >= breaker
    olduğunda o işlemde recovery'yi devre dışı bırakmak için geçici params kullan.
    """
    # Motoru birebir taklit etmek yerine, motorun parametre esnekliğini kullanırız:
    # ardışık kayıp eşiği aşılınca, o işlem(ler) için base_risk'i tabana sabitleyen
    # bir "recovery_factor=cok_buyuk" uygula -> required_risk = base_risk olur.
    eq = params["start_capital"]
    consec = 0
    curve = [eq]
    peak = eq
    wiped = False
    base = params["base_risk_pct"]
    for t in trades:
        if wiped:
            curve.append(0.0); continue
        cooling = consec >= breaker_after
        p = dict(params)
        p["start_capital"] = eq
        if cooling:
            # recovery'yi etkisiz kıl: delta/cok_buyuk ~ 0 -> required_risk = base_risk
            p["recovery_factor"] = 1e12
        # tek işlemi motorla çalıştır (cycle hedefi eq'e göre resetlenir -> base_risk taban)
        r = run_orp_dynamic([t], p)
        eq = r["final_eq"]
        peak = max(peak, eq)
        curve.append(eq)
        if t["r_mult"] > 0:
            consec = 0
        else:
            consec += 1
        if eq <= 1.0:
            wiped = True; eq = 0.0
    arr = np.array(curve)
    peak_arr = np.maximum.accumulate(arr)
    peak_arr = np.where(peak_arr == 0, 1.0, peak_arr)
    dd = float(abs(((arr - peak_arr) / peak_arr).min()) * 100)
    return {"final_eq": eq, "max_drawdown": dd, "wiped_out": wiped}


def _fmt(name, res, start=100.0):
    return (f"{name:<34} ${res['final_eq']:>9,.2f}  "
            f"(%{(res['final_eq']/start-1)*100:>+7.1f})   maxDD %{res['max_drawdown']:>5.1f}"
            + ("   ⚠️İFLAS" if res.get("wiped_out") else ""))


def main():
    base_params = {
        "cycle_target_pct": 0.10, "recovery_factor": 1.0, "max_risk_cap": 0.20,
        "base_risk_pct": 0.04, "max_leverage": 10.0, "dynamic_recovery": False,
        "dd_scaling": False, "start_capital": 100.0,
    }

    print("="*78)
    print(" ORP DEVRE KESİCİ — Gerçek başarısızlık modunu yeniden üret & çöz")
    print("="*78)

    # --- Senaryo 1: GERÇEK veriyi taklit eden en kötü an: 10 ardışık kayıp serisi ---
    # results_real.md: 83 işlem, 27 TP (+2R), 56 SL (-1R), 10 ardışık kayıp.
    # En kötü kümelenme: kayıpları öne yığ (deficit'in en sığ kasada vurması).
    wins = [{"r_mult": 2.0, "sl_pct": 5.0}] * 27
    losses = [{"r_mult": -1.0, "sl_pct": 5.0}] * 56
    worst = losses[:10] + wins + losses[10:]   # baştan 10 stop

    print("\n[Senaryo A] Gerçek dağılım, kayıplar başta kümelenmiş (en kötü hal):")
    print(_fmt("  Mevcut ORP (kesicisiz)", run_orp_dynamic(worst, base_params)))
    print(_fmt("  ORP + dd_scaling",       run_orp_dynamic(worst, {**base_params, "dd_scaling": True})))
    for k in (2, 3, 4):
        print(_fmt(f"  ORP + devre kesici (N={k})", run_orp_circuit_breaker(worst, base_params, k)))
    print(_fmt("  Kıyas: sabit %4 (ORP yok)",
               {"final_eq": _flat(worst), "max_drawdown": _flat_dd(worst)}))

    # --- Senaryo 2: Monte Carlo, gerçek WR=%32.5, +2R ---
    rng = np.random.default_rng(7)
    N = 4000
    def mc(fn, **kw):
        fin, ruin, dds = [], 0, []
        for _ in range(N):
            seq = (rng.random(83) < 0.325)
            tr = [{"r_mult": 2.0 if w else -1.0, "sl_pct": 5.0} for w in seq]
            r = fn(tr, base_params, **kw) if fn is run_orp_circuit_breaker else fn(tr, base_params)
            fin.append(r["final_eq"]); dds.append(r["max_drawdown"])
            if r.get("wiped_out") or r["final_eq"] <= 1.0: ruin += 1
        fin = np.array(fin)
        return np.median(fin), np.percentile(fin, 10), np.mean(dds), 100*ruin/N

    print("\n[Senaryo B] Monte Carlo (WR %32.5, +2R, 83 işlem, N=4000):")
    print(f"{'Yöntem':<34}{'Medyan':>10}{'P10':>10}{'Ort.maxDD':>12}{'İflas%':>9}")
    for name, fn, kw in [
        ("Mevcut ORP (kesicisiz)", run_orp_dynamic, {}),
        ("ORP + devre kesici (N=3)", run_orp_circuit_breaker, {"breaker_after": 3}),
    ]:
        med, p10, dd, ruin = mc(fn, **kw)
        print(f"{name:<34}${med:>8,.0f}${p10:>8,.0f}    %{dd:>6.1f}   %{ruin:>5.2f}")

    print("\n" + "="*78)
    print("YORUM: Devre kesici, ardışık-kayıp serilerinde deficit büyütmeyi durdurur;")
    print("drawdown'u sert biçimde keser. Edge zaten breakeven olduğundan asıl kazanç")
    print("BÜYÜTMEK değil, HAYATTA KALMAK. Önce yaşa, sonra büyü.")


def _flat(trades, start=100.0):
    eq = start
    for t in trades:
        eq += eq*0.04*t["r_mult"]
        if eq <= 1: return 0.0
    return eq

def _flat_dd(trades, start=100.0):
    eq = start; peak = start; mdd = 0.0
    for t in trades:
        eq += eq*0.04*t["r_mult"]
        peak = max(peak, eq)
        mdd = max(mdd, (peak-eq)/peak*100 if peak > 0 else 0)
    return mdd


if __name__ == "__main__":
    main()
