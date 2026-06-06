"""FIRMA × YAPI prop geçiş Monte-Carlo — Türkiye-uygun firmalar, DOĞRU edge ile.

LEVER: combo edge'inde max prop geçiş-oranı için FİRMA/YAPI optimize et. Breakout
Türkiye-yasaklı → HARİÇ. Her firmayı KENDİ uygulanabilir edge'inde test eder:
  - HyroTrader (crypto perp): combo = crypto_trend + crypto_funding (inverse-vol)
  - Trade The Pool (hisse, statik DD): us_momentum sleeve

Block-bootstrap (gerçek günlük getiriler, 5-gün blok) ile binlerce bağımsız yol;
0.6 haircut (proje konvansiyonu); trailing DD (HyroTrader, EOD) vs statik DD (TTP).
Günlük-kayıp uçurumu EOD modellenir + intraday caveat. IS-bootstrap vs OOS-bootstrap
yan-yana (sadece müşfik 2025-26 rejimini sürmemek için).

Usage: python scripts/run_firm_montecarlo.py
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SLEEVE3 = ROOT / "reports_out" / "_sleeves3.parquet"
CUT = pd.Timestamp("2025-01-01")
HAIRCUT = 0.60
BLOCK = 5
NSIM = 30000
MAXD = 252           # bir faz için ileri-pencere (gün); süre limiti yoksa bağlayıcı değil

# --- Firma/yapı kataloğu (Türkiye-uygun; Breakout HARİÇ) ---
# phases: [(hedef, min_gün), ...]; daily: günlük-kayıp uçurumu; total: max toplam DD;
# trail: EOD-trailing DD mi (HyroTrader) yoksa statik mi (TTP); ppy: yıllıklama günü;
# edge: hangi getiri serisi.
FIRMS = {
    # HyroTrader — crypto perp, combo edge gerçekten uygulanır
    "HyroTrader 1-step (trailing 6%)": dict(
        phases=[(0.10, 5)], daily=-0.04, total=-0.06, trail=True, ppy=365, edge="combo"),
    "HyroTrader 2-step (trailing 10%)": dict(
        phases=[(0.10, 5), (0.05, 5)], daily=-0.05, total=-0.10, trail=True, ppy=365, edge="combo"),
    # Trade The Pool — hisse, STATİK DD, tek-faz; us_momentum edge
    "TradeThePool +6% (static 4% / daily 2%)": dict(
        phases=[(0.06, 5)], daily=-0.02, total=-0.04, trail=False, ppy=252, edge="us"),
    "TradeThePool +8% (static 6% / daily 3%)": dict(
        phases=[(0.08, 5)], daily=-0.03, total=-0.06, trail=False, ppy=252, edge="us"),
    "TradeThePool +10% (static 10% / daily 5%)": dict(
        phases=[(0.10, 5)], daily=-0.05, total=-0.10, trail=False, ppy=252, edge="us"),
}
VOLS = [0.06, 0.08, 0.10, 0.12, 0.15]


def edges():
    R = pd.read_parquet(SLEEVE3)
    c = R[["crypto_trend", "crypto_funding"]]
    iv = 1.0 / c[c.index < CUT].std().to_numpy()
    combo = pd.Series(c.to_numpy() @ (iv / iv.sum()), index=c.index)
    return {"combo": combo, "us": R["us_momentum"].dropna()}


def block_paths(z, n, days, rng):
    """z'den n adet block-bootstrap yol (her satır 'days' uzunlukta standardize getiri)."""
    nb = days // BLOCK + 1
    st = rng.integers(0, len(z) - BLOCK, size=(n, nb))
    out = np.empty((n, days))
    for p in range(n):
        out[p] = np.concatenate([z[s:s + BLOCK] for s in st[p]])[:days]
    return out


def run_challenge(zp, sharpe_d, ppy, vol, cfg):
    """zp: (n, days) standardize yollar. Faz-zincirini ileri-simüle; geçen yol oranı.

    Edge sim Sharpe = HAIRCUT * sharpe_d (yıllık). Günlük drift+vol o seviyeye ölçeklenir.
    daily uçurumu EOD getiriyle, trailing/statik DD floor EOD equity'yle kontrol edilir.
    """
    n = zp.shape[0]
    sd = vol / np.sqrt(ppy)
    mu = HAIRCUT * sharpe_d * sd          # günlük drift (haircut'lı)
    passed = np.zeros(n, bool)
    for p in range(n):
        path = mu + sd * zp[p]
        phase = 0
        eq = peak = 1.0
        dphase = 0
        ok = True
        for ret in path:
            dphase += 1
            if ret <= cfg["daily"]:        # günlük-kayıp uçurumu (anında fail)
                ok = False
                break
            eq *= (1 + ret)
            peak = max(peak, eq)
            floor = peak * (1 + cfg["total"]) if cfg["trail"] else (1 + cfg["total"])
            if eq <= floor:
                ok = False
                break
            tgt, mind = cfg["phases"][phase]
            if eq >= 1 + tgt and dphase >= mind:
                phase += 1
                if phase >= len(cfg["phases"]):
                    break               # tüm fazlar geçildi
                eq = peak = 1.0          # sonraki faz sıfırdan
                dphase = 0
        else:
            ok = False                   # pencere doldu, hedefe ulaşamadı
        if ok and phase >= len(cfg["phases"]):
            passed[p] = True
    return passed.mean()


def daily_breach_3pct(zp, sharpe_d, ppy, vol):
    """Bir EOD gününün ≤−3% olma olasılığı (intraday −daily uçurum riski proxy'si)."""
    sd = vol / np.sqrt(ppy)
    mu = HAIRCUT * sharpe_d * sd
    paths = mu + sd * zp
    return float((paths <= -0.03).any(axis=1).mean())


def main():
    E = edges()
    stats = {}
    for k, s in E.items():
        z = ((s - s.mean()) / s.std()).to_numpy()
        oos = s[s.index >= CUT]
        zoos = ((oos - oos.mean()) / oos.std()).to_numpy()
        isr = s[s.index < CUT]
        zis = ((isr - isr.mean()) / isr.std()).to_numpy()
        stats[k] = dict(
            sh_full=float(s.mean() / s.std()),
            sh_oos=float(oos.mean() / oos.std()),
            sh_is=float(isr.mean() / isr.std()),
            z_full=z, z_oos=zoos, z_is=zis)

    rng = np.random.default_rng(11)
    lines = ["# FİRMA × YAPI prop geçiş Monte-Carlo (Türkiye-uygun; Breakout HARİÇ)", "",
             f"Block-bootstrap ({BLOCK}-gün blok), {NSIM} yol, haircut ×{HAIRCUT}. Her firma KENDİ "
             "uygulanabilir edge'inde: HyroTrader=combo(crypto), TradeThePool=us_momentum(hisse).", "",
             "Sim Sharpe (yıllık, haircut'lı) edge başına: " +
             ", ".join(f"{k} full {HAIRCUT*stats[k]['sh_full']*np.sqrt(365 if k=='combo' else 252):.2f}"
                       for k in E), "",
             "## P(geç) — firma/yapı × vol-hedef (FULL-örneklem bootstrap)", "",
             "| Firma/yapı | DD | " + " | ".join(f"vol {int(v*100)}%" for v in VOLS) + " |",
             "|" + "---|" * (len(VOLS) + 2)]

    best = (None, 0.0, None)
    detail = {}
    for name, cfg in FIRMS.items():
        st = stats[cfg["edge"]]
        sh_d = st["sh_full"]
        row = []
        for v in VOLS:
            zp = block_paths(st["z_full"], NSIM, MAXD, rng)
            p = run_challenge(zp, sh_d, cfg["ppy"], v, cfg)
            row.append(p)
            if p > best[1]:
                best = (name, p, v)
        detail[name] = row
        dd = ("trailing %d%%" % int(abs(cfg["total"]) * 100)) if cfg["trail"] else \
             ("static %d%%" % int(abs(cfg["total"]) * 100))
        lines.append(f"| {name} | {dd} | " + " | ".join(f"**{x*100:.0f}%**" for x in row) + " |")

    # OOS-only vs IS-only bootstrap (rejim-dürüstlüğü) — en iyi config + her firmanın tepe vol'ü
    lines += ["", "## Rejim-dürüstlüğü: IS-bootstrap vs OOS-bootstrap (her firmanın en iyi vol'ü)", "",
              "| Firma/yapı | en iyi vol | P(geç) FULL | P(geç) IS-only | P(geç) OOS-only |",
              "|---|---|---|---|---|"]
    for name, cfg in FIRMS.items():
        st = stats[cfg["edge"]]
        row = detail[name]
        bv = VOLS[int(np.argmax(row))]
        pf = row[int(np.argmax(row))]
        zis = block_paths(st["z_is"], NSIM, MAXD, rng)
        zoos = block_paths(st["z_oos"], NSIM, MAXD, rng)
        pis = run_challenge(zis, st["sh_is"], cfg["ppy"], bv, cfg)
        poos = run_challenge(zoos, st["sh_oos"], cfg["ppy"], bv, cfg)
        lines.append(f"| {name} | {int(bv*100)}% | {pf*100:.0f}% | {pis*100:.0f}% | {poos*100:.0f}% |")

    # En iyi config için intraday −%3 uçurum riski
    bname, bp, bv = best
    bcfg = FIRMS[bname]
    bst = stats[bcfg["edge"]]
    zp = block_paths(bst["z_full"], NSIM, MAXD, rng)
    d3 = daily_breach_3pct(zp, bst["sh_full"], bcfg["ppy"], bv)

    lines += ["", "## En iyi config", "",
              f"- **{bname} @ vol {int(bv*100)}% → P(geç) {bp*100:.0f}% (full-bootstrap).**",
              f"- Bu config'te bir EOD günü ≤−%3 olma olasılığı: **{d3*100:.0f}%** "
              f"(intraday'in günlük {int(abs(bcfg['daily'])*100)}% uçurumunu kırma proxy'si; "
              "düşükse güvenli marj).",
              "", "## Yorum (dürüst)", "",
              "- **STATİK DD (Trade The Pool) trailing'i (HyroTrader) geçiş-kolaylığında yener:** "
              "zirveden geri-çekilme cezalandırılmaz, floor sabit → hedefe daha rahat tırmanırsın. "
              "TTP'nin küçük hedefi (+%6/+%8) de combo'nun +%10'undan kolay.",
              "- **AMA edge eşleşmesi şart:** TTP yalnız us_momentum'da geçerli (hisse), HyroTrader "
              "combo'da (crypto perp+funding). İki ayrı bot, iki ayrı edge — birini diğerinin "
              "rakamıyla karıştırma.",
              "- **Vol kaldıracı:** hedef sabitken vol↑ → P(geç)↑ ama günlük-uçurum/DD riski de↑. "
              "TTP'nin SIKI günlük −%2'si düşük vol'ü zorlar; HyroTrader'ın −%4/−%5'i daha toleranslı.",
              "- ⚠️ **Rejim:** OOS-bootstrap (müşfik 2025-26) IS-bootstrap'ten yüksek geçiş verir; "
              "gerçek beklenti IS-seviyesi ya da altı. Yukarıdaki FULL kolonu ikisinin ortası.",
              "- ⚠️ **Survivorship:** her iki evren de bugünün hayatta-kalanları (crypto 27-coin, "
              "US büyük-cap). Büyüklük şişkin; literatür haircut (~%15-22/yıl) MAGNITUDE'a uygulanmalı.",
              "- ⚠️ **Intraday:** EOD veri günlük-kayıp uçurumunu HAFİFE alır. −%3 self-stop bota "
              "kodlanmalı (intraday −daily limite asla değme).",
              "- ⚠️ **%100 geçiş imkânsız:** dürüst tavan yukarıdaki rakam; geri kalanı blowup/yetişememe."]
    report = "\n".join(lines)
    print(report)
    (ROOT / "reports_out" / "firm_montecarlo.md").write_text(report)
    print("\nSaved -> reports_out/firm_montecarlo.md")


if __name__ == "__main__":
    main()
