"""
signal_lab.py
=============
Repo'nun GERÇEK SMC fonksiyonlarından (order block, FVG, likidite sweep,
displacement, OTE, market structure, EMA trend) üretilen long+short sinyal
kombinasyonlarını, REPAINTING/LOOK-AHEAD OLMADAN, OUT-OF-SAMPLE değerlendirir.

Metodoloji (MIT-quant standardı):
  • Karar bar t'nin KAPANIŞINDA, sadece df[:t+1] (kapanmış mumlar) ile verilir.
  • İşleme bir SONRAKİ mumun (t+1) AÇILIŞINDA girilir (market). -> look-ahead yok.
  • Komisyon+slipaj her iki tarafa uygulanır.
  • SL = ATR×1.5 (1R). TP = tp_R × R. max_hold sonra zaman-stop.
  • Train = ilk %60, Test (OOS) = son %40. Sıralama OOS expectancy'ye göre.
  • Negatif kontrol: sinyaller karıştırılınca (shuffle) edge kaybolmalı.

NOT: Bu ortamda borsalar allowlist dışı; canlı ETH verisi çekilemiyor.
'data_eth_1h.csv' varsa o KULLANILIR (kendi gerçek verinizi koyun);
yoksa yüksek-doğrulukta sentetik ETH 1h (~4 ay) üretilir (açıkça etiketli).
"""
import warnings; warnings.filterwarnings("ignore")
import os, sys
import numpy as np
import pandas as pd
from repo_signals import (ema, atr_fn, order_blocks, fair_value_gaps,
                          liquidity_map, displacement, optimal_trade_entry,
                          market_structure)

FEE_SIDE = 0.0009     # %0.09/taraf  (round-trip %0.18 — komisyon+slipaj)
FUNDING_8H = 0.0001   # perpetual funding ~%0.01/8h (long öder varsayımı — kötümser)
ATR_MULT = 1.5
WARMUP   = 215
MAX_HOLD = 48         # zaman-stop (saat)
CACHE    = "features_cache.npz"


# ════════════════════════════════════════════════════════════════
# 1) VERİ
# ════════════════════════════════════════════════════════════════
def load_data(months=4):
    if os.path.exists("data_eth_1h.csv"):
        df = pd.read_csv("data_eth_1h.csv")
        cols = {c.lower(): c for c in df.columns}
        df.columns = [c.lower() for c in df.columns]
        if "timestamp" in df: df.index = pd.to_datetime(df["timestamp"])
        df = df[["open", "high", "low", "close", "volume"]].astype(float)
        print(f"[VERİ] GERÇEK veri: data_eth_1h.csv  ({len(df)} bar)")
        return df, "REEL"
    from data_gen import gen_ohlcv
    n = months * 30 * 24
    df = gen_ohlcv(n_bars=n, mu_annual=0.25, sigma_annual=0.80,
                   start_price=3000.0, seed=2026)
    print(f"[VERİ] SENTETİK ETH-benzeri 1h, ~{months} ay ({len(df)} bar)  "
          f"[borsalar allowlist dışı; gerçek veri için data_eth_1h.csv koyun]")
    return df, "SENTETİK"


# ════════════════════════════════════════════════════════════════
# 2) WALK-FORWARD FEATURE MATRİSİ (cache'li)
# ════════════════════════════════════════════════════════════════
FEAT_COLS = ["ema_bull", "ema_bear", "ms_bull", "ms_bear", "bos_bull", "bos_bear",
             "bull_ob", "bear_ob", "bull_fvg", "bear_fvg", "sweep_up", "sweep_down",
             "disp_up", "disp_down", "ote_bull", "ote_bear", "rsi_os", "rsi_ob"]


def build_features(df, tag):
    key = f"{tag}_{len(df)}"
    if os.path.exists(CACHE):
        z = np.load(CACHE, allow_pickle=True)
        if str(z["key"]) == key:
            print("[FEATURE] cache'ten yüklendi")
            return pd.DataFrame(z["F"], columns=FEAT_COLS), z["atr"], z["open_"], z["high_"], z["low_"], z["close_"]

    n = len(df)
    close = df["close"]; openv = df["open"].values
    high = df["high"].values; low = df["low"].values
    # causal indikatörler (vektörize, look-ahead yok — değer i-1'de okunur)
    ema200 = ema(close, 200).values
    atr = atr_fn(df, 14).values
    d = close.diff(); up = d.clip(lower=0).rolling(14).mean(); dn = (-d.clip(upper=0)).rolling(14).mean()
    rsi = (100 - 100 / (1 + up / dn.replace(0, np.nan))).values

    F = np.zeros((n, len(FEAT_COLS)), dtype=np.float32)
    print(f"[FEATURE] walk-forward hesaplama ({n} bar)...", flush=True)
    for i in range(WARMUP, n):
        sl = df.iloc[:i]                       # SADECE kapanmış mumlar (bar i-1'e kadar)
        c1 = close.iloc[i - 1]
        e2 = ema200[i - 1]
        row = [c1 > e2, c1 < e2]               # ema_bull/bear
        ms = market_structure(sl.iloc[-250:])  # yapı yereldir; perf için son 250
        row += [ms["trend"] == "BULLISH", ms["trend"] == "BEARISH",
                ms["bos_bull"], ms["bos_bear"]]
        bo, beo = order_blocks(sl)
        row += [len(bo) > 0, len(beo) > 0]
        bf, bef = fair_value_gaps(sl)
        row += [len(bf) > 0, len(bef) > 0]
        su, sd = liquidity_map(sl)
        row += [su, sd]
        du, dd = displacement(sl)
        row += [du, dd]
        ob_, oe_ = optimal_trade_entry(sl)
        row += [ob_, oe_]
        r = rsi[i - 1]
        row += [r < 35 if np.isfinite(r) else False, r > 65 if np.isfinite(r) else False]
        F[i] = np.array(row, dtype=np.float32)
        if i % 500 == 0:
            sys.stdout.write(f"\r  {i}/{n}"); sys.stdout.flush()
    print("\r[FEATURE] tamam            ")
    np.savez(CACHE, key=key, F=F, atr=atr, open_=openv, high_=high, low_=low, close_=close.values)
    return pd.DataFrame(F, columns=FEAT_COLS), atr, openv, high, low, close.values


# ════════════════════════════════════════════════════════════════
# 3) DÜRÜST BACKTEST (market giriş, komisyon, ATR SL, R-TP)
# ════════════════════════════════════════════════════════════════
def backtest(long_sig, short_sig, atr, op, hi, lo, cl, tp_R=2.0, lo_idx=0, hi_idx=None):
    """Tek pozisyon. R cinsinden net sonuç listesi döner (komisyon dahil)."""
    n = len(cl)
    if hi_idx is None: hi_idx = n
    trades = []
    i = max(WARMUP, lo_idx)
    while i < min(n - 1, hi_idx):
        go_long = long_sig[i]; go_short = short_sig[i]
        if not (go_long or go_short):
            i += 1; continue
        a = atr[i - 1]
        if not np.isfinite(a) or a <= 0:
            i += 1; continue
        sign = 1 if go_long else -1
        entry = op[i]                          # SONRAKİ mum açılışı (look-ahead yok)
        R = ATR_MULT * a
        sl = entry - sign * R
        tp = entry + sign * tp_R * R
        fee_R = FEE_SIDE / (R / entry)         # komisyon R cinsinden (giriş)
        exit_R = None
        for j in range(i, min(i + MAX_HOLD, n)):
            # kötümser: önce SL
            if (lo[j] <= sl) if sign == 1 else (hi[j] >= sl):
                exit_R = -1.0; ej = j; break
            if (hi[j] >= tp) if sign == 1 else (lo[j] <= tp):
                exit_R = tp_R; ej = j; break
        if exit_R is None:                     # zaman-stop: kapanışta çık
            ej = min(i + MAX_HOLD, n - 1)
            exit_R = (cl[ej] - entry) / R * sign
        hours = max(ej - i, 1)
        funding_R = (FUNDING_8H * hours / 8.0) / (R / entry)   # tutulan süre × funding
        net = exit_R - 2 * fee_R - funding_R   # komisyon(2 taraf) + funding
        trades.append(net)
        i = ej + 1                             # pozisyon kapanınca devam
    return np.array(trades)


def stats(tr):
    if len(tr) == 0:
        return dict(n=0, wr=np.nan, exp=np.nan, pf=np.nan)
    w = tr[tr > 0]; l = tr[tr <= 0]
    return dict(n=len(tr), wr=len(w) / len(tr), exp=tr.mean(),
                pf=w.sum() / (abs(l.sum()) + 1e-12))


# ════════════════════════════════════════════════════════════════
# 4) SİNYAL KOMBİNASYONLARI (long + short, repo SMC'sinden)
# ════════════════════════════════════════════════════════════════
def make_rules(F):
    f = {c: F[c].values.astype(bool) for c in FEAT_COLS}
    Z = np.zeros(len(F), dtype=bool)
    rules = {}
    # S3 (rapor): EMA trend + OB
    rules["S3: EMA+OB"] = (f["ema_bull"] & f["bull_ob"], f["ema_bear"] & f["bear_ob"])
    # Saf OB
    rules["Saf OB"] = (f["bull_ob"], f["bear_ob"])
    # Trend + FVG
    rules["EMA+FVG"] = (f["ema_bull"] & f["bull_fvg"], f["ema_bear"] & f["bear_fvg"])
    # Trend + OB + FVG
    rules["EMA+OB+FVG"] = (f["ema_bull"] & f["bull_ob"] & f["bull_fvg"],
                           f["ema_bear"] & f["bear_ob"] & f["bear_fvg"])
    # Sweep + trend (likidite avı sonrası dönüş)
    rules["EMA+Sweep"] = (f["ema_bull"] & f["sweep_down"], f["ema_bear"] & f["sweep_up"])
    # Displacement + trend
    rules["EMA+Disp"] = (f["ema_bull"] & f["disp_up"], f["ema_bear"] & f["disp_down"])
    # OTE + trend
    rules["EMA+OTE"] = (f["ema_bull"] & f["ote_bull"], f["ema_bear"] & f["ote_bear"])
    # MarketStructure + OB
    rules["MS+OB"] = (f["ms_bull"] & f["bull_ob"], f["ms_bear"] & f["bear_ob"])
    # BOS + OB (kırılım + OB)
    rules["BOS+OB"] = (f["bos_bull"] & f["bull_ob"], f["bos_bear"] & f["bear_ob"])
    # Sweep + OB (klasik ICT setup)
    rules["Sweep+OB"] = (f["sweep_down"] & f["bull_ob"], f["sweep_up"] & f["bear_ob"])
    # RSI + trend (klasik mean-rev)
    rules["EMA+RSI"] = (f["ema_bull"] & f["rsi_os"], f["ema_bear"] & f["rsi_ob"])
    # Çoklu konfluens (en sıkı — en az işlem)
    rules["Konfluens(OB+FVG+Sweep)"] = (
        f["ema_bull"] & f["bull_ob"] & (f["bull_fvg"] | f["sweep_down"]),
        f["ema_bear"] & f["bear_ob"] & (f["bear_fvg"] | f["sweep_up"]))
    return rules


# ════════════════════════════════════════════════════════════════
def main():
    df, tag = load_data(months=4)
    F, atr, op, hi, lo, cl = build_features(df, tag)
    n = len(cl); split = int(n * 0.60)
    rules = make_rules(F)

    print("\n" + "═" * 108)
    print(f"  SİNYAL ARAMA — {tag} ETH 1h, {n} bar | TP=2R, SL=1.5×ATR | maliyet: komisyon+slipaj %0.18 r/t + funding")
    print(f"  Tüm expectancy değerleri TÜM MALİYETLER SONRASI (net). Train=ilk %60, Test=son %40 (OOS)")
    print("═" * 108)
    hdr = (f"{'KURAL':26s} | {'TÜM n':>6s} {'WR':>5s} {'netR':>6s} || "
           f"{'TRAIN n':>8s} {'netR':>7s} || {'TEST(OOS) n':>11s} {'WR':>5s} {'netR':>7s} {'PF':>5s}")
    print(hdr); print("─" * 108)

    results = []
    for name, (ls, ss) in rules.items():
        sa = stats(backtest(ls, ss, atr, op, hi, lo, cl))
        st = stats(backtest(ls, ss, atr, op, hi, lo, cl, lo_idx=WARMUP, hi_idx=split))
        se = stats(backtest(ls, ss, atr, op, hi, lo, cl, lo_idx=split, hi_idx=n))
        results.append((name, sa, st, se))
        print(f"{name:26s} | {sa['n']:6d} {sa['wr']*100:4.0f}% {sa['exp']:+6.2f} || "
              f"{st['n']:8d} {st['exp']:+7.2f} || {se['n']:11d} {se['wr']*100:4.0f}% "
              f"{se['exp']:+7.2f} {se['pf']:5.2f}")

    # ════════════════════════════════════════════════════════════
    #  4-KAPILI EDGE BARİYERİ
    #   (a) TRAIN net expR > 0   (b) TEST net expR > 0
    #   (d) net = tüm maliyetler (komisyon+slipaj+funding) sonrası -> zaten net
    #   (c) 300-shuffle OOS dağılımını p<0.05 ile geçmeli
    #  (c) yalnızca (a)&(b)&yeterli işlem geçen kurallar için hesaplanır.
    # ════════════════════════════════════════════════════════════
    print("\n" + "═" * 108)
    print("  4-KAPILI EDGE BARİYERİ  [a: train>0 | b: test>0 | c: shuffle p<0.05 | d: tüm maliyetler sonrası>0]")
    print("═" * 108)
    rng = np.random.default_rng(0)
    candidates = []
    for name, sa, st, se in results:
        ga = st["n"] >= 10 and st["exp"] > 0
        gb = se["n"] >= 10 and se["exp"] > 0
        gd = True                                  # netR zaten tüm maliyetleri içerir
        pval = np.nan; gc = False
        if ga and gb:                              # shuffle yalnızca a&b geçenlere (pahalı)
            ls, ss = rules[name]
            sh = []
            for _ in range(300):
                perm = rng.permutation(len(ls))
                e = stats(backtest(ls[perm], ss[perm], atr, op, hi, lo, cl,
                                   lo_idx=split, hi_idx=n))["exp"]
                if np.isfinite(e): sh.append(e)
            sh = np.array(sh)
            pval = (sh >= se["exp"]).mean()
            gc = pval < 0.05
        passed = ga and gb and gc and gd
        if passed: candidates.append((name, se, pval))
        mark = lambda b: "✓" if b else "✗"
        pv = f"p={pval:.3f}" if np.isfinite(pval) else "p=  — "
        print(f"  {name:26s}  a:{mark(ga)} b:{mark(gb)} c:{mark(gc)}({pv}) d:{mark(gd)}  "
              f"-> {'✅ EDGE ADAYI' if passed else '❌ elendi'}")

    print("\n" + "═" * 108)
    if candidates:
        print("  ✅ DÖRT KAPIYI DA GEÇEN EDGE ADAYI(LARI):")
        for name, se, pval in sorted(candidates, key=lambda c: c[1]["exp"], reverse=True):
            print(f"     • {name}: OOS netR={se['exp']:+.3f}, n={se['n']}, "
                  f"WR=%{se['wr']*100:.0f}, shuffle p={pval:.3f}")
        print("     -> Bu aday(lar) walk-forward'ın FARKLI dönemlerinde + farklı")
        print("        coinlerde de doğrulanmalı; sonra paper-trade.")
    else:
        print("  ❌ HİÇBİR KURAL DÖRT KAPIYI BİRDEN GEÇMEDİ -> doğrulanmış edge YOK.")
        print("     Bu bir BAŞARISIZLIK DEĞİL: gerçek paranı sahte bir sisteme")
        print("     yatırmaktan korur. Edge'i sinyalde aramaya devam (çoklu-TF,")
        print("     funding/CVD filtresi, rejim filtresi, asimetrik R:R).")
    print("═" * 108)
    print(f"  [VERİ KAYNAĞI: {tag}]  " +
          ("Bu GERÇEK veridir." if tag == "REEL" else
           "Bu SENTETİK kuru-çalıştırmadır; gerçek karar için fetch_real_data.py ile REEL veride çalıştırın."))
    print("═" * 108)
    return df, tag, F, results


if __name__ == "__main__":
    main()
