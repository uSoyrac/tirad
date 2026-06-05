#!/usr/bin/env python3
"""
GERÇEK VERİ BACKTEST — Son 3 ay / 4H / $100 ORP testi
=====================================================

NEDEN BU DOSYA?
  - Mevcut `score_slice_v2` motoru live_scan -> ccxt/yfinance/ta zincirine bağlı
    ve `ta` paketi bazı ortamlarda wheel derleyemiyor. Bu script ZİNCİRE
    DOKUNMAZ; sadece requests+pandas+numpy ile her yerde çalışır.
  - Veriyi Binance'in PUBLIC ucundan çeker -> API KEY GEREKMEZ (auth yok).
    Secret key paylaşmana asla gerek yoktu; bu script anahtar kullanmaz.
  - ORP para yönetimi için senin GERÇEK motorun `dynamic_optimizer.run_orp_dynamic`
    kullanılır (uydurma yok).

SADIK OLDUĞU AGENT.md KURALLARI:
  - 4H zaman dilimi, Top likit coinler (BTC/ETH/SOL/BNB/XRP).
  - Market emri YOK -> 2 kademeli Limit Scale-In (%50 OB üstü, %50 FVG ortası).
  - 12 saat (=3 mum) içinde dolmazsa emir İPTAL.
  - SL = Order Block'un dibi (+tampon), TP = giriş + 2*ATR.
  - Komisyon erimesi modellenir (Binance maker/taker + slippage).
  - ORP: %4 base risk, %20 max cap, %10 cycle, recovery_factor=1.0.

DÜRÜSTLÜK NOTU:
  Bu, `score_slice_v2`nin BİREBİR kopyası DEĞİL; AGENT.md kurallarının temiz,
  bağımsız ve denetlenebilir bir uygulamasıdır (clean-room). Amaç: gerçek veride
  şeffaf, tekrar üretilebilir bir alt-sınır (baseline) WR ve $100 sonucu vermek.
  Tam motorla birebir eşleştirmek istersen, ta/ccxt'yi çalışan bir ortamda
  kurup vectorized_dataset_builder.py'yi de besleyebiliriz.

KULLANIM:
  python3 real_backtest_3m.py                 # Binance'ten canlı çek (ağ açıksa)
  python3 real_backtest_3m.py --demo          # sentetik veriyle pipeline testi
  python3 real_backtest_3m.py --months 3
"""
import os
import sys
import time
import json
import argparse
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HERE)
from dynamic_optimizer import run_orp_dynamic  # senin gerçek ORP motorun

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
INTERVAL = "4h"
BARS_PER_DAY = 6  # 24/4

# --- Komisyon / slippage (Binance USDT-M, gerçekçi) ---
MAKER_FEE = 0.0002   # limit giriş ve TP (maker)
TAKER_FEE = 0.0004   # SL (taker, piyasa kapanışı)
SLIPPAGE = 0.0005    # SL'de kayma

# --- Strateji parametreleri ---
ATR_LEN = 14
EMA_TREND = 200      # 4H trend filtresi (AGENT.md _trend_1d mantığı)
FILL_BARS = 3        # 12 saat = 3 x 4H
MAX_HOLD_BARS = 30   # pozisyon zaman aşımı (~5 gün)
TP_ATR_MULT = 2.0
SL_BUFFER = 0.10     # OB dibinin %10 ATR altına SL tamponu

# --- ORP (AGENT.md kesinleşmiş mimari) ---
ORP_PARAMS = {
    "cycle_target_pct": 0.10,
    "recovery_factor": 1.0,
    "max_risk_cap": 0.20,
    "base_risk_pct": 0.04,
    "max_leverage": 10.0,
    "dynamic_recovery": False,
    "dd_scaling": False,
    "start_capital": 100.0,
}


# ───────────────────────── VERİ ÇEKME (anahtarsız) ─────────────────────────
def fetch_klines(symbol, interval, months):
    """Binance public klines — auth YOK. Sayfalı çeker."""
    import requests
    limit = 1000
    end = int(time.time() * 1000)
    start = end - int(months * 30 * 24 * 3600 * 1000)
    rows = []
    hosts = ["https://api.binance.com", "https://data-api.binance.vision"]
    cur = start
    while cur < end:
        ok = False
        for h in hosts:
            try:
                r = requests.get(
                    f"{h}/api/v3/klines",
                    params={"symbol": symbol, "interval": interval,
                            "startTime": cur, "limit": limit},
                    timeout=15,
                )
                if r.status_code == 200:
                    data = r.json()
                    ok = True
                    break
            except Exception:
                continue
        if not ok or not data:
            break
        rows.extend(data)
        cur = data[-1][0] + 1
        if len(data) < limit:
            break
        time.sleep(0.25)
    if not rows:
        raise RuntimeError(f"{symbol}: veri çekilemedi (ağ engelli olabilir).")
    df = pd.DataFrame(rows, columns=[
        "ts", "open", "high", "low", "close", "volume",
        "ct", "qv", "n", "tb", "tq", "ig"])
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms")
    return df[["ts", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def demo_klines(symbol, months, seed):
    """Sentetik GBM fiyat — SADECE pipeline doğrulaması için (gerçek değil)."""
    rng = np.random.default_rng(seed)
    n = int(months * 30 * BARS_PER_DAY)
    mu, sigma = 0.0001, 0.018
    rets = rng.normal(mu, sigma, n)
    price = 100 * np.exp(np.cumsum(rets))
    o = price * (1 + rng.normal(0, 0.002, n))
    c = price
    hi = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.004, n)))
    lo = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.004, n)))
    vol = np.abs(rng.normal(1000, 300, n))
    ts = pd.date_range("2025-03-01", periods=n, freq="4h")
    return pd.DataFrame({"ts": ts, "open": o, "high": hi, "low": lo,
                         "close": c, "volume": vol})


# ───────────────────────── İNDİKATÖRLER (saf pandas) ─────────────────────────
def add_indicators(df):
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(ATR_LEN).mean()
    df["ema_trend"] = c.ewm(span=EMA_TREND, adjust=False).mean()
    return df


# ───────────────────────── SİNYAL: OB + FVG + Scale-In ─────────────────────────
def find_signals(df):
    """
    Bullish kurulum (AGENT.md mantığı):
      - Trend: close > EMA200 (4H).
      - Displacement: i-1 düşüş mumu, i güçlü yükseliş ve i.close > (i-1).high (BOS).
      - Order Block = (i-1) düşüş mumu: zone = [low(i-1), high(i-1)].
      - FVG (bullish) = boşluk: low(i+? ) ... biz high(i-1) ile low(i+1) arası -> burada
        i. mum impuls; FVG ortası = (high(i-1) + low(i+1)) / 2 yaklaşımı yerine
        klasik 3-mum FVG: gap = low(i) > high(i-2) ? Basit ve sağlam için:
        FVG_mid = (high(i-1) + low(i)) / 2  (OB üstü ile impuls dibi ortası).
      - Limit Scale-In: leg1 = high(i-1) (OB üstü), leg2 = FVG_mid (daha aşağı).
      - SL = low(i-1) - SL_BUFFER*ATR ; TP = avg_entry + 2*ATR.
    Bearish simetrik.
    Döndürür: her sinyal için fill+sonuç simülasyonu yapılmış dict listesi.
    """
    sigs = []
    atr = df["atr"].values
    o, h, l, c = df["open"].values, df["high"].values, df["low"].values, df["close"].values
    ema = df["ema_trend"].values
    ts = df["ts"].values
    n = len(df)

    for i in range(EMA_TREND + 2, n - 1):
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        prev_down = c[i-1] < o[i-1]
        prev_up = c[i-1] > o[i-1]
        impulse_up = (c[i] > o[i]) and (c[i] > h[i-1]) and ((c[i]-o[i]) > 0.5*a)
        impulse_dn = (c[i] < o[i]) and (c[i] < l[i-1]) and ((o[i]-c[i]) > 0.5*a)

        sig = None
        if c[i] > ema[i] and prev_down and impulse_up:
            ob_top, ob_bot = h[i-1], l[i-1]
            leg1 = ob_top
            leg2 = (ob_top + l[i]) / 2.0
            sl = ob_bot - SL_BUFFER * a
            sig = ("BULLISH", leg1, leg2, sl, a, i)
        elif c[i] < ema[i] and prev_up and impulse_dn:
            ob_bot, ob_top = l[i-1], h[i-1]
            leg1 = ob_bot
            leg2 = (ob_bot + h[i]) / 2.0
            sl = ob_top + SL_BUFFER * a
            sig = ("BEARISH", leg1, leg2, sl, a, i)
        if sig is None:
            continue

        trade = simulate_trade(df, sig)
        if trade is not None:
            trade["ts"] = ts[i]
            trade["coin_i"] = i
            sigs.append(trade)
    return sigs


def simulate_trade(df, sig):
    direction, leg1, leg2, sl, a, i = sig
    h, l = df["high"].values, df["low"].values
    n = len(df)

    # --- Limit dolum (12h = 3 mum) ---
    filled = []  # (price, weight)
    for k in range(i+1, min(i+1+FILL_BARS, n)):
        if direction == "BULLISH":
            if leg1 not in [f[0] for f in filled] and l[k] <= leg1:
                filled.append((leg1, 0.5))
            if leg2 not in [f[0] for f in filled] and l[k] <= leg2:
                filled.append((leg2, 0.5))
        else:
            if leg1 not in [f[0] for f in filled] and h[k] >= leg1:
                filled.append((leg1, 0.5))
            if leg2 not in [f[0] for f in filled] and h[k] >= leg2:
                filled.append((leg2, 0.5))
    if not filled:
        return None  # 12 saatte dolmadı -> iptal (slippage SIFIR)

    w = sum(f[1] for f in filled)
    entry = sum(p*wt for p, wt in filled) / w
    if direction == "BULLISH":
        if sl >= entry:
            return None
        tp = entry + TP_ATR_MULT * a
        risk = entry - sl
    else:
        if sl <= entry:
            return None
        tp = entry - TP_ATR_MULT * a
        risk = sl - entry
    if risk <= 0:
        return None

    sl_pct = risk / entry * 100.0
    rr = (abs(tp - entry)) / risk  # ham R (kazançta)

    # --- Pozisyon takibi: TP mi SL mi önce? ---
    fill_start = i + 1
    outcome = None
    for k in range(fill_start, min(i+1+MAX_HOLD_BARS, n)):
        if direction == "BULLISH":
            if l[k] <= sl:
                outcome = "SL"; break
            if h[k] >= tp:
                outcome = "TP"; break
        else:
            if h[k] >= sl:
                outcome = "SL"; break
            if l[k] <= tp:
                outcome = "TP"; break
    if outcome is None:
        outcome = "TIMEOUT"

    # --- Komisyon erimesi (R cinsine çevir) ---
    # giriş maker, çıkış: TP maker / SL taker+slippage
    entry_fee = MAKER_FEE
    if outcome == "TP":
        exit_cost = MAKER_FEE
        gross_r = rr
    elif outcome == "SL":
        exit_cost = TAKER_FEE + SLIPPAGE
        gross_r = -1.0
    else:  # TIMEOUT -> son fiyatta kapat (yaklaşık), taker
        exit_cost = TAKER_FEE
        last = df["close"].values[min(i+MAX_HOLD_BARS, n-1)]
        if direction == "BULLISH":
            gross_r = (last - entry) / risk
        else:
            gross_r = (entry - last) / risk
    fee_r = (entry_fee + exit_cost) / (risk / entry)  # komisyonun R karşılığı
    net_r = gross_r - fee_r

    return {
        "direction": direction, "outcome": outcome,
        "r_mult": float(net_r), "sl_pct": float(sl_pct),
        "rr": float(rr), "legs": len(filled),
    }


# ───────────────────────── RAPOR ─────────────────────────
def report(trades):
    if not trades:
        print("Hiç işlem üretilmedi.")
        return
    trades = sorted(trades, key=lambda t: t["ts"])  # portföy: kronolojik sıralı
    r = np.array([t["r_mult"] for t in trades])
    wins = r > 0
    wr = wins.mean()
    n = len(trades)
    filled_tp = sum(1 for t in trades if t["outcome"] == "TP")
    filled_sl = sum(1 for t in trades if t["outcome"] == "SL")
    timeout = sum(1 for t in trades if t["outcome"] == "TIMEOUT")

    # max ardışık kayıp
    mcl = cur = 0
    for x in r:
        cur = cur + 1 if x <= 0 else 0
        mcl = max(mcl, cur)

    print("\n" + "="*64)
    print(" 📊 GERÇEK VERİ BACKTEST — 3 AY / 4H")
    print("="*64)
    print(f"Toplam işlem (dolan)  : {n}")
    print(f"  TP / SL / Timeout   : {filled_tp} / {filled_sl} / {timeout}")
    print(f"Win Rate (net, fee'li): %{100*wr:.1f}")
    print(f"Ortalama R (beklenti) : {r.mean():+.3f} R / işlem")
    print(f"Toplam R              : {r.sum():+.2f} R")
    print(f"Max ardışık kayıp     : {mcl}")

    # ORP $100 testi — senin gerçek motorun
    res = run_orp_dynamic([{"r_mult": t["r_mult"], "sl_pct": t["sl_pct"]} for t in trades], ORP_PARAMS)
    print("\n--- 💵 $100 KASA (ORP — %4 base, %20 cap, %10 cycle) ---")
    print(f"3 ay sonra kasa       : ${res['final_eq']:,.2f}")
    print(f"Büyüme                : %{((res['final_eq']/100)-1)*100:,.1f}")
    print(f"Maksimum Drawdown     : %{res['max_drawdown']:.1f}")

    # Karşılaştırma: sabit %4 risk (ORP'siz)
    eq = 100.0
    for t in trades:
        eq += eq * 0.04 * t["r_mult"]
        if eq <= 1:
            eq = 0; break
    print(f"\n--- Kıyas: sabit %4 risk (ORP'siz) ---")
    print(f"3 ay sonra kasa       : ${eq:,.2f}")

    print("\n" + "="*64)
    if wr < 0.5 or r.mean() <= 0:
        print("UYARI: Net beklenti pozitif değil. Komisyon/sinyal kalitesi gözden geçirilmeli.")
    print("Not: Bu, AGENT.md kurallarının temiz uygulamasıdır; score_slice_v2 ile")
    print("birebir değildir. Sayılar gerçek veriden ve gerçek fee'lerden gelir.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="sentetik veri (pipeline testi)")
    ap.add_argument("--months", type=float, default=3.0)
    args = ap.parse_args()

    all_trades = []
    for idx, sym in enumerate(COINS):
        try:
            if args.demo:
                df = demo_klines(sym, args.months, seed=idx)
                src = "DEMO"
            else:
                df = fetch_klines(sym, INTERVAL, args.months)
                src = "BINANCE"
        except Exception as e:
            print(f"[{sym}] HATA: {e}")
            print("  -> Ağ engelliyse bu makinede çalıştır ya da --demo dene.")
            continue
        df = add_indicators(df)
        sigs = find_signals(df)
        print(f"[{src}] {sym}: {len(df)} mum, {len(sigs)} dolan işlem")
        all_trades.extend(sigs)

    report(all_trades)


if __name__ == "__main__":
    main()
