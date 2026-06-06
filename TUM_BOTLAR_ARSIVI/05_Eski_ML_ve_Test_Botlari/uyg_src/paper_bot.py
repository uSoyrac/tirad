#!/usr/bin/env python3
"""
paper_bot.py — PAPER-TRADE BOTU + REPLAY DOĞRULAMA (FAZ 4)
═══════════════════════════════════════════════════════════════════════
Doğrulanmış sistemi (donchian+supertrend agreement + meta-label + Kelly +
eşzamanlı tavan + SL/TP) çalıştırır. İki mod:
  --replay : son OOS dilimini bar-bar oynat → botun GERÇEK mantığı backtest
             edge'ini üretiyor mu? (canlıya geçişin son sınavı)
  --live   : ccxt ile canlı 4H çek, paper hesabı yönet (ileri forward-test)

Bot mantığı backtest'ten FARKLI (tek-pozisyon/coin + çelişki-dışlama) → ayrı doğrulama.
"""
import os, sys, json, pickle, argparse, numpy as np
import warnings; warnings.filterwarnings("ignore")
from signal_lab import load_all, atr, metrics
from meta_label import feat_arrays, FEATURES
import sig_donchian_breakout as D, sig_supertrend_regime as S
from live_strategy import DONCHIAN, SUPERTREND, SL_ATR, TP_R, BASE_RISK, MAX_RISK

def precompute(df):
    return {"O": df["open"].to_numpy(float), "H": df["high"].to_numpy(float),
            "L": df["low"].to_numpy(float), "C": df["close"].to_numpy(float),
            "atr": atr(df, 14), "don": DONCHIAN(df), "st": SUPERTREND(df),
            "feat": feat_arrays(df), "idx": df.index}

def candidate(pc, t, model):
    """Bar t'de (son kapanmış) entry kararı — live_strategy.decide ile aynı mantık, hızlı."""
    don = int(pc["don"][t]); st = int(pc["st"][t])
    fired = [x for x in (don, st) if x != 0]
    if not fired:
        return None
    dirs = set(fired)
    if len(dirs) > 1:
        return None                          # çelişki → atla
    d = dirs.pop()
    entry = float(pc["C"][t]); at = float(pc["atr"][t]) if pc["atr"][t] > 0 else entry*0.01
    risk_px = SL_ATR*at; sl_dist = risk_px/entry
    if not (0.003 < sl_dist < 0.12):
        return None
    proba = None
    if model:
        fa = pc["feat"]
        row = [float(fa[f][t]) if f in fa and np.isfinite(fa[f][t]) else np.nan for f in FEATURES[:10]]
        row += [d, sl_dist]
        proba = float(model["model"].predict_proba(np.array([row]))[:,1][0])
        if proba < model["threshold"]:
            return None
    risk_pct = BASE_RISK if proba is None else min(MAX_RISK, BASE_RISK*(0.5 + proba/model["threshold"]*0.5))
    return {"d": d, "entry": entry, "sl": entry - d*risk_px, "tp": entry + d*TP_R*risk_px,
            "sl_dist": sl_dist, "proba": proba, "risk_pct": risk_pct}

def replay(start_frac=0.60, max_concurrent=10, use_meta=True, start_eq=100.0, risk_mult=1.0, quiet=False):
    dfs = load_all("mktdata", "4h")
    pcs = {c: precompute(df) for c, df in dfs.items()}
    model = pickle.load(open("meta_model.pkl","rb")) if (use_meta and os.path.exists("meta_model.pkl")) else None
    n = max(len(p["C"]) for p in pcs.values())
    t0 = int(n*start_frac)
    eq = start_eq; peak = start_eq; mdd = 0.0
    positions = {}   # coin -> pos dict
    trades = []
    for t in range(t0, n-1):
        # --- EXIT yönetimi ---
        for c in list(positions.keys()):
            p = positions[c]; pc = pcs[c]
            if t >= len(pc["C"]): positions.pop(c); continue
            hi, lo = pc["H"][t], pc["L"][t]; d = p["d"]
            exit_p = None
            if d == 1:
                if lo <= p["sl"]: exit_p = p["sl"]
                elif hi >= p["tp"]: exit_p = p["tp"]
            else:
                if hi >= p["sl"]: exit_p = p["sl"]
                elif lo <= p["tp"]: exit_p = p["tp"]
            if exit_p is not None:
                r = d*(exit_p - p["entry"])/p["entry"]/p["sl_dist"] - (0.0004+0.0003)*2/p["sl_dist"]
                eq += p["risk_amt"]*r
                peak = max(peak, eq); mdd = max(mdd, (peak-eq)/peak if peak>0 else 0)
                trades.append({"coin": c, "r_mult": r, "exit_ts": str(pc["idx"][t]), "proba": p["proba"]})
                positions.pop(c)
        # --- ENTRY ---
        for c, pc in pcs.items():
            if c in positions or len(positions) >= max_concurrent: continue
            if t >= len(pc["C"])-1: continue
            dec = candidate(pc, t, model)
            if dec:
                entry = float(pc["O"][t+1])           # sıradaki açılışta gir (look-ahead yok)
                risk_amt = eq * dec["risk_pct"] * risk_mult
                positions[c] = {**dec, "entry": entry, "risk_amt": risk_amt,
                                "sl": entry - dec["d"]*SL_ATR*pc["atr"][t],
                                "tp": entry + dec["d"]*TP_R*SL_ATR*pc["atr"][t]}
        if eq <= 0: break
    m = metrics(trades)
    span_years = (n-t0)/(6*365)
    if quiet:
        x = eq/start_eq; cagr = (x**(1/span_years)-1)*100 if x>0 else -100
        return {"eq": eq, "x": x, "mdd": mdd*100, "cagr": cagr, "n": m.get("n",0),
                "wr": m.get("wr",0), "e": m.get("avg_r",0)}
    print("="*78)
    print(f"  PAPER BOT REPLAY — son %{(1-start_frac)*100:.0f} ({span_years:.1f} yıl OOS) | meta={'AÇIK' if model else 'KAPALI'}")
    print("="*78)
    print(f"  İşlem: {m['n']}  (~{m['n']/span_years:.0f}/yıl)  WR={m.get('wr',0):.1f}%  beklenti={m.get('avg_r',0):+.3f}R  PF={m.get('pf',0):.2f}")
    print(f"  Equity: ${start_eq:.0f} → ${eq:,.0f} ({eq/start_eq:.1f}x)  MaxDD={mdd*100:.1f}%")
    if m.get("n"):
        h = len(trades)//2
        m1 = metrics(trades[:h]); m2 = metrics(trades[h:])
        print(f"  Zaman: ilk½ E={m1.get('avg_r',0):+.3f}  son½ E={m2.get('avg_r',0):+.3f}")
        exp = "+0.12R (meta) / +0.08R (filtresiz)"
        print(f"  Backtest beklentisi: {exp} → bot {'TUTARLI ✓' if m.get('avg_r',0)>0 else 'TUTARSIZ ✗'}")
    return eq, m

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", action="store_true")
    ap.add_argument("--no-meta", action="store_true")
    ap.add_argument("--max-pos", type=int, default=10)
    ap.add_argument("--start", type=float, default=0.60)
    args = ap.parse_args()
    if args.replay:
        replay(start_frac=args.start, max_concurrent=args.max_pos, use_meta=not args.no_meta)
    else:
        print("Kullanım: python3 paper_bot.py --replay [--no-meta] [--max-pos 10]")
        print("(--live modu ccxt forward-test için sonraki adımda eklenecek)")

if __name__ == "__main__":
    main()
