#!/usr/bin/env python3
"""
run_edge_engine.py — Phase A (paralel tara+cache) + Phase B (fill süpürme).
Kullanım:
  python3 run_edge_engine.py --data data --tf 4h --workers 6
Çıktı: fill-config süpürme tablosu (dolum% vs WR vs beklenti) + en iyi config havuz metrikleri.
"""
import os, sys, json, time, argparse, warnings
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed

warnings.filterwarnings("ignore")
from edge_engine import scan_and_cache, simulate_fills, edge_metrics, load_df


def _scan_job(args):
    coin, path, cache_dir, tf = args
    t0 = time.time()
    sigs = scan_and_cache(coin, path, cache_dir, tf)
    return coin, len(sigs), time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--tf", default="4h")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--coins", default="")
    args = ap.parse_args()
    cache_dir = f"sigcache_{os.path.basename(args.data)}"

    coins = args.coins.split(",") if args.coins else \
        sorted(f.split("_")[0] for f in os.listdir(args.data) if f.endswith(f"_{args.tf}.csv"))
    jobs = [(c, f"{args.data}/{c}_USDT_{args.tf}.csv", cache_dir, args.tf)
            for c in coins if os.path.exists(f"{args.data}/{c}_USDT_{args.tf}.csv")]

    print("=" * 90)
    print(f"  EDGE ENGINE — {args.data}/ TF={args.tf}  ({len(jobs)} coin, {args.workers} işçi)")
    print("=" * 90)

    # ── PHASE A: paralel scan+cache ──
    print("  [A] Sinyal taraması (cache'li)...", flush=True)
    t0 = time.time()
    sig_counts = {}
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for coin, ns, el in [f.result() for f in as_completed([ex.submit(_scan_job, j) for j in jobs])]:
            sig_counts[coin] = ns
    print(f"      {sum(sig_counts.values())} sinyal, {time.time()-t0:.0f}s", flush=True)

    # dataframe'leri yükle (Phase B ucuz)
    dfs = {c: load_df(f"{args.data}/{c}_USDT_{args.tf}.csv") for c, *_ in jobs}
    sigs = {c: json.load(open(f"{cache_dir}/{c}_{args.tf}.json")) for c, *_ in jobs}

    # ── PHASE B: fill-config süpürme ──
    configs = [
        ("scalein  t=3  noRun", dict(entry_mode="scalein", timeout=3,  runaway=False)),
        ("scalein  t=6  noRun", dict(entry_mode="scalein", timeout=6,  runaway=False)),
        ("scalein  t=12 noRun", dict(entry_mode="scalein", timeout=12, runaway=False)),
        ("scalein  t=24 noRun", dict(entry_mode="scalein", timeout=24, runaway=False)),
        ("mid      t=12 noRun", dict(entry_mode="mid",     timeout=12, runaway=False)),
        ("high     t=12 noRun", dict(entry_mode="high",    timeout=12, runaway=False)),
        ("scalein  t=12 RUN3",  dict(entry_mode="scalein", timeout=12, runaway=True, runaway_atr=3.0)),
        ("market   (next open)", dict(entry_mode="market")),
    ]
    print(f"\n  [B] Fill-config süpürme (dolum% vs WR vs beklenti):")
    print(f"      {'config':22}{'fill%':>7}{'N':>6}{'WR%':>7}{'avgR':>8}{'sumR':>9}{'PF':>6}{'lstrk':>6}")
    results = {}
    for label, cfg in configs:
        pool = []; tot_sig = tot_fill = 0
        for c in sigs:
            tr, st = simulate_fills(dfs[c], sigs[c], **cfg)
            for t in tr: t["coin"] = c
            pool += tr; tot_sig += st["signals"]; tot_fill += st["fills"]
        m = edge_metrics(pool)
        fr = tot_fill / tot_sig * 100 if tot_sig else 0
        results[label] = (fr, m, pool)
        if m["n"]:
            print(f"      {label:22}{fr:>7.1f}{m['n']:>6}{m['wr']:>7.1f}{m['avg_r']:>+8.3f}"
                  f"{m['sum_r']:>+9.1f}{m['pf']:>6.2f}{m['max_loss_streak']:>6}")
        else:
            print(f"      {label:22}{fr:>7.1f}{0:>6}   (trade yok)")

    # en iyi: beklenti>0 ve dolum makul (>=%20), sumR'ye göre
    valid = [(lab, fr, m, pool) for lab, (fr, m, pool) in results.items()
             if m.get("n", 0) >= 20 and fr >= 15]
    if valid:
        valid.sort(key=lambda x: -x[2]["sum_r"])
        lab, fr, m, pool = valid[0]
        print(f"\n  >>> EN İYİ DENGELİ CONFIG: {lab}")
        print(f"      dolum %{fr:.1f} | N={m['n']} | WR={m['wr']:.1f}% | beklenti={m['avg_r']:+.3f}R | PF={m['pf']:.2f}")
        print(f"      %60 WR hedefi: {'TUTTU ✓' if m['wr']>=60 else 'TUTMADI ✗ → FAZ 2 keskinleştirme'}")
        pool.sort(key=lambda x: x["exit_ts"])
        h = len(pool)//2
        for labn, seg in [("ilk yarı", pool[:h]), ("son yarı", pool[h:])]:
            sm = edge_metrics(seg)
            yr = (seg[0]["exit_ts"][:7], seg[-1]["exit_ts"][:7]) if seg else ("", "")
            print(f"      {labn} [{yr[0]}→{yr[1]}]: N={sm['n']} WR={sm['wr']:.1f}% avgR={sm['avg_r']:+.3f} PF={sm['pf']:.2f}")
        json.dump(pool, open(f"/tmp/edge_best_{os.path.basename(args.data)}_{args.tf}.json", "w"), default=str)
        print(f"      ✅ en iyi config havuzu → /tmp/edge_best_{os.path.basename(args.data)}_{args.tf}.json")
    else:
        print("\n  ⚠ Hiçbir config 'dolum≥%15 & N≥20' eşiğini geçmedi — limit-giriş 4H'de fiilen dolmuyor.")


if __name__ == "__main__":
    main()
