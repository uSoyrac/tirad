"""
multiseed_and_plots.py
======================
1) Çoklu-seed sağlamlık testi: sonuç tek bir rastgele tohuma mı bağlı?
2) Görseller: equity eğrisi (buggy vs honest) + win-rate karşılaştırması.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from data_gen import regime
from backtest_compare import run

SEEDS = [1, 7, 13, 21, 42, 99]
MODES = ["buggy_repo", "honest_limit", "honest_market"]

agg = {m: {"wr": [], "mult": [], "avgR": [], "dd": []} for m in MODES}
rep_curves = {}

print("ÇOKLU-SEED SAĞLAMLIK (realistic rejim)")
print(f"{'seed':>5s} {'mod':14s} {'işlem':>6s} {'WR':>6s} {'ortR':>6s} {'çarpan':>14s} {'maxDD':>7s}")
print("─" * 70)
for s in SEEDS:
    df = regime("realistic", seed=s)
    for m in MODES:
        r = run(df, m)
        agg[m]["wr"].append(r["win_rate"]); agg[m]["mult"].append(r["mult"])
        agg[m]["avgR"].append(r["avg_R"]); agg[m]["dd"].append(r["max_dd"])
        if s == 42:
            rep_curves[m] = r["eq_curve"]
        wr = f"{r['win_rate']*100:.0f}%"
        print(f"{s:5d} {m:14s} {r['trades']:6d} {wr:>6s} {r['avg_R']:+6.2f} "
              f"{r['mult']:>13.2e}x {r['max_dd']:>6.1f}%")
    print()

print("═" * 70)
print("ORTALAMALAR (6 seed):")
print(f"{'mod':14s} {'ort.WR':>8s} {'ort.R':>8s} {'medyan çarpan':>16s} {'ort.maxDD':>10s}")
for m in MODES:
    wr = np.nanmean(agg[m]["wr"]) * 100
    ar = np.nanmean(agg[m]["avgR"])
    mm = np.nanmedian(agg[m]["mult"])
    dd = np.nanmean(agg[m]["dd"])
    print(f"{m:14s} {wr:7.0f}% {ar:+8.2f} {mm:>15.3e}x {dd:9.1f}%")

# ── GÖRSEL 1: equity eğrisi (log) ───────────────────────────────
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))
colors = {"buggy_repo": "#d62728", "honest_limit": "#2ca02c", "honest_market": "#1f77b4"}
labels = {"buggy_repo": "Rapor metodolojisi (look-ahead)",
          "honest_limit": "Gerçekçi (limit fill + komisyon)",
          "honest_market": "Gerçekçi (market fill + komisyon)"}
for m in MODES:
    c = rep_curves[m]
    ax1.plot(np.arange(len(c)), c, color=colors[m], label=labels[m], lw=1.6)
ax1.set_yscale("log")
ax1.axhline(1000, color="gray", ls="--", lw=0.8)
ax1.set_title("Equity Eğrisi — log ölçek ($1000 başlangıç)\n(realistic rejim, seed=42)")
ax1.set_xlabel("İşlem #"); ax1.set_ylabel("Equity ($, log)")
ax1.legend(fontsize=8, loc="upper left"); ax1.grid(alpha=0.3)

# ── GÖRSEL 2: WR + çarpan bar ───────────────────────────────────
x = np.arange(len(MODES))
wr_means = [np.nanmean(agg[m]["wr"]) * 100 for m in MODES]
bars = ax2.bar(x, wr_means, color=[colors[m] for m in MODES], alpha=0.85)
ax2.axhline(50, color="black", ls=":", lw=1, label="%50 (yazı-tura)")
ax2.set_xticks(x); ax2.set_xticklabels(["Rapor\n(buggy)", "Gerçekçi\nlimit", "Gerçekçi\nmarket"])
ax2.set_ylabel("Ortalama Kazanma Oranı (%)")
ax2.set_title("Kazanma Oranı: Metodoloji Düzeltilince Çöküyor\n(6 seed ortalaması)")
ax2.set_ylim(0, 100)
for b, v in zip(bars, wr_means):
    ax2.text(b.get_x() + b.get_width() / 2, v + 1.5, f"%{v:.0f}", ha="center", fontweight="bold")
ax2.legend(); ax2.grid(alpha=0.3, axis="y")

plt.tight_layout()
plt.savefig("fig_karsilastirma.png", dpi=130)
print("\n[OK] fig_karsilastirma.png kaydedildi")
