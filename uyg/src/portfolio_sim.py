#!/usr/bin/env python3
"""
portfolio_sim.py — GERÇEKÇİ PORTFÖY COMPOUND (eşzamanlı-risk tavanlı)
═══════════════════════════════════════════════════════════════════════
Naif ardışık sabit-kesir, overlapping pozisyonları yanlış modelliyordu (MDD %100).
Bu motor zaman-sıralı çalışır: her giriş anında, açık pozisyon sayısı tavanın
altındaysa equity'nin R%'iyle pozisyon aç; çıkışta R-sonucu uygula. Eşzamanlı
toplam risk tavanı (korelasyon koruması) ile GERÇEK drawdown'ı ölçer.

Kelly/fractional sizing + leverage süpürmesi + harvest-cycle P($100→$10k).
"""
import json, numpy as np
import warnings; warnings.filterwarnings("ignore")
from signal_lab import load_all, simulate, metrics, BARS_PER_YEAR
import sig_donchian_breakout as D, sig_supertrend_regime as S, sig_vol_regime_mom as V

# temiz edge'ler (volregime'i ajanın seçici best'iyle: expansion düşük-frekans)
STRATS = [
    ("donchian",   D.make_sig(40, "atr", 0.25, 0.0), 2.0, 2.5),
    ("supertrend", S.make_sig(10, 3, 25),            2.0, 3.0),
]

def build_stream():
    dfs = load_all("mktdata", "4h")
    tr = []
    for name, sig, sl, tp in STRATS:
        for c, df in dfs.items():
            for t in simulate(df, sig(df), sl_atr=sl, tp_r=tp):
                t["coin"] = c; t["strat"] = name; tr.append(t)
    tr.sort(key=lambda x: x["entry_ts"])
    return tr

def portfolio_run(trades, risk=0.01, max_concurrent=8, start=100.0):
    """Zaman-sıralı; giriş anında slot varsa equity*risk kadar riskle aç, çıkışta uygula.
    Basit model: equity sadece çıkışta güncellenir; eşzamanlı açık risk tavanla sınırlı."""
    events = []
    for k, t in enumerate(trades):
        events.append((t["entry_ts"], "open", k))
        events.append((t["exit_ts"], "close", k))
    events.sort(key=lambda e: (e[0], 0 if e[1] == "close" else 1))  # önce kapanışlar
    eq = start; peak = start; mdd = 0.0; open_risk = {}; curve = [start]
    for ts, typ, k in events:
        if typ == "open":
            if len(open_risk) >= max_concurrent:
                continue
            open_risk[k] = eq * risk          # giriş anındaki equity'den risk
        else:
            if k in open_risk:
                eq += open_risk.pop(k) * trades[k]["r_mult"]
                if eq <= 1: eq = 0.0
                peak = max(peak, eq)
                if peak > 0: mdd = max(mdd, (peak - eq)/peak)
                curve.append(eq)
        if eq <= 0: break
    return eq, mdd*100, curve

def harvest_cycle(trades, risk, max_concurrent, target=10000, reset=300, ruin=0.10, n_paths=3000, seed=42):
    """Bootstrap blok: gerçek trade dizisini rastgele başlangıçtan oynat, $10k'ya ulaş/iflas."""
    rng = np.random.default_rng(seed)
    R = np.array([t["r_mult"] for t in trades])
    # ardışıklık/korelasyonu korumak için blok-bootstrap (50'lik bloklar)
    succ = ruined = 0; times = []
    for _ in range(n_paths):
        eq = 100.0; floor = 100.0*ruin; steps = 0
        while steps < 4000:
            blk = rng.integers(0, len(R)-50)
            for r in R[blk:blk+50]:
                eq += eq * risk * r; steps += 1
                if eq >= target:
                    succ += 1; times.append(steps); eq = reset; floor = reset*ruin
                elif eq <= floor:
                    ruined += 1; eq = reset; floor = reset*ruin
                if steps >= 4000: break
        # path sonu
    cyc = succ + ruined
    return (succ/cyc*100 if cyc else 0), (np.median(times) if times else float("inf"))

def main():
    tr = build_stream()
    m = metrics(tr); span = 11860
    fq = m["n"]/(span/BARS_PER_YEAR)
    print("="*84); print("  GERÇEKÇİ PORTFÖY COMPOUND — donchian+supertrend (temiz edge'ler)"); print("="*84)
    print(f"  Akış: N={m['n']}  freq~{fq:.0f}/yıl  WR={m['wr']:.1f}%  E={m['avg_r']:+.3f}R  PF={m['pf']:.2f}")
    print(f"\n  Eşzamanlı-risk tavanlı portföy (5.4y gerçek sıra):")
    print(f"  {'risk%':>6}{'maxPoz':>7}{'bitiş$':>14}{'x':>8}{'MDD%':>8}{'CAGR%':>8}")
    for risk in [0.005, 0.01, 0.02, 0.03]:
        for mc in [5, 10, 20]:
            eq, mdd, _ = portfolio_run(tr, risk=risk, max_concurrent=mc)
            x = eq/100; cagr = (x**(1/5.4)-1)*100 if x > 0 else -100
            print(f"  {risk*100:>6.1f}{mc:>7}{eq:>14,.0f}{x:>8.1f}{mdd:>8.1f}{cagr:>8.1f}")
    # harvest cycle (en dengeli sizing'lerde)
    print(f"\n  Hasat-döngüsü P($100→$10k) (blok-bootstrap, korelasyon korunur):")
    print(f"  {'risk%':>6}{'P(başarı)%':>12}{'medyan adım':>13}")
    for risk in [0.01, 0.02, 0.03, 0.05]:
        ps, mt = harvest_cycle(tr, risk, 10)
        tl = f"{mt:.0f}işlem" if mt != float("inf") else "ulaşmıyor"
        print(f"  {risk*100:>6.1f}{ps:>12.1f}{tl:>13}")
    json.dump([{"r_mult": t["r_mult"], "entry_ts": t["entry_ts"], "exit_ts": t["exit_ts"],
                "coin": t["coin"], "strat": t["strat"]} for t in tr],
              open("/tmp/portfolio_trades.json", "w"))
    print(f"\n  ✅ /tmp/portfolio_trades.json")

if __name__ == "__main__":
    main()
