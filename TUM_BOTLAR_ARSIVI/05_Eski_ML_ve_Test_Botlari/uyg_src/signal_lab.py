#!/usr/bin/env python3
"""
signal_lab.py — ORTAK DÜRÜST SİNYAL DEĞERLENDİRME ZEMİNİ (multi-agent edge avı)
═══════════════════════════════════════════════════════════════════════
Amaç: HER sinyal hipotezini (SuperTrend, RSI, MACD, SMC, breakout, momentum…)
aynı titiz, look-ahead'siz, maliyetli, OOS-kontrollü motorla ölçmek.
Agent'lar yalnız signal_fn(df)->pos yazar; rigor burada sabittir.

Sözleşme:
  signal_fn(df) -> np.array pos[i] ∈ {-1,0,+1}   (i barında ARZULANAN yön)
  KURAL: pos[i] yalnız i ve öncesini kullanmalı (causal). Giriş i+1 açılışında olur.

Exit: SL (sl_atr×ATR) / TP (tp_r×risk) / pos flip / seri sonu.
Maliyet: market giriş+çıkış → taker fee + slippage (R cinsinden /risk).
Metrikler: WR, beklenti(R), frekans/yıl, Sharpe, profit factor; havuz + OOS
(ilk %60 train / son %40 test) + per-coin pozitiflik.
"""
import os, json, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

FEE = 0.0004          # taker
SLIP = 0.0003         # market/stop kayma
RT_COST_PRICE = (FEE + SLIP) * 2   # round-trip fiyat oranı
BARS_PER_YEAR = 6 * 365            # 4H

# ── indikatör yardımcıları (agent'lar kullanabilir) ──
def ema(s, n): return pd.Series(s).ewm(span=n, adjust=False).mean().to_numpy()
def sma(s, n): return pd.Series(s).rolling(n).mean().to_numpy()
def roc(s, n): a = np.asarray(s, float); return a/np.roll(a, n) - 1.0

def rsi(s, n=14):
    s = pd.Series(s); d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs = up/(dn+1e-12); return (100 - 100/(1+rs)).to_numpy()

def atr(df, n=14):
    h, l, c = df["high"].to_numpy(float), df["low"].to_numpy(float), df["close"].to_numpy(float)
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h-l, np.maximum(np.abs(h-pc), np.abs(l-pc)))
    return pd.Series(tr).ewm(alpha=1/n, adjust=False).mean().to_numpy()

def macd(s, fast=12, slow=26, sig=9):
    m = ema(s, fast) - ema(s, slow); sline = ema(m, sig); return m, sline, m - sline

def supertrend(df, period=10, mult=3.0):
    h, l, c = df["high"].to_numpy(float), df["low"].to_numpy(float), df["close"].to_numpy(float)
    a = atr(df, period); hl2 = (h + l) / 2
    up = hl2 - mult*a; dn = hl2 + mult*a
    st = np.zeros(len(c)); dir_ = np.ones(len(c))
    for i in range(1, len(c)):
        up[i] = max(up[i], up[i-1]) if c[i-1] > up[i-1] else up[i]
        dn[i] = min(dn[i], dn[i-1]) if c[i-1] < dn[i-1] else dn[i]
        if c[i] > dn[i-1]: dir_[i] = 1
        elif c[i] < up[i-1]: dir_[i] = -1
        else: dir_[i] = dir_[i-1]
    return dir_  # +1 uptrend, -1 downtrend

def bollinger(s, n=20, k=2.0):
    m = sma(s, n); sd = pd.Series(s).rolling(n).std().to_numpy()
    return m, m + k*sd, m - k*sd

def donchian(df, n=20):
    h = pd.Series(df["high"]).rolling(n).max().to_numpy()
    l = pd.Series(df["low"]).rolling(n).min().to_numpy()
    return h, l

def adx(df, n=14):
    h, l, c = df["high"].to_numpy(float), df["low"].to_numpy(float), df["close"].to_numpy(float)
    a = atr(df, n); up = h - np.roll(h, 1); dn = np.roll(l, 1) - l
    pdm = np.where((up > dn) & (up > 0), up, 0.0); mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    pdi = 100*pd.Series(pdm).ewm(alpha=1/n, adjust=False).mean().to_numpy()/(a+1e-12)
    mdi = 100*pd.Series(mdm).ewm(alpha=1/n, adjust=False).mean().to_numpy()/(a+1e-12)
    dx = 100*np.abs(pdi-mdi)/(pdi+mdi+1e-12)
    return pd.Series(dx).ewm(alpha=1/n, adjust=False).mean().to_numpy(), pdi, mdi


# ── veri ──
def load_all(data="mktdata", tf="4h"):
    out = {}
    for f in sorted(os.listdir(data)):
        if f.endswith(f"_{tf}.csv"):
            c = f.split("_")[0]
            df = pd.read_csv(f"{data}/{f}"); df["ts"] = pd.to_datetime(df["ts"])
            out[c] = df.set_index("ts").sort_index()
    return out


# ── çekirdek: pozisyon dizisinden trade üret (look-ahead'siz, maliyetli) ──
def simulate(df, pos, sl_atr=1.5, tp_r=2.0, warmup=200, allow_flip=True):
    O = df["open"].to_numpy(float); H = df["high"].to_numpy(float)
    L = df["low"].to_numpy(float); C = df["close"].to_numpy(float)
    A = atr(df, 14); idx = df.index; n = len(C)
    pos = np.asarray(pos); trades = []
    i = warmup
    while i < n - 1:
        d = pos[i]
        if d == 0:
            i += 1; continue
        entry = O[i+1]                      # i+1 açılışında gir (look-ahead yok)
        a = A[i] if A[i] > 0 else (entry*0.01)
        risk = sl_atr * a
        if risk <= 0: i += 1; continue
        sl = entry - d*risk; tp = entry + d*tp_r*risk
        sl_dist = risk/entry
        exit_p = None; j = i+1
        while j < n:
            hi, lo = H[j], L[j]
            if d == 1:
                if lo <= sl: exit_p = sl; break
                if hi >= tp: exit_p = tp; break
            else:
                if hi >= sl: exit_p = sl; break
                if lo <= tp: exit_p = tp; break
            if allow_flip and pos[j] == -d:    # ters sinyal → çık
                exit_p = O[j+1] if j+1 < n else C[j]; break
            j += 1
        if exit_p is None: exit_p = C[n-1]; j = n-1
        r_price = d*(exit_p - entry)/entry
        r_mult = r_price/sl_dist - RT_COST_PRICE/sl_dist   # R + maliyet
        trades.append({"r_mult": float(r_mult), "dir": int(d), "entry_i": i+1,
                       "entry_ts": str(idx[min(i+1, n-1)]),
                       "exit_ts": str(idx[min(j, n-1)]), "sl_dist": float(sl_dist)})
        i = j + 1                            # çıkıştan sonra devam
    return trades


def metrics(trades):
    if not trades: return {"n": 0}
    r = np.array([t["r_mult"] for t in trades]); w = r[r > 0]; l = r[r <= 0]
    return {"n": len(r), "wr": float((r > 0).mean()*100), "avg_r": float(r.mean()),
            "sum_r": float(r.sum()), "pf": float(w.sum()/abs(l.sum())) if len(l) and l.sum()!=0 else float("inf"),
            "avg_win": float(w.mean()) if len(w) else 0, "avg_loss": float(l.mean()) if len(l) else 0}


def evaluate(signal_fn, data="mktdata", tf="4h", sl_atr=1.5, tp_r=2.0, coins=None, label=""):
    """signal_fn(df)->pos. Havuz + OOS(ilk60/son40) + per-coin + frekans raporla."""
    dfs = load_all(data, tf)
    if coins: dfs = {c: dfs[c] for c in coins if c in dfs}
    pool = []; per_coin = {}; span_bars = 0
    for c, df in dfs.items():
        pos = signal_fn(df)
        tr = simulate(df, pos, sl_atr=sl_atr, tp_r=tp_r)
        for t in tr: t["coin"] = c
        per_coin[c] = metrics(tr); pool += tr; span_bars = max(span_bars, len(df))
    m = metrics(pool)
    pool.sort(key=lambda x: x["exit_ts"])
    split = int(len(pool)*0.6)
    tr_m = metrics(pool[:split]); te_m = metrics(pool[split:])
    pos_coins = sum(1 for c, cm in per_coin.items() if cm.get("avg_r", -9) > 0)
    freq_yr = m["n"]/ (span_bars/BARS_PER_YEAR) if span_bars else 0
    return {"label": label, "pool": m, "train": tr_m, "test": te_m,
            "pos_coins": pos_coins, "tot_coins": len(per_coin), "freq_yr": freq_yr,
            "robust": (m["avg_r"] > 0 and te_m.get("avg_r", -9) > 0 and pos_coins >= 0.6*len(per_coin))}


def report(res):
    p, tr, te = res["pool"], res["train"], res["test"]
    print(f"  [{res['label']}] N={p['n']} freq/yr={res['freq_yr']:.0f}  WR={p['wr']:.1f}%  "
          f"beklenti={p['avg_r']:+.3f}R  PF={p['pf']:.2f}")
    print(f"       OOS: train avgR={tr.get('avg_r',0):+.3f}  test avgR={te.get('avg_r',0):+.3f}  "
          f"per-coin+ {res['pos_coins']}/{res['tot_coins']}  → {'ROBUST ✓' if res['robust'] else 'robust değil'}")
    return res


if __name__ == "__main__":
    # SANITY: 2 referans sinyal
    import sys
    def buy_hold(df): return np.ones(len(df))  # hep long → kripto beta
    def st_trend(df): return supertrend(df, 10, 3.0)  # SuperTrend yönü
    print("="*80); print("  signal_lab SANITY (mktdata 4h)"); print("="*80)
    report(evaluate(buy_hold, label="buy&hold (beta)", tp_r=3.0, sl_atr=3.0))
    report(evaluate(st_trend, label="SuperTrend(10,3) trend-follow", tp_r=2.0, sl_atr=1.5))
