#!/usr/bin/env python3
"""
run_edge_parallel.py — Dürüst edge ölçümünü coin'ler arası PARALEL koşar.
Çok-yıllık (5.4y) × 20 coin veride score_slice_v2 yavaş olduğundan
ProcessPoolExecutor ile coin başına bir işçi → ~Nx hızlanma.
Çıktı: per-coin tablo + havuz + zaman-dışı stabilite + /tmp/honest_trades_multiyear.json
"""
import os, sys, json, time, argparse, warnings
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed

warnings.filterwarnings("ignore")
from edge_audit import honest_backtest, edge_metrics, load_df


def work(args):
    coin, path, scale = args
    df = load_df(path)
    t0 = time.time()
    trades, st = honest_backtest(df, scale_in=scale)
    for t in trades:
        t["coin"] = coin
    m = edge_metrics(trades)
    return coin, len(df), st, m, trades, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="mktdata")
    ap.add_argument("--tf", default="4h")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--no-scale", action="store_true")
    ap.add_argument("--coins", default="")
    args = ap.parse_args()

    if args.coins:
        coins = args.coins.split(",")
    else:
        coins = sorted(f.split("_")[0] for f in os.listdir(args.data) if f.endswith(f"_{args.tf}.csv"))
    jobs = [(c, f"{args.data}/{c}_USDT_{args.tf}.csv", not args.no_scale)
            for c in coins if os.path.exists(f"{args.data}/{c}_USDT_{args.tf}.csv")]

    print("=" * 88)
    print(f"  DÜRÜST EDGE — PARALEL ({len(jobs)} coin, {args.workers} işçi)  {args.data}/ TF={args.tf}")
    print("=" * 88)
    print(f"  {'COIN':6}{'bars':>6}{'sig':>6}{'fill%':>7}{'N':>5}{'WR%':>7}{'avgR':>8}{'sumR':>9}{'PF':>6}{'lstrk':>6}{'sec':>6}")

    pool = []
    rows = []
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(work, j) for j in jobs]
        for f in as_completed(futs):
            coin, bars, st, m, trades, el = f.result()
            pool += trades
            rows.append((coin, bars, st, m, el))

    rows.sort(key=lambda x: x[0])
    for coin, bars, st, m, el in rows:
        if m["n"]:
            print(f"  {coin:6}{bars:>6}{st['signals']:>6}{st['fill_rate']:>7.1f}{m['n']:>5}"
                  f"{m['wr']:>7.1f}{m['avg_r']:>+8.3f}{m['sum_r']:>+9.1f}{m['pf']:>6.2f}{m['max_loss_streak']:>6}{el:>6.0f}")
        else:
            print(f"  {coin:6}{bars:>6}{st['signals']:>6}{st['fill_rate']:>7.1f}{0:>5}   (trade yok){'':>20}{el:>6.0f}")

    print("  " + "-" * 86)
    pm = edge_metrics(pool)
    if pm["n"]:
        # ortalama dolum oranı (sinyal ağırlıklı)
        tot_sig = sum(r[2]["signals"] for r in rows)
        tot_fill = sum(r[2]["filled_signals"] for r in rows)
        fr = tot_fill / tot_sig * 100 if tot_sig else 0
        print(f"  {'POOL':6}{'':>6}{tot_sig:>6}{fr:>7.1f}{pm['n']:>5}{pm['wr']:>7.1f}"
              f"{pm['avg_r']:>+8.3f}{pm['sum_r']:>+9.1f}{pm['pf']:>6.2f}{pm['max_loss_streak']:>6}")
        print(f"\n  Beklenti: {pm['expectancy']:+.4f}R/işlem | avg_win {pm['avg_win']:+.2f}R | avg_loss {pm['avg_loss']:+.2f}R | dolum %{fr:.1f}")

        pool.sort(key=lambda x: x["exit_ts"])
        q = len(pool) // 4
        for lab, seg in [("Ç1", pool[:q]), ("Ç2", pool[q:2*q]), ("Ç3", pool[2*q:3*q]), ("Ç4", pool[3*q:])]:
            sm = edge_metrics(seg)
            yr = (seg[0]["exit_ts"][:7], seg[-1]["exit_ts"][:7]) if seg else ("", "")
            print(f"  Zaman {lab} [{yr[0]}→{yr[1]}]: N={sm['n']:>4}  WR={sm['wr']:.1f}%  avgR={sm['avg_r']:+.3f}  PF={sm['pf']:.2f}")

        print(f"\n  >>> EDGE KARARI (5.4y, {len(jobs)} coin): WR={pm['wr']:.1f}%  beklenti={pm['expectancy']:+.3f}R")
        print(f"      {'POZİTİF EDGE ✓' if pm['expectancy']>0 else 'EDGE YOK ✗'}"
              f"  | %60 WR hedefi: {'TUTTU ✓' if pm['wr']>=60 else 'TUTMADI ✗ (FAZ 2 keskinleştirme gerek)'}")
    print(f"\n  toplam {time.time()-t0:.0f}s")
    json.dump(pool, open(f"/tmp/honest_trades_multiyear_{args.tf}.json", "w"), default=str)
    print(f"  ✅ {len(pool)} trade → /tmp/honest_trades_multiyear_{args.tf}.json")


if __name__ == "__main__":
    main()
