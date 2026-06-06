#!/usr/bin/env python3
"""
tv_kalman.py — KALMAN ADAPTİF TREND FİLTRESİ (D7)
═══════════════════════════════════════════════════════════════════════
Tek-state causal Kalman trend takibi.
  meas[t] = EMA(close, span=KSPAN)            (düz EMA, fractional hile YOK)
  innovation = meas - X
  ATR ile normalize edilmiş residual'dan adaptif Q,R (kısa/uzun pencere var.)
  K = P/(P+R);  X += K*innov;  P = (1-K)(P+Q)
  slope[t] = X[t] - X[t-1]

İKİ kullanım:
  (a) TRIGGER : sign(slope) → standalone long/short, baseline ile kıyas.
  (b) FİLTRE  : baseline trend girişini SADECE Kalman eğimi aynı yönde iken al.

DÜRÜSTLÜK: default param, in-sample sweep YOK. TÜM feature shift(1) leak-free.
Kalman zaten causal (sadece geçmiş). Çıktı: simulate + portfolio_run.
Baseline vs (a) vs (b): MDD/CAGR/Calmar/whipsaw, walk-forward OOS, per-coin.
"""
import numpy as np
import pandas as pd
import warnings; warnings.filterwarnings("ignore")
from signal_lab import load_all, simulate, metrics, atr, ema, BARS_PER_YEAR
import sig_donchian_breakout as D, sig_supertrend_regime as S
from portfolio_sim import portfolio_run

# ── DEFAULT parametreler (sweep YOK, overfit kaçınma) ──
KSPAN   = 10     # ölçüm EMA span'ı (memory'deki ~10)
WIN_S   = 20     # kısa pencere (R: ölçüm gürültüsü)
WIN_L   = 60     # uzun pencere (Q: süreç/trend varyansı)

BASE = [   # baseline ensemble (memory'deki doğrulanmış edge)
    ("donchian",   D.make_sig(40, "atr", 0.25, 0.0), 2.0, 2.5),
    ("supertrend", S.make_sig(10, 3, 25),            2.0, 3.0),
]

# ── Kalman state serisi (causal, adaptif Q/R) ──
def kalman_state(df, kspan=KSPAN, win_s=WIN_S, win_l=WIN_L):
    c = df["close"].to_numpy(float)
    n = len(c)
    a = atr(df, 14)
    a = np.where(a > 0, a, np.nan)
    a = pd.Series(a).bfill().ffill().to_numpy()
    meas = ema(c, kspan)                      # düz EMA ölçüm

    # adaptif Q/R: ATR-normalize edilmiş ölçüm değişiminin rolling varyansı.
    # innovation proxy = meas farkının ATR'ye oranı (causal, sadece geçmiş)
    dmeas = np.diff(meas, prepend=meas[0]) / a
    s = pd.Series(dmeas)
    R_ser = s.rolling(win_s).var().bfill().to_numpy() + 1e-6   # kısa: gürültü
    Q_ser = s.rolling(win_l).var().bfill().to_numpy() + 1e-6   # uzun: süreç

    X = np.zeros(n); P = np.zeros(n)
    X[0] = meas[0]; P[0] = R_ser[0]
    for i in range(1, n):
        # predict
        P_pred = P[i-1] + Q_ser[i]
        # update (innovation ATR-normalize edilmeden ham fiyat ölçeğinde;
        # Q,R aynı normalize ölçekte oransal olduğu için K boyutsuz kalır)
        innov = meas[i] - X[i-1]
        K = P_pred / (P_pred + R_ser[i])
        X[i] = X[i-1] + K * innov
        P[i] = (1 - K) * P_pred
    return X

def kalman_slope_sign(df, **kw):
    """slope = X[t]-X[t-1]; sign → +1/-1. Causal."""
    X = kalman_state(df, **kw)
    slope = np.diff(X, prepend=X[0])
    sgn = np.sign(slope)
    sgn[:max(WIN_L + KSPAN, 200)] = 0   # warmup
    return sgn

# ── (a) TRIGGER: standalone Kalman ──
def sig_trigger(df):
    return kalman_slope_sign(df)

# ── (b) FİLTRE: baseline sinyalini Kalman eğimi onaylarsa al ──
def make_filtered(base_sig):
    def sig(df):
        raw = np.asarray(base_sig(df))
        ks = kalman_slope_sign(df)        # +1/-1, warmup'ta 0
        out = raw.copy()
        # sadece Kalman eğimi AYNI yönde iken işleme izin ver; aksi halde flat
        out[(raw != 0) & (ks != raw)] = 0.0
        return out
    return sig

# ── metrik yardımcıları ──
def whipsaw(sig_arr):
    """flip sayısı / nonzero-bar (yön değişim yoğunluğu)."""
    s = np.asarray(sig_arr)
    nz = s[s != 0]
    if len(nz) < 2: return 0.0
    flips = int((np.diff(nz) != 0).sum())
    return flips / len(nz)

def build_stream(strats):
    dfs = load_all("mktdata", "4h")
    tr = []
    for name, sig, sl, tp in strats:
        for c, df in dfs.items():
            for t in simulate(df, sig(df), sl_atr=sl, tp_r=tp):
                t["coin"] = c; t["strat"] = name; tr.append(t)
    tr.sort(key=lambda x: x["entry_ts"])
    return tr

def eval_block(strats, label):
    dfs = load_all("mktdata", "4h")
    pool = []; per_coin = {}; span_bars = 0; wsum = []; flip_total = 0; trade_total = 0
    for name, sig, sl, tp in strats:
        for c, df in dfs.items():
            arr = sig(df)
            tr = simulate(df, arr, sl_atr=sl, tp_r=tp)
            for t in tr: t["coin"] = c; t["strat"] = name
            per_coin.setdefault(c, []).extend(tr)
            pool += tr; span_bars = max(span_bars, len(df))
            wsum.append(whipsaw(arr))
    m = metrics(pool)
    pool.sort(key=lambda x: x["exit_ts"])
    split = int(len(pool) * 0.6)
    tr_m = metrics(pool[:split]); te_m = metrics(pool[split:])
    pc = {c: metrics(ts) for c, ts in per_coin.items()}
    pos_coins = sum(1 for c, cm in pc.items() if cm.get("avg_r", -9) > 0)
    freq = m["n"] / (span_bars / BARS_PER_YEAR) if span_bars else 0
    eq, mdd, _ = portfolio_run(pool if False else build_stream(strats), risk=0.02, max_concurrent=20)
    x = eq / 100; cagr = (x ** (1/5.4) - 1) * 100 if x > 0 else -100
    calmar = cagr / mdd if mdd > 0 else float("inf")
    wmean = float(np.mean(wsum)) if wsum else 0
    return {
        "label": label, "n": m["n"], "freq": freq, "wr": m.get("wr", 0),
        "avg_r": m.get("avg_r", 0), "sum_r": m.get("sum_r", 0), "pf": m.get("pf", 0),
        "train_r": tr_m.get("avg_r", 0), "test_r": te_m.get("avg_r", 0),
        "pos_coins": pos_coins, "tot_coins": len(pc),
        "mdd": mdd, "cagr": cagr, "calmar": calmar, "whipsaw": wmean, "end_eq": eq,
    }

def show(r):
    print(f"[{r['label']:34s}] N={r['n']:5d} freq={r['freq']:5.0f} WR={r['wr']:5.1f}% "
          f"E={r['avg_r']:+.3f}R PF={r['pf']:.2f}")
    print(f"{'':36s} MDD={r['mdd']:5.1f}% CAGR={r['cagr']:6.1f}% CALMAR={r['calmar']:5.2f} "
          f"whipsaw={r['whipsaw']:.3f} end=${r['end_eq']:,.0f}")
    print(f"{'':36s} OOS train={r['train_r']:+.3f} test={r['test_r']:+.3f}  "
          f"per-coin+ {r['pos_coins']}/{r['tot_coins']}")

def main():
    print("=" * 90)
    print("  KALMAN ADAPTİF TREND (D7) — baseline vs (a)trigger vs (b)filtre")
    print(f"  default: KSPAN={KSPAN} WIN_S={WIN_S} WIN_L={WIN_L}  (sweep YOK, OOS ayrı)")
    print("=" * 90)

    base = eval_block(BASE, "BASELINE donch+ST")
    show(base)

    # (a) standalone trigger — iki SL/TP rejimi de baseline'la aynı kalsın (default)
    trig = eval_block([("kalman_trig", sig_trigger, 2.0, 2.75)], "(a) Kalman TRIGGER standalone")
    show(trig)

    # (b) filtre: baseline'ın HER kolunu Kalman eğimiyle gate'le
    filt = [
        ("donchian_kf",   make_filtered(D.make_sig(40, "atr", 0.25, 0.0)), 2.0, 2.5),
        ("supertrend_kf", make_filtered(S.make_sig(10, 3, 25)),            2.0, 3.0),
    ]
    fres = eval_block(filt, "(b) baseline + Kalman FİLTRE")
    show(fres)

    print("\n" + "=" * 90)
    print("  DELTA (b filtre − baseline):")
    print(f"    MDD     {base['mdd']:6.1f}% → {fres['mdd']:6.1f}%   ({fres['mdd']-base['mdd']:+.1f})")
    print(f"    CALMAR  {base['calmar']:6.2f}  → {fres['calmar']:6.2f}    ({fres['calmar']-base['calmar']:+.2f})")
    print(f"    CAGR    {base['cagr']:6.1f}% → {fres['cagr']:6.1f}%   ({fres['cagr']-base['cagr']:+.1f})")
    print(f"    whipsaw {base['whipsaw']:6.3f}  → {fres['whipsaw']:6.3f}   ({fres['whipsaw']-base['whipsaw']:+.3f})")
    print(f"    N       {base['n']:6d}  → {fres['n']:6d}     ({fres['n']-base['n']:+d})")
    print(f"    E(R)    {base['avg_r']:+.3f}  → {fres['avg_r']:+.3f}")
    print("=" * 90)
    return base, trig, fres

if __name__ == "__main__":
    main()
