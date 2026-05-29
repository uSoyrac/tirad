"""Sizing karşılaştırma görseli (sizing_compound sonuçlarından)."""
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

schemes = ["Fixed %1", "Fixed %2", "Half-Kelly", "Paroli", "Kaldıraç↑"]
# (A) ölçülen SMC edge (exp -0.07R)  -- medyan, %5 dilim, iflas%
A_med = [83, 65, 100, 46, 54]; A_p5 = [58, 32, 100, 15, 24]; A_ruin = [0, 0.1, 0, 6.2, 0.7]
# (B) gerçekçi-iyi edge (exp +0.17R)
B_med = [189, 337, 1638, 571, 487]; B_p5 = [124, 144, 152, 118, 137]
x = np.arange(len(schemes)); w = 0.38
fig, ax = plt.subplots(1, 2, figsize=(13, 5))

ax[0].bar(x - w/2, A_med, w, label="medyan $", color="#1f77b4")
ax[0].bar(x + w/2, A_p5, w, label="%5 dilim (kötü senaryo)", color="#aec7e8")
ax[0].axhline(100, color="k", ls="--", lw=0.8, label="başlangıç $100")
for i, r in enumerate(A_ruin):
    if r > 0.5: ax[0].text(i, A_med[i]+5, f"iflas %{r}", ha="center", color="red", fontsize=8)
ax[0].set_title("(A) ÖLÇÜLEN SMC edge (exp −0.07R)\nEdge yok → hepsi $100 altında")
ax[0].set_xticks(x); ax[0].set_xticklabels(schemes, rotation=15); ax[0].legend(fontsize=8)
ax[0].set_ylabel("Bitiş sermayesi ($)")

ax[1].bar(x - w/2, B_med, w, label="medyan $", color="#2ca02c")
ax[1].bar(x + w/2, B_p5, w, label="%5 dilim (kötü senaryo)", color="#98df8a")
ax[1].axhline(100, color="k", ls="--", lw=0.8)
ax[1].set_title("(B) GERÇEKÇİ-İYİ edge (exp +0.17R)\nHalf-Kelly: en yüksek medyan + sağlam taban")
ax[1].set_xticks(x); ax[1].set_xticklabels(schemes, rotation=15); ax[1].legend(fontsize=8)
ax[1].set_ylabel("Bitiş sermayesi ($)")
plt.tight_layout(); plt.savefig("fig_sizing.png", dpi=130)
print("[OK] fig_sizing.png")
