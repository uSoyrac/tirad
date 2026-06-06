#!/usr/bin/env python3
"""
faz2_exits.py — ÇIKIŞ ASİMETRİSİ SÜPÜRMESİ (S3 için son kaldıraç)
═══════════════════════════════════════════════════════════════════════
Dolan S3 girişlerini alıp farklı ÇIKIŞ şemalarını replay eder.
Soru: WR ~%37'de S3 girişleri "koşan" harekete giriyor mu? Çıkışı serbest
bırakınca beklenti pozitife dönüyor mu? (avg_win/avg_loss > ~1.7 gerek)

Şemalar: single TP@{2,3,4}R | ATR-trailing@{2,3} | runner(TP1+trail) | scaled(mevcut)
Maliyet: (komisyon RT + limit + market kayma)/sl_dist  her trade'den düşülür.
Overfit kontrolü: pooled + zaman-yarısı + per-coin pozitiflik.
"""
import os, sys, json, argparse, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
from edge_engine import get_fills, edge_metrics, load_df, ROUND_TRIP, SLIP_LIMIT, SLIP_MARKET

COST = ROUND_TRIP + SLIP_LIMIT + SLIP_MARKET


def replay(H, L, e, scheme, n):
    """Tek pozisyonu replay et → (net_r, exit_bar). R = risk birimi (|entry-sl|)."""
    entry = e["entry"]; sl = e["sl"]; atr = e["atr"]; is_long = e["dir"] in ("LONG", "BULLISH")
    risk = abs(entry - sl)
    if risk <= 0:
        return None, e["fill_bar"]
    sd = e["sl_dist"]; cost_r = COST / sd if sd > 0 else 0
    start = e["fill_bar"] + 1
    sign = 1 if is_long else -1

    def Rprice(p):  # fiyatı R'ye çevir
        return sign * (p - entry) / risk

    if scheme.startswith("single"):
        k = float(scheme.split("_")[1].replace("R", ""))
        tp = entry + sign * k * risk
        for j in range(start, n):
            hi = H[j]; lo = L[j]
            if is_long:
                if lo <= sl: return -1.0 - cost_r, j
                if hi >= tp: return k - cost_r, j
            else:
                if hi >= sl: return -1.0 - cost_r, j
                if lo <= tp: return k - cost_r, j
        return Rprice((H[n-1]+L[n-1])/2) - cost_r, n-1

    if scheme.startswith("trail"):
        m = float(scheme.split("_")[1].replace("atr", ""))
        tsl = sl
        for j in range(start, n):
            hi = H[j]; lo = L[j]
            if is_long:
                if lo <= tsl: return Rprice(tsl) - cost_r, j
                tsl = max(tsl, hi - m * atr)
            else:
                if hi >= tsl: return Rprice(tsl) - cost_r, j
                tsl = min(tsl, lo + m * atr)
        return Rprice((H[n-1]+L[n-1])/2) - cost_r, n-1

    if scheme == "runner":  # TP1 1.5R %50 kapat (lock 0.75R), kalan %50 trail 2.5atr
        tp1 = entry + sign * 1.5 * risk; tp1_hit = False; locked = 0.0; tsl = sl
        for j in range(start, n):
            hi = H[j]; lo = L[j]
            if not tp1_hit:
                if is_long and lo <= sl: return -1.0 - cost_r, j
                if (not is_long) and hi >= sl: return -1.0 - cost_r, j
                if (is_long and hi >= tp1) or ((not is_long) and lo <= tp1):
                    tp1_hit = True; locked = 0.5 * 1.5; tsl = entry  # breakeven kalan
            else:
                if is_long:
                    if lo <= tsl: return locked + 0.5 * Rprice(tsl) - cost_r, j
                    tsl = max(tsl, hi - 2.5 * atr)
                else:
                    if hi >= tsl: return locked + 0.5 * Rprice(tsl) - cost_r, j
                    tsl = min(tsl, lo + 2.5 * atr)
        return locked + 0.5 * Rprice((H[n-1]+L[n-1])/2) - cost_r, n-1

    if scheme == "scaled":  # mevcut: TP1 1.5R %40, TP2 3R %35, TP3 5R %25, TP1 sonrası breakeven
        tp1 = entry + sign*1.5*risk; tp2 = entry + sign*3.0*risk; tp3 = entry + sign*5.0*risk
        tp1_hit = tp2_hit = False; locked = 0.0; cur_sl = sl
        for j in range(start, n):
            hi = H[j]; lo = L[j]
            if is_long:
                if lo <= cur_sl: return (locked if tp1_hit else -1.0) - cost_r, j
                if hi >= tp3: return locked + 0.25*5.0 - cost_r, j
                if not tp2_hit and hi >= tp2: locked += 0.35*3.0; tp2_hit = True
                if not tp1_hit and hi >= tp1: locked += 0.40*1.5; tp1_hit = True; cur_sl = entry
            else:
                if hi >= cur_sl: return (locked if tp1_hit else -1.0) - cost_r, j
                if lo <= tp3: return locked + 0.25*5.0 - cost_r, j
                if not tp2_hit and lo <= tp2: locked += 0.35*3.0; tp2_hit = True
                if not tp1_hit and lo <= tp1: locked += 0.40*1.5; tp1_hit = True; cur_sl = entry
        return (locked if tp1_hit else Rprice((H[n-1]+L[n-1])/2)) - cost_r, n-1

    return None, start


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="mktdata"); ap.add_argument("--tf", default="4h")
    ap.add_argument("--entry", default="mid"); ap.add_argument("--timeout", type=int, default=12)
    args = ap.parse_args()
    cache = f"sigcache_{os.path.basename(args.data)}"
    coins = sorted(f.split("_")[0] for f in os.listdir(args.data) if f.endswith(f"_{args.tf}.csv"))
    coins = [c for c in coins if os.path.exists(f"{cache}/{c}_{args.tf}.json")]

    # dolan girişleri topla
    entries = {}
    for c in coins:
        df = load_df(f"{args.data}/{c}_USDT_{args.tf}.csv")
        sigs = json.load(open(f"{cache}/{c}_{args.tf}.json"))
        ents = get_fills(df, sigs, timeout=args.timeout, entry_mode=args.entry)
        entries[c] = (df["high"].to_numpy(), df["low"].to_numpy(), df.index, ents)
    tot = sum(len(v[3]) for v in entries.values())

    print("=" * 84)
    print(f"  ÇIKIŞ ASİMETRİSİ SÜPÜRMESİ — {args.data}/ ({len(coins)} coin, {tot} dolan giriş, fill={args.entry})")
    print("=" * 84)
    print(f"  {'şema':14}{'N':>6}{'WR%':>7}{'avgR':>8}{'avgW':>7}{'avgL':>7}{'PF':>6}{'sumR':>9}{'ilk½':>8}{'son½':>8}")

    schemes = ["scaled", "single_2R", "single_3R", "single_4R", "trail_2atr", "trail_3atr", "runner"]
    best = None
    for sch in schemes:
        pool = []
        for c, (H, L, idx, ents) in entries.items():
            n = len(H)
            for e in ents:
                r, xb = replay(H, L, e, sch, n)
                if r is None:
                    continue
                pool.append({"r_mult": r, "exit_ts": str(idx[min(xb, n-1)]), "coin": c})
        m = edge_metrics(pool)
        pool.sort(key=lambda x: x["exit_ts"]); h = len(pool)//2
        h1 = edge_metrics(pool[:h]); h2 = edge_metrics(pool[h:])
        stable = h1.get("avg_r", -9) > 0 and h2.get("avg_r", -9) > 0
        mark = " ✓STABİL" if stable and m["avg_r"] > 0 else (" +" if m["avg_r"] > 0 else "")
        print(f"  {sch:14}{m['n']:>6}{m['wr']:>7.1f}{m['avg_r']:>+8.3f}{m['avg_win']:>+7.2f}"
              f"{m['avg_loss']:>+7.2f}{m['pf']:>6.2f}{m['sum_r']:>+9.1f}{h1.get('avg_r',0):>+8.2f}{h2.get('avg_r',0):>+8.2f}{mark}")
        if m["avg_r"] > 0 and (best is None or m["avg_r"] > best[1]["avg_r"]):
            best = (sch, m, pool, stable)

    if best:
        sch, m, pool, stable = best
        print(f"\n  >>> EN İYİ ÇIKIŞ: {sch}  beklenti={m['avg_r']:+.3f}R  PF={m['pf']:.2f}  "
              f"{'ZAMAN-STABİL ✓' if stable else 'zaman-stabil DEĞİL ✗ (gürültü riski)'}")
        # per-coin pozitiflik
        bycoin = {}
        for t in pool:
            bycoin.setdefault(t["coin"], []).append(t)
        pos = sum(1 for c, ts in bycoin.items() if edge_metrics(ts)["avg_r"] > 0)
        print(f"      per-coin: {pos}/{len(bycoin)} coinde beklenti pozitif")
        if m["avg_r"] > 0 and stable and pos >= len(bycoin) * 0.6:
            print(f"      ✅ S3 YAŞIYOR — bu çıkışla robust pozitif edge. FAZ 3 compound buraya kurulur.")
            json.dump(pool, open(f"/tmp/faz2_exit_best_{os.path.basename(args.data)}.json", "w"), default=str)
        else:
            print(f"      ⚠ Pozitif ama robust değil → S3 girişi zayıf; sinyal tabanı değişmeli (pivot).")
    else:
        print(f"\n  ✗ HİÇBİR ÇIKIŞ beklentiyi pozitife çevirmedi → S3 girişi değersiz. PİVOT şart.")


if __name__ == "__main__":
    main()
