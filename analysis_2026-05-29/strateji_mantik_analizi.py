"""
strateji_mantik_analizi.py
==========================
Kullanıcının mantık zincirini sayısal olarak test eder:

  İddia 1: %2/işlem bileşik, 365 işlemde $100 -> $137K.
  İddia 2: Kayıplar olunca, kazançtan sonra kaldıraç/Fibonacci büyüterek
           kârda kalınabilir.
  İddia 3: Win-rate'i %80'de tutmak için çok indikatör kullanmak gerek.
  İddia 4: İnput azaltıp işlem sıklığını artırınca hedefe daha hızlı varılır.

Test edilen matematiksel gerçekler:
  A) Pozisyon boyutlandırma (Fixed / Paroli / Fibonacci) EDGE YARATMAZ;
     sadece dağılımı (varyans, iflas riski) değiştirir.
  B) Edge yoksa hiçbir boyutlandırma kurtarmaz; eskalasyon daha hızlı batırır.
  C) Win-rate tek başına anlamsız: expectancy = p*W - (1-p)*L.
     Yüksek win-rate + küçük R = kaybeden; düşük win-rate + büyük R = kazanan.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

rng = np.random.default_rng(42)
N_PATHS = 20000
N_TRADES = 300
START = 100.0
BASE_RISK = 0.02
RUIN_LEVEL = 0.10 * START   # -%90 = pratik iflas

line = "═" * 70


# ──────────────────────────────────────────────────────────────
def simulate(p, W, L, scheme, n_paths=N_PATHS, n_trades=N_TRADES):
    """Vektörize Monte Carlo. scheme: 'fixed' | 'paroli' | 'fib_on_win'."""
    eq = np.full(n_paths, START)
    peak = eq.copy()
    maxdd = np.zeros(n_paths)
    cw = np.zeros(n_paths, dtype=int)        # ardışık kazanç sayacı
    ruined = np.zeros(n_paths, dtype=bool)
    fib = np.array([1, 1, 2, 3, 5, 8, 13])

    for _ in range(n_trades):
        win = rng.random(n_paths) < p
        outcome = np.where(win, W, -L)        # R cinsinden sonuç

        if scheme == "fixed":
            risk = np.full(n_paths, BASE_RISK)
        elif scheme == "paroli":
            risk = np.minimum(BASE_RISK * (2 ** cw), 0.15)
        elif scheme == "fib_on_win":
            risk = np.minimum(BASE_RISK * fib[np.minimum(cw, len(fib) - 1)], 0.15)
        else:
            raise ValueError(scheme)

        alive = ~ruined
        pnl = eq * risk * outcome
        eq = np.where(alive, eq + pnl, eq)
        eq = np.maximum(eq, 0.0)

        # streak güncelle
        cw = np.where(win, cw + 1, 0)
        if scheme in ("paroli",):
            cw = np.where(cw >= 3, 0, cw)     # rapor: 3 kazançta resetle

        peak = np.maximum(peak, eq)
        dd = (peak - eq) / peak
        maxdd = np.maximum(maxdd, dd)
        ruined |= (eq <= RUIN_LEVEL)

    return {"final": eq, "maxdd": maxdd, "ruin_rate": ruined.mean()}


def expectancy(p, W, L):
    return p * W - (1 - p) * L


# ──────────────────────────────────────────────────────────────
def part1_compound_reality():
    print(line); print("1) '%2/işlem, 365 işlemde $137K' GERÇEKÇİ Mİ?"); print(line)
    print(f"  Aritmetik doğru: $100 × 1.02^365 = ${100*1.02**365:,.0f}")
    print()
    print("  AMA bu, HER işlemin net +%2 (ana para üzerinde) getirmesi demek.")
    print("  +%2/işlem net = +1R expectancy (risk %2 ise). Yani PRATİKTE")
    print("  hiç kaybetmemek gerekir. Gerekli win-rate (L=1R, çeşitli W):")
    for W in [1.0, 2.0, 3.0]:
        # p*W - (1-p)*1 = 1.0  ->  p = 2/(W+1)
        p_req = 2.0 / (W + 1)
        tag = "  imkansız (>%100)" if p_req > 1 else ""
        print(f"    W={W:.0f}R ödül için gereken win-rate = %{min(p_req,1)*100:.0f}{tag}")
    print("  -> +%2/işlem hedefi, ancak look-ahead'li backtest'te 'görünür'.")
    print()
    print("  365 işlemde beklenen EN UZUN KAYIP SERİSİ (win-rate'e göre):")
    for p in [0.55, 0.70, 0.80, 0.90]:
        streak = np.log(N_TRADES) / np.log(1 / (1 - p))
        print(f"    win-rate %{p*100:.0f}: ~{streak:.1f} ardışık kayıp BEKLENİR")
    print("  -> '%80 win-rate'te bile bir yerde ~4 ardışık kayıp normaldir.")
    print()


def part2_sizing_no_edge_change():
    print(line); print("2) BOYUTLANDIRMA EDGE YARATIR MI? (Fixed vs Paroli vs Fibonacci)")
    print(line)

    scenarios = [
        ("POZİTİF edge (p=55%, W=1, L=1, E=+0.10R)", 0.55, 1.0, 1.0),
        ("SIFIR/NEG edge + komisyon (p=50%, W=0.95, L=1, E=-0.03R)", 0.50, 0.95, 1.0),
        ("KULLANICININ HAYALİ: yüksek WR/küçük R (p=80%, W=0.25, L=1, E=0)", 0.80, 0.25, 1.0),
    ]
    for title, p, W, L in scenarios:
        E = expectancy(p, W, L)
        print(f"\n  ▶ {title}")
        print(f"    {'şema':12s} {'medyan $':>12s} {'ort $':>12s} {'iflas%':>8s} {'ort.maxDD':>10s}")
        for scheme in ["fixed", "paroli", "fib_on_win"]:
            r = simulate(p, W, L, scheme)
            print(f"    {scheme:12s} {np.median(r['final']):>12,.0f} "
                  f"{r['final'].mean():>12,.0f} {r['ruin_rate']*100:>7.1f}% "
                  f"{r['maxdd'].mean()*100:>9.1f}%")
    print()
    print("  YORUM:")
    print("  • Boyutlandırma işlem başı EXPECTANCY'yi DEĞİŞTİRMEZ; sadece riski")
    print("    artırıp/azaltıp dağılımı (varyans, drawdown, iflas) değiştirir.")
    print("  • Pozitif edge'te: Paroli/Fib daha yüksek getiri verebilir AMA bu")
    print("    BEDAVA değil — drawdown ~%22'den ~%43'e fırlıyor (daha çok risk).")
    print("    Aynı sonucu Fixed risk'i artırarak da alırsınız; 'sihir' yok.")
    print("  • Edge SIFIR/NEGATİFse (sizin gerçek durumunuz): HİÇBİR şema kurtarmaz;")
    print("    eskalasyon medyanı DÜŞÜRÜR ve iflas riski yaratır.")
    print("  • KULLANICININ HAYALİ satırına dikkat: %80 win-rate olsa BİLE, küçük R")
    print("    (E=0) + Fibonacci eskalasyon -> medyan $100'den $68'e DÜŞÜYOR,")
    print("    drawdown %65, hatta iflas. 'Kazançta büyüt' biriken kârı tam")
    print("    tepede gelen tek kayba teslim eder.")
    print()


def part3_winrate_is_a_knob():
    print(line); print("3) WIN-RATE BİR HEDEF DEĞİL, BİR AYAR DÜĞMESİDİR"); print(line)
    print("  expectancy = p·W − (1−p)·L   (L=1R sabit)")
    print(f"  {'win-rate':>9s} {'W=0.25R':>9s} {'W=0.5R':>9s} {'W=1R':>9s} {'W=2R':>9s} {'W=3R':>9s}")
    for p in [0.40, 0.50, 0.60, 0.70, 0.80, 0.90]:
        row = f"  %{p*100:>7.0f}"
        for W in [0.25, 0.5, 1.0, 2.0, 3.0]:
            e = expectancy(p, W, 1.0)
            row += f" {e:>+9.2f}"
        print(row)
    print()
    print("  • %80 win-rate + W=0.25R  -> E=0.00 (komisyonla NEGATİF). KAYBEDEN.")
    print("  • %45 win-rate + W=2R     -> E=+0.35R. KAZANAN.")
    print("  -> Win-rate'i istediğiniz kadar yükseltebilirsiniz (TP'yi yakına,")
    print("     SL'i uzağa koyarak) ama bu BECERİ değil; expectancy'yi değiştirmez.")
    print("  -> Çok indikatör 'gerçek' win-rate'i artırmaz; overfitting + look-ahead")
    print("     yüzeyini artırır. Doğru hedef: OUT-OF-SAMPLE expectancy & Sharpe.")
    print()


def make_figure():
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    # Panel A: pozitif edge, 3 şema dağılımı
    p, W, L = 0.55, 1.0, 1.0
    res = {s: simulate(p, W, L, s) for s in ["fixed", "paroli", "fib_on_win"]}
    bins = np.logspace(0, 5, 60)
    cols = {"fixed": "#2ca02c", "paroli": "#d62728", "fib_on_win": "#ff7f0e"}
    names = {"fixed": "Fixed %2", "paroli": "Paroli (kazançta x2)", "fib_on_win": "Fibonacci (kazançta)"}
    for s in res:
        axes[0].hist(np.clip(res[s]["final"], 1, 1e5), bins=bins, alpha=0.5,
                     color=cols[s], label=f"{names[s]}  (medyan ${np.median(res[s]['final']):,.0f}, iflas %{res[s]['ruin_rate']*100:.0f})")
    axes[0].set_xscale("log"); axes[0].axvline(START, color="k", ls="--", lw=0.8)
    axes[0].set_title("A) AYNI POZİTİF EDGE, 3 boyutlandırma\n($100 başlangıç, 300 işlem)")
    axes[0].set_xlabel("Bitiş sermayesi ($, log)"); axes[0].set_ylabel("Yol sayısı")
    axes[0].legend(fontsize=7.5)

    # Panel B: sıfır/neg edge
    p2, W2 = 0.50, 0.95
    res2 = {s: simulate(p2, W2, 1.0, s) for s in ["fixed", "paroli", "fib_on_win"]}
    for s in res2:
        axes[1].hist(np.clip(res2[s]["final"], 1, 1e5), bins=bins, alpha=0.5,
                     color=cols[s], label=f"{names[s]}  (medyan ${np.median(res2[s]['final']):,.0f})")
    axes[1].set_xscale("log"); axes[1].axvline(START, color="k", ls="--", lw=0.8)
    axes[1].set_title("B) EDGE YOK (komisyonlu)\nHiçbir şema kurtarmaz")
    axes[1].set_xlabel("Bitiş sermayesi ($, log)"); axes[1].legend(fontsize=7.5)

    # Panel C: expectancy vs win-rate
    pp = np.linspace(0.30, 0.95, 100)
    for W in [0.25, 0.5, 1.0, 2.0, 3.0]:
        axes[2].plot(pp * 100, pp * W - (1 - pp) * 1.0, label=f"W={W}R")
    axes[2].axhline(0, color="k", lw=1)
    axes[2].scatter([80], [expectancy(0.80, 0.25, 1)], color="red", zorder=5, s=60)
    axes[2].annotate("hayal:\n%80/0.25R\n(=0, kaybeden)", (80, 0), textcoords="offset points",
                     xytext=(-70, 35), fontsize=8, color="red",
                     arrowprops=dict(arrowstyle="->", color="red"))
    axes[2].scatter([45], [expectancy(0.45, 2.0, 1)], color="green", zorder=5, s=60)
    axes[2].annotate("%45/2R\n(kazanan)", (45, expectancy(0.45, 2, 1)),
                     textcoords="offset points", xytext=(10, -5), fontsize=8, color="green")
    axes[2].set_title("C) Expectancy = p·W − (1−p)·L\nWin-rate tek başına anlamsız")
    axes[2].set_xlabel("Win-rate (%)"); axes[2].set_ylabel("İşlem başı beklenen (R)")
    axes[2].legend(fontsize=8); axes[2].grid(alpha=0.3)

    plt.tight_layout(); plt.savefig("fig_mantik_analizi.png", dpi=130)
    print("[OK] fig_mantik_analizi.png kaydedildi")


if __name__ == "__main__":
    print("\n" + "█" * 70)
    print("  STRATEJİ MANTIĞININ SAYISAL DENETİMİ")
    print("█" * 70 + "\n")
    part1_compound_reality()
    part2_sizing_no_edge_change()
    part3_winrate_is_a_knob()
    make_figure()
