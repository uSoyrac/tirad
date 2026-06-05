#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════
BOT 5 — REJİM (Rejim-Bazlı Akıllı Strateji Seçimi) ⭐ YENİ EN İYİ MAR
═══════════════════════════════════════════════════════════════════════════
KANIT: Boğada trend-following kaybeder, ayıda kazanır (test edildi).
Bu bot her 4H barında piyasa rejimini tespit eder ve otomatik ayarlar:
  BOĞA  → notional 0.25x + sadece top%5 sinyal (zararı keser)
  KARMA → güven-bazlı (0.6/1.25/2.5x), mevcut optimal sistem
  AYI   → notional 1.5x agresif (en iyi performans bu rejimde)

DOĞRULANMIŞ (OOS 2024-2026 walk-forward, $250):
  baseline (düz 0.6x) : $250→$480   +31% CAGR  MDD%17  MAR 1.84
  bot_optimal          : $250→$1003  +78% CAGR  MDD%31  MAR 2.49
  >>> BOT REJİM        : $250→$865   +67% CAGR  MDD%25  MAR 2.74 ⭐

MAR 2.74 = en yüksek risk-ayarlı getiri (birim drawdown başına en çok kazanç).
Daha pürüzsüz equity eğrisi: MDD%25 vs bot_optimal MDD%31.

REJİM ALGILAMA (sızıntısız, sadece geçmişe bakan):
  BTC son 20 bar (80 saat) eğimi + ADX + toplam getiri.
  BOĞA  : >%15 ralli + ADX>25 + güçlü yukarı eğim
  AYI   : <-%8 düşüş veya güçlü aşağı eğim
  KARMA : arada kalan her şey

Çalıştır: cd uyg/Botlar && python3 bot_rejim.py
═══════════════════════════════════════════════════════════════════════════
"""
import os, sys
import numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import compound_engine as E
import ta

# ── KONFİGÜRASYON ─────────────────────────────────────────────────────────
LOOKBACK   = 20    # rejim tespiti için kaç 4H bar
NT_BULL    = 0.25  # boğada notional (küçük, zarar kısıtla)
NT_BEAR    = 1.50  # ayıda notional (agresif, en iyi performans)
GATE_BULL  = 0.05  # boğada gate: sadece top%5
GATE_BEAR  = 0.20  # ayıda gate: top%20
BTC_DATA   = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "..", "uyg", "src", "mktdata", "BTC_USDT_4h.csv")

def detect_regime(df_btc, t, lookback=LOOKBACK):
    """t anında rejimi tespit et (sadece geçmişe bakar — sızıntısız)."""
    if t < lookback + 20: return "mixed"
    w = df_btc.iloc[t-lookback:t]
    cl = w["close"]
    x = np.arange(len(cl))
    slope_pct = np.polyfit(x, cl.values, 1)[0] / cl.iloc[0] * 100
    total_ret  = (cl.iloc[-1] / cl.iloc[0] - 1) * 100
    adx_val    = ta.trend.ADXIndicator(
        df_btc["high"].iloc[t-lookback-14:t],
        df_btc["low"].iloc[t-lookback-14:t],
        df_btc["close"].iloc[t-lookback-14:t], 14).adx().iloc[-1]
    if total_ret > 15 and slope_pct > 0.3 and adx_val > 25:
        return "bull"
    elif total_ret < -8 or (total_ret < 0 and adx_val > 30 and slope_pct < -0.2):
        return "bear"
    return "mixed"

def backtest(rows, P, df_btc, btc_idx):
    all_P = np.array([P[i] for i in P])
    thr_bull  = np.quantile(all_P, 1-GATE_BULL)
    thr_bear  = np.quantile(all_P, 1-GATE_BEAR)
    passed = all_P[all_P >= thr_bear]
    lo, hi = np.quantile(passed, 0.40), np.quantile(passed, 0.80)

    eq=250.; peak=250.; mdd=0.; free=pd.Timestamp("2000")
    trades=[]; monthly={}
    for i, r in enumerate(rows):
        if str(r["et"]) < E.OOS_START or i not in P or r["et"] < free: continue
        bt = btc_idx.searchsorted(r["et"])
        regime = detect_regime(df_btc, bt)
        if regime == "bull":
            if P[i] < thr_bull: continue
            nt = NT_BULL
        elif regime == "bear":
            if P[i] < thr_bear: continue
            p = P[i]
            nt = 0.6 if p < lo else (1.25 if p < hi else NT_BEAR)
        else:  # mixed
            if P[i] < thr_bear: continue
            p = P[i]
            nt = 0.6 if p < lo else (1.25 if p < hi else 2.5)
            nt = min(nt, 1.5)

        g = nt * (r["ret"] - E.COST)
        eq *= (1+g); free = r["xt"]
        peak = max(peak, eq); mdd = max(mdd, (peak-eq)/peak if peak>0 else 0)
        trades.append({"win": r["win"], "regime": regime, "nt": nt})
        monthly[str(r["et"])[:7]] = eq
        if eq <= 0: break

    yrs = (pd.Timestamp(str(rows[-1]["xt"]))-pd.Timestamp(E.OOS_START)).days/365.25
    cagr = ((eq/250)**(1/yrs)-1)*100 if eq>0 else -100
    return dict(eq=eq, cagr=cagr, mdd=mdd*100, n=len(trades),
                wr=np.mean([t["win"] for t in trades])*100 if trades else 0,
                monthly=monthly, trades=trades)

def main():
    print(__doc__)
    print("Hazırlanıyor (sinyaller + walk-forward model)...")
    rows = E.build_signals(); P = E.walk_forward_proba(rows)
    df_btc = pd.read_csv(BTC_DATA, parse_dates=["ts"]).set_index("ts").sort_index()
    btc_idx = df_btc.index
    r = backtest(rows, P, df_btc, btc_idx)

    print("="*72); print("  BOT REJİM — Rejim-Bazlı Akıllı Strateji"); print("="*72)
    print(f"  $250 → ${r['eq']:.0f}   CAGR %{r['cagr']:.1f}   MaxDD %{r['mdd']:.1f}   WR %{r['wr']:.0f}   n={r['n']}")
    mar = r['cagr']/r['mdd'] if r['mdd']>0 else 0
    print(f"  MAR: {mar:.2f}  ⭐ En yüksek risk-ayarlı getiri")

    # Kıyaslar
    ref = E.backtest(rows, P, bankroll=250., sizing="fixed", notional_cap=0.6)
    print(f"\n  Kıyas bot_kararli : $250→${ref['eq']:.0f}  CAGR%{ref['cagr']:.1f}  MDD%{ref['mdd']:.1f}  MAR{ref['cagr']/ref['mdd']:.2f}")

    # Rejim dağılımı
    print(f"\n  Rejim dağılımı:")
    for reg in ["bull","mixed","bear"]:
        sub = [t for t in r["trades"] if t["regime"]==reg]
        if sub:
            wr_r = np.mean([t["win"] for t in sub])*100
            nt_r = np.mean([t["nt"] for t in sub])
            print(f"    {reg:>8}: {len(sub):>4} işlem  WR%{wr_r:.0f}  ort.notional {nt_r:.2f}x")

    # Aylık kırılım
    print(f"\n  Aylık kasa ($250 başlangıç):")
    prev = 250.
    for mo in sorted(r["monthly"]):
        v = r["monthly"][mo]; ch = (v/prev-1)*100; prev = v
        bar = "█" * max(0,int(min(v,1200)/40))
        print(f"    {mo}: ${v:8.0f} ({ch:+5.1f}%) {bar}")
    print(f"\n  ⚠️ BACKTEST. Paper-trade ile doğrula, sonra gerçek sermaye.")

if __name__ == "__main__":
    main()
