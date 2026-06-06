#!/usr/bin/env python3
"""
bot_v2.py — ENTEGRE PRODUCTION BOT (v2+vov meta-model)
═══════════════════════════════════════════════════════════════════════
paper_bot (v1) + tam v2+vov feature pipeline + cross-sectional panel context.
Replay ile final sistemi ölçer. Feature kurgusu meta_features_v2.build_v2 ile birebir.
"""
import os, json, pickle, argparse, numpy as np, pandas as pd
import warnings; warnings.filterwarnings("ignore")
from signal_lab import load_all, atr, metrics
from meta_features_v2 import coin_feats, FEATURES_V2, V1
from live_strategy import DONCHIAN, SUPERTREND, SL_ATR, TP_R, BASE_RISK, MAX_RISK

def build_context(dfs):
    panel = pd.DataFrame({c: df["close"] for c, df in dfs.items()}).sort_index().ffill()
    xs = panel.pct_change(30).rank(axis=1, pct=True)
    btc = dfs["BTC"]; btc_e = btc["close"].ewm(span=200, adjust=False).mean()
    btc_reg = (btc["close"] > btc_e).astype(int); btc_ret = btc["close"].pct_change(10)
    return {"xs": xs, "btc_reg": btc_reg, "btc_ret": btc_ret}

def precompute(c, df, ctx):
    fa = coin_feats(df); idx = df.index
    return {"O": df["open"].to_numpy(float), "H": df["high"].to_numpy(float),
            "L": df["low"].to_numpy(float), "C": df["close"].to_numpy(float),
            "atr": atr(df, 14), "don": DONCHIAN(df), "st": SUPERTREND(df), "fa": fa, "idx": idx,
            "xs": ctx["xs"][c].reindex(idx).to_numpy(),
            "btc_reg": ctx["btc_reg"].reindex(idx).to_numpy(),
            "btc_ret": ctx["btc_ret"].reindex(idx).to_numpy()}

def feature_row(pc, t, d, sl_dist):
    fa = pc["fa"]
    row = [float(fa[f][t]) if (f in fa and np.isfinite(fa[f][t])) else np.nan for f in V1]
    row += [float(d), float(sl_dist)]
    # trend_age: st_dir aynı-yön run (causal)
    age = 0; sd = pc["st"]
    while t-age > 0 and sd[t-age] == sd[t] and sd[t] != 0: age += 1
    row += [pc["xs"][t], pc["btc_reg"][t], pc["btc_ret"][t], float(age),
            fa["ext"][t] if np.isfinite(fa["ext"][t]) else np.nan,
            fa["volp"][t] if np.isfinite(fa["volp"][t]) else np.nan,
            fa["vov"][t] if np.isfinite(fa["vov"][t]) else np.nan]
    return np.array([row], float)

def candidate(pc, t, model):
    don = int(pc["don"][t]); st = int(pc["st"][t])
    fired = [x for x in (don, st) if x != 0]
    if not fired or len(set(fired)) > 1: return None
    d = set(fired).pop()
    entry = float(pc["C"][t]); at = float(pc["atr"][t]) if pc["atr"][t] > 0 else entry*0.01
    risk_px = SL_ATR*at; sl_dist = risk_px/entry
    if not (0.003 < sl_dist < 0.12): return None
    proba = None
    if model:
        proba = float(model["model"].predict_proba(feature_row(pc, t, d, sl_dist))[:,1][0])
        if proba < model["threshold"]: return None
    rp = BASE_RISK if proba is None else min(MAX_RISK, BASE_RISK*(0.5 + proba/model["threshold"]*0.5))
    return {"d": d, "sl_dist": sl_dist, "proba": proba, "risk_pct": rp}

def replay(start_frac=0.60, max_pos=8, risk_mult=0.5, model_path="meta_model_v2.pkl", quiet=False):
    dfs = load_all("mktdata", "4h"); ctx = build_context(dfs)
    pcs = {c: precompute(c, df, ctx) for c, df in dfs.items()}
    model = pickle.load(open(model_path,"rb")) if os.path.exists(model_path) else None
    n = max(len(p["C"]) for p in pcs.values()); t0 = int(n*start_frac)
    eq = 100.0; peak = 100.0; mdd = 0.0; pos = {}; trades = []
    for t in range(t0, n-1):
        for c in list(pos.keys()):
            p = pos[c]; pc = pcs[c]
            if t >= len(pc["C"]): pos.pop(c); continue
            hi, lo = pc["H"][t], pc["L"][t]; dd = p["d"]; xp = None
            if dd == 1:
                if lo <= p["sl"]: xp = p["sl"]
                elif hi >= p["tp"]: xp = p["tp"]
            else:
                if hi >= p["sl"]: xp = p["sl"]
                elif lo <= p["tp"]: xp = p["tp"]
            if xp is not None:
                r = dd*(xp-p["entry"])/p["entry"]/p["sl_dist"] - 0.0007*2/p["sl_dist"]
                eq += p["risk_amt"]*r; peak = max(peak, eq); mdd = max(mdd, (peak-eq)/peak if peak>0 else 0)
                trades.append({"r_mult": r, "exit_ts": str(pc["idx"][t])}); pos.pop(c)
        for c, pc in pcs.items():
            if c in pos or len(pos) >= max_pos or t >= len(pc["C"])-1: continue
            dec = candidate(pc, t, model)
            if dec:
                entry = float(pc["O"][t+1]); ra = eq*dec["risk_pct"]*risk_mult
                pos[c] = {**dec, "entry": entry, "risk_amt": ra,
                          "sl": entry - dec["d"]*SL_ATR*pc["atr"][t], "tp": entry + dec["d"]*TP_R*SL_ATR*pc["atr"][t]}
        if eq <= 0: break
    m = metrics(trades); yr = (n-t0)/(6*365); x = eq/100
    cagr = (x**(1/yr)-1)*100 if x>0 else -100
    if quiet: return {"x": x, "mdd": mdd*100, "cagr": cagr, "n": m.get("n",0), "wr": m.get("wr",0), "e": m.get("avg_r",0)}
    print("="*74); print(f"  BOT v2+vov REPLAY — son %{(1-start_frac)*100:.0f} ({yr:.1f}y OOS), risk_mult={risk_mult} maxPos={max_pos}"); print("="*74)
    print(f"  İşlem {m['n']} (~{m['n']/yr:.0f}/yıl)  WR {m.get('wr',0):.1f}%  beklenti {m.get('avg_r',0):+.3f}R  PF {m.get('pf',0):.2f}")
    print(f"  Equity $100 → ${eq:,.0f} ({x:.1f}x)  MaxDD {mdd*100:.1f}%  CAGR {cagr:.0f}%")
    h = len(trades)//2
    if h: print(f"  Zaman: ilk½ E={metrics(trades[:h]).get('avg_r',0):+.3f}  son½ E={metrics(trades[h:]).get('avg_r',0):+.3f}")
    return {"x": x, "mdd": mdd*100, "cagr": cagr, "e": m.get("avg_r",0)}

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--risk-mult", type=float, default=0.5); ap.add_argument("--max-pos", type=int, default=8)
    a = ap.parse_args()
    if a.sweep:
        print("v2+vov bot — risk × maxPos süpürmesi (MDD≤%30):")
        print(f"  {'rmult':>6}{'maxPos':>7}{'işlem':>7}{'E(R)':>7}{'x':>7}{'MDD%':>7}{'CAGR%':>7}")
        for rm in [0.33, 0.5, 0.66]:
            for mp in [5, 8, 10]:
                r = replay(risk_mult=rm, max_pos=mp, quiet=True)
                fl = " ✓" if r["mdd"]<=30 and r["x"]>1 else ""
                print(f"  {rm:>6.2f}{mp:>7}{r['n']:>7}{r['e']:>+7.3f}{r['x']:>7.1f}{r['mdd']:>7.1f}{r['cagr']:>7.0f}{fl}")
    else:
        replay(risk_mult=a.risk_mult, max_pos=a.max_pos)

if __name__ == "__main__":
    main()
