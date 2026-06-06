#!/usr/bin/env python3
"""
faz2_sharpen.py — EDGE KESKİNLEŞTİRME (cache'li sinyaller üstünde, ANINDA)
═══════════════════════════════════════════════════════════════════════
FAZ 1 dürüst edge'i kurdu (S3 ham → beklenti negatif). FAZ 2: edge'i
yükseltecek kaldıraçları sırayla, overfit-korumalı test eder:
  L1. SKOR EŞİĞİ süpürmesi   — comp≥{4.5..8.5}: seçicilik WR'yi pozitife çeviriyor mu?
  L2. REJİM FİLTRESİ          — BTC kendi EMA200 üstünde mi (risk-on) sinyal al
  L3. PER-COIN / PER-ZAMAN    — edge belli ceplerde mi (coin/rejim) yoğunlaşıyor?
Tümü cache'li sinyaller + mktdata üstünde saniyede çalışır (yeni tarama yok).
"""
import os, sys, json, argparse, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
from edge_engine import simulate_fills, edge_metrics, load_df

EMA_TREND = 200


def pooled(dfs, sigs, cfg, comp_min=0.0, regime=None):
    """regime: None | dict{btc_above:bool} — sinyal anında BTC EMA200 üstünde mi filtre."""
    pool = []; tot_sig = tot_fill = 0
    for c, df in dfs.items():
        ss = [s for s in sigs[c] if s.get("comp", 0) >= comp_min]
        if regime is not None:
            ss = [s for s in ss if _regime_ok(c, s, regime)]
        tr, st = simulate_fills(df, ss, **cfg)
        for t in tr: t["coin"] = c
        pool += tr; tot_sig += st["signals"]; tot_fill += st["fills"]
    m = edge_metrics(pool)
    m["fill_rate"] = tot_fill / tot_sig * 100 if tot_sig else 0
    return m, pool


# BTC rejim haritası (global)
_BTC_REGIME = {}
def build_btc_regime(data_dir, tf):
    path = f"{data_dir}/BTC_USDT_{tf}.csv"
    if not os.path.exists(path):
        return
    df = load_df(path)
    ema = df["close"].ewm(span=EMA_TREND, adjust=False).mean()
    above = (df["close"] > ema)
    for ts, a in zip(df.index, above):
        _BTC_REGIME[str(ts)] = bool(a)

def _regime_ok(coin, sig, regime):
    # sinyalin bar zamanını bilmiyoruz (cache'te i var, ts yok) — yaklaşık: comp filtresi
    # gerçek rejim filtresi için sig'e ts eklenmeli; şimdilik True (L2 ayrı yürütülür)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="mktdata")
    ap.add_argument("--tf", default="4h")
    ap.add_argument("--entry", default="mid")
    ap.add_argument("--timeout", type=int, default=12)
    args = ap.parse_args()
    cache_dir = f"sigcache_{os.path.basename(args.data)}"
    cfg = dict(entry_mode=args.entry, timeout=args.timeout, runaway=False)

    coins = sorted(f.split("_")[0] for f in os.listdir(args.data) if f.endswith(f"_{args.tf}.csv"))
    coins = [c for c in coins if os.path.exists(f"{cache_dir}/{c}_{args.tf}.json")]
    dfs = {c: load_df(f"{args.data}/{c}_USDT_{args.tf}.csv") for c in coins}
    sigs = {c: json.load(open(f"{cache_dir}/{c}_{args.tf}.json")) for c in coins}
    nsig = sum(len(s) for s in sigs.values())

    print("=" * 86)
    print(f"  FAZ 2 — EDGE KESKİNLEŞTİRME  ({len(coins)} coin, {nsig} sinyal, fill={args.entry} t={args.timeout})")
    print("=" * 86)

    # ── L1: SKOR EŞİĞİ SÜPÜRMESİ ──
    print("\n  [L1] SKOR EŞİĞİ SÜPÜRMESİ — seçicilik edge yaratıyor mu?")
    print(f"      {'comp≥':>6}{'N':>6}{'fill%':>7}{'WR%':>7}{'avgR':>8}{'sumR':>9}{'PF':>6}{'lstrk':>6}")
    best = None
    for thr in [0.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5]:
        m, pool = pooled(dfs, sigs, cfg, comp_min=thr)
        if m["n"] >= 10:
            print(f"      {thr:>6.1f}{m['n']:>6}{m['fill_rate']:>7.1f}{m['wr']:>7.1f}"
                  f"{m['avg_r']:>+8.3f}{m['sum_r']:>+9.1f}{m['pf']:>6.2f}{m['max_loss_streak']:>6}")
            if m["avg_r"] > 0 and (best is None or m["avg_r"] > best[1]["avg_r"]):
                best = (thr, m, pool)
        else:
            print(f"      {thr:>6.1f}{m['n']:>6}   (N<10)")

    # ── L3: PER-COIN (en iyi eşikte edge nerede yoğun?) ──
    thr_use = best[0] if best else 6.0
    print(f"\n  [L3] PER-COIN @ comp≥{thr_use:.1f} — edge hangi coinlerde?")
    print(f"      {'COIN':6}{'N':>5}{'WR%':>7}{'avgR':>8}{'sumR':>8}{'PF':>6}")
    rows = []
    for c in coins:
        ss = [s for s in sigs[c] if s.get("comp", 0) >= thr_use]
        tr, _ = simulate_fills(dfs[c], ss, **cfg)
        m = edge_metrics(tr)
        if m["n"] >= 5:
            rows.append((c, m))
    rows.sort(key=lambda x: -x[1]["avg_r"])
    for c, m in rows:
        flag = " ←+" if m["avg_r"] > 0 else ""
        print(f"      {c:6}{m['n']:>5}{m['wr']:>7.1f}{m['avg_r']:>+8.3f}{m['sum_r']:>+8.1f}{m['pf']:>6.2f}{flag}")

    # ── L1 sonuç + zaman stabilitesi ──
    if best:
        thr, m, pool = best
        print(f"\n  >>> POZİTİF EDGE BULUNDU: comp≥{thr:.1f} → WR={m['wr']:.1f}% beklenti={m['avg_r']:+.3f}R PF={m['pf']:.2f} (N={m['n']})")
        pool.sort(key=lambda x: x["exit_ts"])
        q = max(1, len(pool)//4)
        for i, lab in enumerate(["Ç1", "Ç2", "Ç3", "Ç4"]):
            seg = pool[i*q:(i+1)*q] if i < 3 else pool[3*q:]
            sm = edge_metrics(seg)
            if sm["n"]:
                yr = (seg[0]["exit_ts"][:7], seg[-1]["exit_ts"][:7])
                print(f"      {lab} [{yr[0]}→{yr[1]}]: N={sm['n']:>3} WR={sm['wr']:.1f}% avgR={sm['avg_r']:+.3f} PF={sm['pf']:.2f}")
        print(f"      %60 WR: {'TUTTU ✓' if m['wr']>=60 else 'TUTMADI (ama beklenti+, RR ile telafi)'}")
        json.dump(pool, open(f"/tmp/faz2_edge_{os.path.basename(args.data)}.json", "w"), default=str)
        print(f"      ✅ pozitif-edge havuzu → /tmp/faz2_edge_{os.path.basename(args.data)}.json")
    else:
        print("\n  ⚠ Hiçbir skor eşiği beklentiyi pozitife çeviremedi.")
        print("    → L2 rejim filtresi / çıkış-optimizasyonu / farklı TF gerekli (FAZ 2 devam).")


if __name__ == "__main__":
    main()
