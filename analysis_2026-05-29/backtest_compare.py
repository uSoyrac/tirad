"""
backtest_compare.py
===================
AYNI sinyal motoru (repo_signals.s3_signal — rapordaki S3), AYNI veri,
AYNI SL/TP/risk kuralları. TEK FARK: işlem doldurma (fill) ve maliyet katmanı.

  MODE = "buggy_repo":
      Rapor/repo metodolojisi. Sinyal bar'ında pozisyon ANINDA Order Block
      ORTA NOKTASINDA açılır. Bu fiyat seviyesi GEÇMİŞTE kalmış, mevcut
      piyasa fiyatının ALTINDADIR (long için). Doldurma kontrolü YOK,
      komisyon/slipaj YOK. -> look-ahead / fill-assumption hatası.

  MODE = "honest_limit":
      OB orta noktasına LİMİT emri konur. Emir, ANCAK gelecekteki bir mum
      gerçekten o seviyeye GERİ DÖNERSE dolar (bar.low <= ob_mid). Fiyat
      geri dönmezse işlem AÇILMAZ. Komisyon+slipaj uygulanır.

  MODE = "honest_market":
      Sinyal sonrası bir SONRAKİ mumun AÇILIŞINDA piyasa emriyle girilir
      (gerçekçi alternatif). Komisyon+slipaj uygulanır.

Tüm modlarda: bar-içi hem SL hem TP değerse, KÖTÜMSER varsayım (önce SL).
"""
import numpy as np
import pandas as pd
from repo_signals import s3_signal, atr_fn, ema

# ── Rapor §3.2 parametreleri ────────────────────────────────────
RISK_PCT   = 0.02      # işlem başına %2 risk (her iki motorda AYNI — karşılaştırma adil)
ATR_MULT   = 1.5       # SL = entry -/+ ATR*1.5
SL_MIN     = 0.005     # sl mesafesi guard [%0.5, %10]
SL_MAX     = 0.10
TP_R       = [1.5, 2.5, 4.0]      # R cinsinden TP seviyeleri
TP_CLOSE   = [0.40, 0.35, 0.25]   # her TP'de kapatılan oran
LEV_CAP    = 5.0
FEE_RT     = 0.0018    # round-trip komisyon+slipaj (%0.18) — raporun iddia ettiği oran
EXPIRY     = 60        # limit emrin geçerlilik süresi (bar)
WARMUP     = 220       # EMA200 + OB için yeterli geçmiş


def _simulate_one(df, i, direction, ob, atr_val, mode):
    """
    Tek bir işlemi simüle eder. Döner: dict(filled, r_mult, exit_bar) ya da None.
    r_mult = işlemin R cinsinden net sonucu (komisyon dahil), risk birimi = 1R.
    """
    n = len(df)
    high = df["high"].values; low = df["low"].values; opn = df["open"].values
    sign = 1 if direction == "LONG" else -1

    # ── Giriş fiyatı ve fill ────────────────────────────────────
    if mode == "buggy_repo":
        entry = ob["mid"]
        entry_bar = i                      # ANINDA, kontrol yok (HATA)
        fill_fee = 0.0
    elif mode == "honest_market":
        if i >= n: return None
        entry = opn[i]                     # sonraki mum açılışı
        entry_bar = i
        fill_fee = FEE_RT / 2
    elif mode == "honest_limit":
        entry = ob["mid"]
        entry_bar = None
        for j in range(i, min(i + EXPIRY, n)):
            if direction == "LONG" and low[j] <= entry:   # geri döndü mü?
                entry_bar = j; break
            if direction == "SHORT" and high[j] >= entry:
                entry_bar = j; break
        if entry_bar is None:
            return {"filled": False}        # fiyat hiç geri dönmedi -> işlem yok
        fill_fee = FEE_RT / 2
    else:
        raise ValueError(mode)

    # ── SL / TP seviyeleri (rapor §3.2) ─────────────────────────
    sl = entry - sign * ATR_MULT * atr_val
    sl_dist = abs(entry - sl) / entry
    sl_dist = min(max(sl_dist, SL_MIN), SL_MAX)
    sl = entry - sign * sl_dist * entry
    R = abs(entry - sl)
    tps = [entry + sign * r * R for r in TP_R]

    # ── İleri simülasyon (kötümser: önce SL) ────────────────────
    remaining = 1.0
    realized_R = 0.0
    sl_cur = sl
    moved_be = False
    close_fee_R = fill_fee / sl_dist        # giriş komisyonu R cinsinden
    tp_idx = 0
    start = entry_bar if mode != "honest_market" else entry_bar
    # buggy/honest_limit: aynı barı da kontrol et; market: giriş barından sonrası
    rng_start = entry_bar
    for j in range(rng_start, n):
        hi = high[j]; lo = low[j]
        # SL (önce — kötümser)
        hit_sl = (lo <= sl_cur) if direction == "LONG" else (hi >= sl_cur)
        if hit_sl:
            loss_R = (sl_cur - entry) / R * sign     # be -> 0, gerçek SL -> -1
            realized_R += remaining * loss_R
            close_fee_R += (FEE_RT / 2) * remaining / sl_dist
            return {"filled": True, "r_mult": realized_R - close_fee_R, "exit_bar": j}
        # TP'ler
        while tp_idx < len(tps):
            tp = tps[tp_idx]
            hit_tp = (hi >= tp) if direction == "LONG" else (lo <= tp)
            if not hit_tp:
                break
            part = TP_CLOSE[tp_idx]
            realized_R += part * TP_R[tp_idx]
            close_fee_R += (FEE_RT / 2) * part / sl_dist
            remaining -= part
            if tp_idx == 0 and not moved_be:
                sl_cur = entry; moved_be = True       # TP1 -> SL breakeven
            tp_idx += 1
            if remaining <= 1e-9:
                return {"filled": True, "r_mult": realized_R - close_fee_R, "exit_bar": j}
    # veri bitti — kalan pozisyonu son kapanışta kapat
    last = df["close"].values[-1]
    realized_R += remaining * (last - entry) / R * sign
    close_fee_R += (FEE_RT / 2) * remaining / sl_dist
    return {"filled": True, "r_mult": realized_R - close_fee_R, "exit_bar": n - 1}


def run(df, mode, risk_pct=RISK_PCT):
    """Walk-forward backtest. Döner: dict(metrikler)."""
    n = len(df)
    atr_series = atr_fn(df).values
    equity = 1000.0
    eq_curve = [equity]
    trades = []           # r_mult listesi
    no_fill = 0
    i = WARMUP
    while i < n - 1:
        df_slice = df.iloc[:i]                 # SADECE kapanmış mumlar
        direction, ob = s3_signal(df_slice)
        if direction is None:
            i += 1; continue
        atr_val = atr_series[i - 1]
        if not np.isfinite(atr_val) or atr_val <= 0:
            i += 1; continue
        res = _simulate_one(df, i, direction, ob, atr_val, mode)
        if res is None:
            i += 1; continue
        if not res.get("filled", False):
            no_fill += 1
            i += 1
            continue
        r = res["r_mult"]
        # sabit-fraksiyonel: 1R = equity*risk_pct (kaldıraç capi liq yaratmıyor, rapor da öyle)
        equity += equity * risk_pct * r
        equity = max(equity, 1e-6)
        eq_curve.append(equity)
        trades.append(r)
        i = max(res["exit_bar"] + 1, i + 1)    # işlem kapanınca devam

    trades = np.array(trades)
    eq = np.array(eq_curve)
    if len(trades) == 0:
        return {"mode": mode, "trades": 0, "win_rate": float("nan"),
                "final": equity, "mult": equity / 1000, "max_dd": 0.0,
                "no_fill": no_fill, "avg_R": float("nan"), "pf": float("nan")}
    wins = trades[trades > 0]
    losses = trades[trades <= 0]
    win_rate = len(wins) / len(trades)
    peak = np.maximum.accumulate(eq)
    max_dd = float(np.max((peak - eq) / peak)) * 100
    pf = wins.sum() / (abs(losses.sum()) + 1e-12)
    return {"mode": mode, "trades": int(len(trades)), "win_rate": win_rate,
            "final": equity, "mult": equity / 1000, "max_dd": max_dd,
            "no_fill": no_fill, "avg_R": float(trades.mean()), "pf": pf,
            "eq_curve": eq}


if __name__ == "__main__":
    from data_gen import regime
    print(f"{'REJIM':10s} {'MOD':14s} {'işlem':>6s} {'fill_yok':>8s} "
          f"{'WR':>6s} {'ortR':>6s} {'PF':>6s} {'çarpan':>12s} {'maxDD':>7s}")
    print("─" * 90)
    for rg in ["realistic", "bull", "bear", "chop"]:
        df = regime(rg, seed=42)
        for mode in ["buggy_repo", "honest_limit", "honest_market"]:
            r = run(df, mode)
            wr = f"{r['win_rate']*100:.0f}%" if r["trades"] else "—"
            ar = f"{r['avg_R']:+.2f}" if r["trades"] else "—"
            pf = f"{r['pf']:.2f}" if r["trades"] else "—"
            print(f"{rg:10s} {mode:14s} {r['trades']:6d} {r['no_fill']:8d} "
                  f"{wr:>6s} {ar:>6s} {pf:>6s} {r['mult']:>11.1f}x {r['max_dd']:>6.1f}%")
        print()
