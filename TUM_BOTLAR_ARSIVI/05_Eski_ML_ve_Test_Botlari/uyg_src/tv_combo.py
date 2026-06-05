#!/usr/bin/env python3
"""
tv_combo.py — KOMBİNASYON: baseline trend edge üstüne açıların YIĞINI (stack)
═══════════════════════════════════════════════════════════════════════════════
Önceki tek-tek testlerde (tv_regime_adaptive / tv_kalman / tv_isotropic) hiçbiri
"real_improvement" çıkmadı; en iyi ihtimalle "neutral". Bu script bunları baseline
trend edge (donchian+supertrend) üstüne YIĞAR ve birlikte Calmar (CAGR/MDD) ile
whipsaw'a etkisini ÖLÇER. Soru: stack tek-tek'lerden iyi mi yoksa over-filtre mi?

Kollar (hepsi AYNI 4H veri, leak-free, default param — in-sample sweep YOK):
  A   = baseline (donchian + sabit-çarpan supertrend)              [portfolio_sim.STRATS]
  G   = A + BTC-rejim-gate (binary, causal)                        [tv_regime_adaptive]
  K   = A + Kalman-eğim FİLTRE (her kol yönü Kalman onaylı)        [tv_kalman]
  I   = A + isotropic consensus FİLTRE (cons>=2)                   [tv_isotropic]
  GK  = A + gate + Kalman
  GKI = A + gate + Kalman + isotropic   (TAM YIĞIN)
  G+adaptST = adaptif-çarpan supertrend (çekirdek) + gate          [tv_regime_adaptive C+B]

ÖLÇÜM: simulate + portfolio_run. Calmar/MDD/CAGR/whipsaw/E[R]/N.
Robustluk: walk-forward OOS (ilk60/son40 exit_ts'e göre) + per-coin (+ oranı).
MDD-bütçe normalizasyonu: her kolu MDD~%25 hedefe getirmek için risk% ölçekle,
o risk%'te CAGR ne olur → compound kazanç adil kıyas.
DÜRÜST: stack edge'i öldürürse (N çöker / E düşer / Calmar baseline altına iner) söyle.
"""
import json, numpy as np, pandas as pd
import warnings; warnings.filterwarnings("ignore")
from signal_lab import load_all, simulate, metrics, BARS_PER_YEAR
import sig_donchian_breakout as D, sig_supertrend_regime as S
from portfolio_sim import portfolio_run

# önceki scriptlerden gerçek bileşenleri import et (yeniden yazma yok)
from tv_regime_adaptive import btc_regime_gate, apply_gate, make_sig_adaptive_supertrend
from tv_kalman import kalman_slope_sign
from tv_isotropic import consensus_features

SPAN_Y = 5.4
DONCH = D.make_sig(40, "atr", 0.25, 0.0)
SUPER = S.make_sig(10, 3, 25)
SUPER_ADAPT = make_sig_adaptive_supertrend(10, 25)

# baseline kol tanımı: (isim, sinyal-üretici, sl_atr, tp_r)
BASE_ARMS = [("donchian", DONCH, 2.0, 2.5), ("supertrend", SUPER, 2.0, 3.0)]


# ── FİLTRELER (sinyal dizisi -> filtreli sinyal dizisi), leak-free ──
def kalman_filter(df, pos):
    """baseline pos'u Kalman eğimi AYNI yönde iken tut (tv_kalman (b) mantığı)."""
    ks = kalman_slope_sign(df)
    out = np.asarray(pos, float).copy()
    out[(out != 0) & (ks != out)] = 0.0
    return out

def isotropic_filter(df, pos, cons_min=2, ang_min=0.0):
    """baseline pos'u çok-ölçekli consensus hizalı+yeterli iken tut (tv_isotropic)."""
    sc, ma = consensus_features(df)
    out = np.zeros(len(pos))
    for i in range(len(pos)):
        d = pos[i]
        if d == 0: continue
        s = sc[i]; a = ma[i]
        if not (np.isfinite(s) and np.isfinite(a)): continue
        aligned = s if (s * d > 0) else 0
        if abs(aligned) >= cons_min and abs(a) >= ang_min and a * d > 0:
            out[i] = d
    return out


def make_arm_sig(base_sig, filters):
    """base sinyal-üreticisini sıralı filtrelerle sarmala."""
    def sig(df):
        pos = np.asarray(base_sig(df), float)
        for f in filters:
            pos = f(df, pos)
        return pos
    return sig


def build_stream(arms, gate_map=None):
    """arms: [(name, sig, sl, tp)]. gate_map verilirse BTC-gate uygulanır."""
    dfs = load_all("mktdata", "4h")
    tr = []
    for name, sig, sl, tp in arms:
        for c, df in dfs.items():
            for t in simulate(df, sig(df), sl_atr=sl, tp_r=tp):
                t["coin"] = c; t["strat"] = name; tr.append(t)
    tr.sort(key=lambda x: x["entry_ts"])
    if gate_map is not None:
        tr = apply_gate(tr, gate_map)
    return tr


def whipsaw(trades):
    if len(trades) < 2: return 0.0
    dirs = [t["dir"] for t in sorted(trades, key=lambda x: x["entry_ts"])]
    flips = sum(1 for i in range(1, len(dirs)) if dirs[i] != dirs[i-1])
    return flips / len(dirs)


def mdd_normalized_cagr(trades, target_mdd=25.0, mc=20):
    """MDD'yi target_mdd'ye getirecek risk% bul (kaba arama), o risk%'te CAGR/end$ döndür.
    Compound adil kıyas: aynı MDD bütçesinde hangi kol daha çok katlar?"""
    best = None
    for risk in np.arange(0.005, 0.121, 0.005):
        eq, mdd, _ = portfolio_run(trades, risk=float(risk), max_concurrent=mc)
        if mdd <= target_mdd:
            best = (float(risk), eq, mdd)
        else:
            break  # MDD risk'le monoton artar; ilk aşımda dur
    if best is None:
        return {"risk": 0.0, "end": 100.0, "mdd": 0.0, "cagr": 0.0, "mult": 1.0}
    risk, eq, mdd = best
    x = eq / 100; cagr = (x ** (1/SPAN_Y) - 1) * 100 if x > 0 else -100
    return {"risk": risk, "end": eq, "mdd": mdd, "cagr": cagr, "mult": x}


def eval_arm(label, trades):
    m = metrics(trades)
    if m["n"] == 0:
        return {"label": label, "n": 0}
    eq, mdd, _ = portfolio_run(trades, risk=0.02, max_concurrent=20)
    x = eq/100; cagr = (x**(1/SPAN_Y)-1)*100 if x > 0 else -100
    calmar = cagr/mdd if mdd > 0 else float("inf")
    ws = whipsaw(trades)
    srt = sorted(trades, key=lambda x: x["exit_ts"])
    sp = int(len(srt)*0.6)
    tr_m = metrics(srt[:sp]); te_m = metrics(srt[sp:])
    coins = sorted(set(t["coin"] for t in trades))
    pc_pos = sum(1 for c in coins if metrics([t for t in trades if t["coin"]==c]).get("avg_r",-9) > 0)
    norm = mdd_normalized_cagr(trades, target_mdd=25.0)
    span = 11860
    return {"label": label, "n": m["n"], "freq": m["n"]/(span/BARS_PER_YEAR),
            "wr": m["wr"], "avg_r": m["avg_r"], "pf": m["pf"],
            "mdd": mdd, "cagr": cagr, "calmar": calmar, "whipsaw": ws,
            "oos_train": tr_m.get("avg_r",0), "oos_test": te_m.get("avg_r",0),
            "pc_pos": pc_pos, "pc_tot": len(coins),
            "norm_risk": norm["risk"], "norm_cagr": norm["cagr"],
            "norm_mdd": norm["mdd"], "norm_mult": norm["mult"]}


def show(r):
    if r.get("n", 0) == 0:
        print(f"[{r['label']:24s}] N=0 (filtre/gate her şeyi kapattı)"); return
    print(f"[{r['label']:24s}] N={r['n']:5d} freq={r['freq']:5.0f} WR={r['wr']:5.1f}% "
          f"E={r['avg_r']:+.3f}R PF={r['pf']:.2f}")
    print(f"{'':26s} MDD={r['mdd']:5.1f}% CAGR={r['cagr']:6.1f}% Calmar={r['calmar']:5.3f} "
          f"whipsaw={r['whipsaw']:.3f}")
    print(f"{'':26s} OOS tr={r['oos_train']:+.3f} te={r['oos_test']:+.3f}  "
          f"pc+={r['pc_pos']}/{r['pc_tot']}  | MDD~25%-norm: risk={r['norm_risk']*100:.1f}% "
          f"-> CAGR={r['norm_cagr']:.1f}% ({r['norm_mult']:.1f}x, MDD={r['norm_mdd']:.1f}%)")


def main():
    print("=" * 100)
    print("  TV_COMBO — baseline trend edge üstüne açı YIĞINI (stack). AYNI 4H veri, leak-free.")
    print("  HEDEF: Calmar (CAGR/MDD) baseline 1.385'i geçiyor mu? whipsaw azalıyor mu? over-filtre mi?")
    print("=" * 100)

    dfs = load_all("mktdata", "4h")
    gate_map = btc_regime_gate(dfs)
    print(f"  BTC-gate açık bar oranı: {np.mean(list(gate_map.values()))*100:.1f}%\n")

    res = {}

    # A baseline
    A = eval_arm("A baseline", build_stream(BASE_ARMS)); show(A); res["A"] = A

    # G = A + gate
    G = eval_arm("G = A+BTCgate", build_stream(BASE_ARMS, gate_map=gate_map)); show(G); res["G"] = G

    # K = A + Kalman filtre
    arms_K = [("donchian", make_arm_sig(DONCH, [kalman_filter]), 2.0, 2.5),
              ("supertrend", make_arm_sig(SUPER, [kalman_filter]), 2.0, 3.0)]
    K = eval_arm("K = A+Kalman", build_stream(arms_K)); show(K); res["K"] = K

    # I = A + isotropic filtre
    arms_I = [("donchian", make_arm_sig(DONCH, [isotropic_filter]), 2.0, 2.5),
              ("supertrend", make_arm_sig(SUPER, [isotropic_filter]), 2.0, 3.0)]
    I = eval_arm("I = A+isotropic", build_stream(arms_I)); show(I); res["I"] = I

    # GK = A + gate + Kalman
    GK = eval_arm("GK = A+gate+Kalman", build_stream(arms_K, gate_map=gate_map)); show(GK); res["GK"] = GK

    # GI = A + gate + isotropic
    GI = eval_arm("GI = A+gate+isotropic", build_stream(arms_I, gate_map=gate_map)); show(GI); res["GI"] = GI

    # GKI = TAM YIĞIN: gate + Kalman + isotropic
    arms_KI = [("donchian", make_arm_sig(DONCH, [kalman_filter, isotropic_filter]), 2.0, 2.5),
               ("supertrend", make_arm_sig(SUPER, [kalman_filter, isotropic_filter]), 2.0, 3.0)]
    GKI = eval_arm("GKI = TAM YIĞIN", build_stream(arms_KI, gate_map=gate_map)); show(GKI); res["GKI"] = GKI

    # adaptST + gate (regime-adaptive çekirdek + gate), filtresiz ve filtreli
    arms_adapt = [("donchian", DONCH, 2.0, 2.5), ("supertrend", SUPER_ADAPT, 2.0, 3.0)]
    GA = eval_arm("GA = adaptST+gate", build_stream(arms_adapt, gate_map=gate_map)); show(GA); res["GA"] = GA

    print("\n" + "=" * 100)
    print("  ÖZET TABLO (risk2%/mc20):")
    print(f"  {'arm':24s}{'N':>6}{'E[R]':>8}{'MDD%':>7}{'CAGR%':>8}{'Calmar':>8}{'whip':>7}{'pc+':>6}"
          f"{'norm-CAGR@MDD25':>17}")
    for k in ["A","G","K","I","GK","GI","GKI","GA"]:
        r = res[k]
        if r.get("n",0) == 0:
            print(f"  {r['label']:24s}{'N=0':>6}"); continue
        print(f"  {r['label']:24s}{r['n']:>6}{r['avg_r']:>+8.3f}{r['mdd']:>7.1f}{r['cagr']:>8.1f}"
              f"{r['calmar']:>8.3f}{r['whipsaw']:>7.3f}{r['pc_pos']:>4}/{r['pc_tot']:<1}"
              f"{r['norm_cagr']:>14.1f}%")

    base_calmar = res["A"]["calmar"]
    print(f"\n  VERDICT yardımcısı: baseline Calmar={base_calmar:.3f}, MDD-norm CAGR@25%={res['A']['norm_cagr']:.1f}%")
    best = max((k for k in res if res[k].get("n",0)>0 and k!="A"),
               key=lambda k: res[k]["calmar"])
    print(f"  En yüksek Calmar (A hariç): {res[best]['label']} = {res[best]['calmar']:.3f} "
          f"({'GEÇTI' if res[best]['calmar']>base_calmar else 'GEÇEMEDI'})")

    json.dump(res, open("/tmp/tv_combo.json","w"), indent=2)
    print("\n  /tmp/tv_combo.json")


if __name__ == "__main__":
    main()
