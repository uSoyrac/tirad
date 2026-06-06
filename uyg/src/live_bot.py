#!/usr/bin/env python3
"""
live_bot.py — TIRAD OPTİMAL BOT (paper/testnet/live)
═══════════════════════════════════════════════════════════════════════
Doğrulanmış sistem: top-5 · 4H · long+short · donchian+supertrend agreement
+ BTC-rejim hizalama + meta-label (v2+vov) kalite kapısı + rejim-gate (skor≥2)
+ seans filtresi (ölü saat 08-12 UTC yok) + fractional Kelly + max 5 poz.

MOD (env BOT_MODE):
  paper   (varsayılan): canlı veri çeker, SANAL portföy (gerçek emir YOK) — burada test edilebilir.
  testnet : Binance testnet (sahte para) — env BINANCE_TESTNET_KEY/SECRET gerekir.
  live    : GERÇEK PARA — env BINANCE_KEY/SECRET + BOT_CONFIRM_LIVE=YES gerekir. DİKKAT.

GÜVENLİK: Anahtarlar SADECE env'den okunur, koda yazılmaz. live için ekstra onay şart.
Kullanım:
  python3 live_bot.py            # tek tarama + dashboard (paper)
  python3 live_bot.py --loop     # 4H kapanışını bekleyip sürekli (paper)
"""
import os, sys, time, json, pickle, sqlite3, argparse, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
import ccxt
from signal_lab import atr, adx
from meta_features_v2 import coin_feats, FEATURES_V2, V1
import sig_donchian_breakout as D, sig_supertrend_regime as S

# ── KONFİG (doğrulanmış optimal) ──────────────────────────────────────
COINS      = ["BTC", "ETH", "SOL", "BNB", "XRP"]
TF         = "4h"
DONCHIAN   = D.make_sig(40, "atr", 0.25, 0.0)
SUPERTREND = S.make_sig(10, 3, 25)
SL_ATR, TP_R = 2.0, 2.75
BASE_RISK, MAX_RISK = 0.015, 0.03        # fractional Kelly (~quarter); agresif sleeve ayrı
MAX_POS    = 5
META_THR   = 0.35
REGIME_MIN = int(os.getenv("BOT_REGIME_MIN", "2"))   # rejim skoru < eşik → işlem yok (uyku)
DEAD_HOURS = {8, 12}                      # 08:00,12:00 UTC 4H barları zayıf → atla
MODE       = os.getenv("BOT_MODE", "paper")
DB         = os.getenv("BOT_DB", "live_bot.db")
START_EQ   = float(os.getenv("BOT_START_EQ", "100"))
MODEL_PATH = "meta_model_v2.pkl"

def log(m): print(f"  [{time.strftime('%H:%M:%S')}] {m}", flush=True)

# ── BORSA (mod'a göre) ────────────────────────────────────────────────
def make_exchange():
    if MODE == "live":
        if os.getenv("BOT_CONFIRM_LIVE") != "YES":
            sys.exit("⛔ live mod için BOT_CONFIRM_LIVE=YES ve BINANCE_KEY/SECRET gerekir. İptal.")
        ex = ccxt.binance({"apiKey": os.getenv("BINANCE_KEY"), "secret": os.getenv("BINANCE_SECRET"),
                           "enableRateLimit": True, "options": {"defaultType": "future"}})
    elif MODE == "testnet":
        ex = ccxt.binance({"apiKey": os.getenv("BINANCE_TESTNET_KEY"), "secret": os.getenv("BINANCE_TESTNET_SECRET"),
                           "enableRateLimit": True, "options": {"defaultType": "future"}})
        ex.set_sandbox_mode(True)
    else:  # paper — sadece public veri
        ex = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "future"}})
    return ex

def fetch_df(ex, coin, limit=460):
    o = ex.fetch_ohlcv(f"{coin}/USDT", TF, limit=limit)
    df = pd.DataFrame(o, columns=["ts","open","high","low","close","volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms"); df.set_index("ts", inplace=True)
    return df

# ── DB (pozisyon + equity kalıcılığı) ─────────────────────────────────
def db():
    c = sqlite3.connect(DB)
    c.execute("CREATE TABLE IF NOT EXISTS pos(coin TEXT PRIMARY KEY, dir INT, entry REAL, sl REAL, tp REAL, risk REAL, opened TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS eq(ts TEXT, equity REAL, event TEXT)")
    if not c.execute("SELECT COUNT(*) FROM eq").fetchone()[0]:
        c.execute("INSERT INTO eq VALUES(?,?,?)", (time.strftime("%Y-%m-%d %H:%M"), START_EQ, "START"))
    c.commit(); return c

def equity(c): return float(c.execute("SELECT equity FROM eq ORDER BY rowid DESC LIMIT 1").fetchone()[0])

# ── REJİM SKORU (BTC, causal) ─────────────────────────────────────────
def btc_regime(btc):
    c = btc["close"].to_numpy(float); a, _, _ = adx(btc, 14); at = atr(btc, 14)
    atrp = at/c; vov = pd.Series(atrp).rolling(30).std().to_numpy(); mom = pd.Series(c).pct_change(10).to_numpy()
    i = len(c)-1
    score = (1 if (np.isfinite(a[i]) and a[i] > 25) else 0) + \
            (1 if (np.isfinite(vov[i]) and vov[i] < np.nanmedian(vov)) else 0) + \
            (1 if (np.isfinite(mom[i]) and abs(mom[i]) > 0.05) else 0)
    above_ema = c[i] > btc["close"].ewm(span=200, adjust=False).mean().iloc[-1]
    return score, (1 if above_ema else -1)

# ── KARAR (tüm doğrulanmış zincir) ────────────────────────────────────
def decide(coin, df, btc, ctx, model, reg_score, btc_dir):
    if reg_score < REGIME_MIN:                       # rejim gate: uyku
        return None, "rejim<2 (uyku)"
    last_hour = df.index[-1].hour
    if last_hour in DEAD_HOURS:                       # seans filtresi
        return None, "ölü saat"
    don = int(DONCHIAN(df)[-1]); st = int(SUPERTREND(df)[-1])
    fired = [x for x in (don, st) if x != 0]
    if not fired or len(set(fired)) > 1:
        return None, "sinyal yok/çelişki"
    d = set(fired).pop()
    if d != btc_dir:                                  # BTC-rejim hizalama
        return None, "BTC trendine ters"
    c = df["close"].to_numpy(float); a = atr(df, 14)
    entry = float(c[-1]); at = float(a[-1]) if a[-1] > 0 else entry*0.01
    sl_dist = SL_ATR*at/entry
    if not (0.003 < sl_dist < 0.12):
        return None, "SL mesafesi dışı"
    # meta-label feature (entry barı, causal) — v2+vov; cross-sectional context ctx'ten
    fa = coin_feats(df); i = len(df)-1
    row = [float(fa[f][i]) if (f in fa and np.isfinite(fa[f][i])) else np.nan for f in V1]
    row += [float(d), float(sl_dist)]
    age = 0; sd = SUPERTREND(df)
    while i-age > 0 and sd[i-age] == sd[i] and sd[i] != 0: age += 1
    row += [ctx["xs"].get(coin, np.nan), ctx["btc_reg"], ctx["btc_ret"], float(age),
            fa["ext"][i] if np.isfinite(fa["ext"][i]) else np.nan,
            fa["volp"][i] if np.isfinite(fa["volp"][i]) else np.nan,
            fa["vov"][i] if np.isfinite(fa["vov"][i]) else np.nan]
    proba = float(model["model"].predict_proba(np.array([row]))[:,1][0])
    if proba < META_THR:
        return None, f"meta {proba:.2f}<{META_THR}"
    risk_pct = min(MAX_RISK, BASE_RISK*(0.5 + proba/META_THR*0.5))
    return {"dir": "LONG" if d == 1 else "SHORT", "d": d, "entry": entry,
            "sl": entry - d*SL_ATR*at, "tp": entry + d*TP_R*SL_ATR*at,
            "sl_dist": sl_dist, "proba": round(proba,3), "risk_pct": round(risk_pct,4),
            "reg": reg_score}, "AÇ"

# ── ANA TARAMA ────────────────────────────────────────────────────────
def scan(once=True):
    ex = make_exchange()
    if not os.path.exists(MODEL_PATH):
        sys.exit(f"⛔ {MODEL_PATH} yok — önce train_meta_v2.py çalıştır.")
    model = pickle.load(open(MODEL_PATH, "rb"))
    c = db()
    dfs = {coin: fetch_df(ex, coin) for coin in COINS}
    btc = dfs["BTC"]
    reg_score, btc_dir = btc_regime(btc)
    # cross-sectional context
    panel = pd.DataFrame({k: v["close"] for k, v in dfs.items()}).dropna()
    xs = (panel.pct_change(30).rank(axis=1, pct=True)).iloc[-1].to_dict()
    btc_e = btc["close"].ewm(span=200, adjust=False).mean().iloc[-1]
    ctx = {"xs": xs, "btc_reg": 1 if btc["close"].iloc[-1] > btc_e else 0,
           "btc_ret": float(btc["close"].pct_change(10).iloc[-1])}
    eq = equity(c)
    open_pos = {r[0]: r for r in c.execute("SELECT coin,dir,entry,sl,tp,risk,opened FROM pos").fetchall()}
    print("\n" + "="*70)
    print(f"  TIRAD OPTİMAL BOT [{MODE}] | kasa ${eq:.2f} | rejim skoru {reg_score}/3 | BTC yön {'↑' if btc_dir>0 else '↓'}")
    print(f"  Bar: {btc.index[-1]} UTC | açık poz: {len(open_pos)}/{MAX_POS}")
    print("="*70)
    # 1) açık pozisyon yönetimi (SL/TP)
    for coin, p in list(open_pos.items()):
        _, pd_, pe, psl, ptp, prisk, _ = p
        last = float(dfs[coin]["close"].iloc[-1]); hi = float(dfs[coin]["high"].iloc[-1]); lo = float(dfs[coin]["low"].iloc[-1])
        exit_p = None
        if pd_ == 1:
            if lo <= psl: exit_p = psl
            elif hi >= ptp: exit_p = ptp
        else:
            if hi >= psl: exit_p = psl
            elif lo <= ptp: exit_p = ptp
        if exit_p is not None:
            sl_dist = abs(pe - psl)/pe
            r = pd_*(exit_p - pe)/pe/sl_dist - 0.0007*2/sl_dist
            eq += prisk*r
            c.execute("DELETE FROM pos WHERE coin=?", (coin,))
            c.execute("INSERT INTO eq VALUES(?,?,?)", (str(btc.index[-1]), eq, f"{coin} ÇIK r={r:+.2f}"))
            log(f"ÇIKIŞ {coin} @ {exit_p:.4f} → r={r:+.2f}R kasa ${eq:.2f}  [{MODE}]")
            # GERÇEK emir: testnet/live'da ex.create_order(... reduceOnly) — paper'da sanal
        else:
            log(f"AÇIK  {coin} {'L' if pd_==1 else 'S'} giriş {pe:.4f} SL {psl:.4f} TP {ptp:.4f}")
    open_pos = {r[0]: r for r in c.execute("SELECT coin FROM pos").fetchall()}
    # 2) yeni giriş kararları
    for coin in COINS:
        if coin in open_pos: continue
        if len(c.execute("SELECT coin FROM pos").fetchall()) >= MAX_POS: break
        dec, reason = decide(coin, dfs[coin], btc, ctx, model, reg_score, btc_dir)
        if dec:
            risk_amt = eq * dec["risk_pct"]
            c.execute("INSERT OR REPLACE INTO pos VALUES(?,?,?,?,?,?,?)",
                      (coin, dec["d"], dec["entry"], dec["sl"], dec["tp"], risk_amt, str(btc.index[-1])))
            c.execute("INSERT INTO eq VALUES(?,?,?)", (str(btc.index[-1]), eq, f"{coin} AÇ {dec['dir']}"))
            log(f"🎯 GİRİŞ {coin} {dec['dir']} @ {dec['entry']:.4f} | SL {dec['sl']:.4f} TP {dec['tp']:.4f} | "
                f"meta {dec['proba']} risk ${risk_amt:.2f}  [{MODE}]")
            # GERÇEK emir: testnet/live'da ex.create_order(market) + SL/TP — paper'da sanal kayıt
        else:
            log(f"—     {coin}: {reason}")
    c.execute("INSERT INTO eq VALUES(?,?,?)", (str(btc.index[-1]), eq, "SCAN")); c.commit()
    print(f"\n  Tarama bitti | kasa ${eq:.2f} ({eq/START_EQ:.2f}x) | mod: {MODE}")
    c.close()

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--loop", action="store_true")
    a = ap.parse_args()
    print(f"\n🤖 TIRAD OPTİMAL BOT — mod: {MODE} (anahtarlar env'den; live için BOT_CONFIRM_LIVE=YES)")
    if a.loop:
        while True:
            scan()
            # sonraki 4H kapanışına kadar bekle
            now = time.time(); nxt = (int(now // 14400) + 1) * 14400 + 5
            log(f"sonraki 4H kapanışı bekleniyor (~{(nxt-now)/60:.0f} dk)…")
            time.sleep(max(60, nxt - now))
    else:
        scan()

if __name__ == "__main__":
    main()
