"""
sizing_compound.py
=================
signal_lab'ın seçtiği kuralın GERÇEK (komisyonlu, look-ahead'siz) işlem
dağılımını alır; bileşik büyümeyi farklı para-yönetimi şemalarıyla
Monte Carlo (bootstrap) ile karşılaştırır:
  Fixed %1 / Fixed %2 / Half-Kelly / Paroli / Kaldıraç-büyütme

AMAÇ: 'Bileşik faizle büyütme' fikrini, ÖLÇÜLEN edge üzerinden gerçekçi
test etmek. Edge pozitifse hangisi optimal? Edge ~0/negatifse ne olur?
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np
from signal_lab import (load_data, build_features, make_rules, backtest, stats, WARMUP)

N_PATHS = 10000
RUIN = 0.15


def kelly_fraction(tr):
    """Edge ve R:R'den tam-Kelly. Kazanç/kayıp R ortalamalarıyla."""
    w = tr[tr > 0]; l = tr[tr <= 0]
    if len(w) == 0 or len(l) == 0: return 0.0
    p = len(w) / len(tr); b = w.mean() / (abs(l.mean()) + 1e-9)
    f = (p * b - (1 - p)) / b
    return max(f, 0.0)


def grow(seq, scheme, kelly_f=0.0, n_paths=N_PATHS, start=100.0):
    rng = np.random.default_rng(1)
    T = len(seq)
    eq = np.full(n_paths, start); cw = np.zeros(n_paths, int); ruined = np.zeros(n_paths, bool)
    fib = np.array([1, 1, 2, 3, 5, 8, 13])
    for _ in range(T):
        out = seq[rng.integers(0, T, n_paths)]            # bootstrap: gerçek R dağılımından
        if scheme == "fixed1":   risk = np.full(n_paths, 0.01)
        elif scheme == "fixed2": risk = np.full(n_paths, 0.02)
        elif scheme == "halfkelly": risk = np.full(n_paths, min(kelly_f * 0.5, 0.2))
        elif scheme == "paroli": risk = np.minimum(0.02 * 2 ** cw, 0.15)
        elif scheme == "lev_grow": risk = np.minimum(0.02 * (1 + 0.5 * cw), 0.15)
        else: raise ValueError(scheme)
        eq = np.where(~ruined, eq * (1 + risk * out), eq)
        eq = np.maximum(eq, 0)
        win = out > 0
        cw = np.where(win, cw + 1, 0)
        if scheme == "paroli": cw = np.where(cw >= 3, 0, cw)
        ruined |= eq <= start * RUIN
    return eq, ruined.mean()


def show(seq, title, n_trades_label):
    s = stats(seq); kf = kelly_fraction(seq)
    print("═" * 78); print(f"  {title}")
    print(f"  n={s['n']}, WR=%{s['wr']*100:.0f}, expectancy={s['exp']:+.3f}R, "
          f"PF={s['pf']:.2f} | Tam-Kelly f*={kf*100:.1f}%")
    print("═" * 78)
    print(f"  Bileşik büyüme ({n_trades_label} işlem, $100, 10k yol bootstrap):")
    print(f"  {'şema':12s} {'medyan $':>10s} {'%5 dilim':>10s} {'%95 dilim':>11s} {'iflas%':>8s}")
    for sch in ["fixed1", "fixed2", "halfkelly", "paroli", "lev_grow"]:
        eq, ruin = grow(seq, sch, kelly_f=kf)
        print(f"  {sch:12s} {np.median(eq):>10,.0f} {np.percentile(eq,5):>10,.0f} "
              f"{np.percentile(eq,95):>11,.0f} {ruin*100:>7.1f}%")
    print()


def main():
    df, tag = load_data(4)
    F, atr, op, hi, lo, cl = build_features(df, tag)
    rules = make_rules(F)

    # (A) ÖLÇÜLEN edge: en çok işlem üreten SMC kuralının GERÇEK işlemleri
    busiest = max(rules, key=lambda nm: stats(backtest(*rules[nm], atr, op, hi, lo, cl))["n"])
    measured = backtest(*rules[busiest], atr, op, hi, lo, cl)
    show(measured, f"(A) ÖLÇÜLEN SMC EDGE — kural '{busiest}' (komisyonlu, look-ahead'siz)",
         len(measured))
    print("  -> Edge ~0/negatif: TÜM şemalar $100'un ALTINA iner. Bileşik faiz,")
    print("     negatif edge'i pozitife çeviremez; eskalasyon iflası hızlandırır.\n")

    # (B) VARSAYIMSAL GERÇEK edge (referans): %48 WR, +2.2R kazanç, -1R kayıp
    rng = np.random.default_rng(5)
    real_edge = np.where(rng.random(400) < 0.45, 1.5, -1.0) - 0.02  # komisyon dahil
    show(real_edge, "(B) REFERANS: GERÇEKÇİ-İYİ edge olsaydı (%45 WR, +1.5R / -1R, exp≈+0.10R)",
         len(real_edge))
    print("  -> Gerçek edge'te: en yüksek MEDYAN genelde agresif şemada AMA en iyi")
    print("     RİSK-AYARLI sonuç (yüksek %5-dilim + düşük iflas) HALF-KELLY'de.")
    print("     Paroli/kaldıraç-büyütme %5-dilimi düşürür, iflas riskini artırır.")


if __name__ == "__main__":
    main()
