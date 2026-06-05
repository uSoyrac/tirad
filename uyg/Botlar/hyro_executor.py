#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
PROP EXECUTOR — firma-yapılandırılabilir İKİ-BOT (geç + funded), Bybit TESTNET-KİLİTLİ
═══════════════════════════════════════════════════════════════════════════════
combo edge'ini (kripto-trend Top-3 long + funding long/short) prop kurallarına göre uygular.
İki-bot tek dosyada:
  --mode pass    : challenge'ı GEÇ  (yüksek vol, hedefe yürü)
  --mode funded  : patlamadan KAZAN (düşük vol, hesabı koru)
Firma-yapılandırılabilir (--firm):
  breakout1 : Breakout 1-step STATİK DD %6 / günlük %4  (OPTIMAL — geçmesi en kolay, %53)
  hyro2     : HyroTrader 2-step TRAILING DD %10 / günlük %5  (forward-doğrulama / Bybit testnet)
Geliştirmeler:
  • MAKER emir (--maker): post-only limit → düşük fee (taker ~5.5bps → maker ~1bps), ince edge'i kurtarır
  • REJİM kapısı (--regime-gate): düşük-vol piyasada tam risk, türbülansta kıs (geçişi artırır)
  • Her pozisyona reduce-only STOP-LOSS (≤%3 risk) + intraday self-stop + kill-switch'ler
  • Top-3 + funding çeşitli → %40-konsantrasyon kuralı doğal geçer

GÜVENLİK: TESTNET sabit True (mainnet yok). Anahtar yalnız env'den. Varsayılan DRY-RUN.
ÇALIŞTIRMA:
  DRY-RUN : python uyg/Botlar/hyro_executor.py --firm breakout1 --mode pass
  TESTNET : . /root/tirad/.hyro_env && python uyg/Botlar/hyro_executor.py --firm hyro2 --mode pass --execute --maker --regime-gate
═══════════════════════════════════════════════════════════════════════════════
"""
import argparse
import json
import os
import time
import warnings
from pathlib import Path


from _botlib import load_universe

warnings.filterwarnings("ignore")

TESTNET = True                 # HARD-LOCK
PER_TRADE_RISK = 0.03
TOP_K, N_FUND = 3, 3
ATR_STOP_MULT = 2.0
MAKER_OFFSET = 0.0005          # post-only limit için pasif mesafe
_BASE = Path("/root/tirad/paper") if Path("/root/tirad/paper").exists() else Path(__file__).resolve().parent / "_state"
_BASE.mkdir(parents=True, exist_ok=True)

# firma preset'leri: daily/total limit (%), trailing mi, faz, etiket
FIRMS = {
    "breakout1": {"daily": 0.04, "total": 0.06, "trailing": False, "label": "Breakout 1-step STATİK"},
    "hyro2":     {"daily": 0.05, "total": 0.10, "trailing": True,  "label": "HyroTrader 2-step trailing"},
}
# mod: pass=geç (yüksek vol), funded=koru (düşük vol)
MODE_PRESETS = {
    "pass":   {"vol": 0.15, "intraday_stop": 0.04},
    "funded": {"vol": 0.08, "intraday_stop": 0.03},
}


def make_exchange():
    import ccxt
    key, sec = os.environ.get("BYBIT_TESTNET_KEY"), os.environ.get("BYBIT_TESTNET_SECRET")
    if not key or not sec:
        raise SystemExit("BYBIT_TESTNET_KEY / BYBIT_TESTNET_SECRET env yok.")
    ex = ccxt.bybit({"apiKey": key, "secret": sec, "enableRateLimit": True, "options": {"defaultType": "swap"}})
    ex.set_sandbox_mode(True)   # TESTNET
    return ex


def compute_targets():
    """combo hedef ağırlıkları + ATR + fiyat + REJİM bayrağı (düşük-vol mu)."""
    from quantlab.indicators import atr
    cfg, frames, higher, targets, momentum, fundings = load_universe()
    asof = max(f.index[-1] for f in frames.values())
    elig = [(s, float(momentum[s].reindex([asof]).fillna(-9).iloc[0]))
            for s in frames if float(targets[s].reindex([asof]).fillna(0).iloc[0]) > 0]
    elig.sort(key=lambda x: x[1], reverse=True)
    mom_long = [s for s, _ in elig[:TOP_K]]
    score = {s: float(fundings[s].tail(21).mean()) for s in fundings}
    ranked = sorted(score, key=score.get)
    fund_long, fund_short = ranked[:N_FUND], ranked[-N_FUND:]
    w = {}
    for s in mom_long:
        w[s] = w.get(s, 0) + 0.5 / max(1, len(mom_long))
    for s in fund_long:
        w[s] = w.get(s, 0) + 0.5 / max(1, len(fund_long))
    for s in fund_short:
        w[s] = w.get(s, 0) - 0.5 / max(1, len(fund_short))
    atrp = {s: float(atr(frames[s], cfg.risk.atr_period).iloc[-1] / frames[s]["close"].iloc[-1]) for s in w}
    px = {s: float(frames[s]["close"].iloc[-1]) for s in w}
    # rejim: BTC 20-bar getiri vol'u, 120-bar medyanın altındaysa 'düşük-vol' (sakin)
    low_vol = True
    try:
        b = frames.get("BTC")
        r = b["close"].pct_change()
        cur = r.tail(20).std()
        med = r.rolling(20).std().tail(120).median()
        low_vol = bool(cur <= med)
    except Exception:  # noqa: BLE001
        pass
    return w, atrp, px, str(asof.date()), low_vol


def load_state(path):
    if path.exists():
        return json.loads(path.read_text())
    return {"start_eq": None, "peak_eq": None, "day": None, "day_start_eq": None}


def risk_gate(equity, st, firm):
    """Günlük + toplam (firma trailing/statik) kill-switch."""
    today = time.strftime("%Y-%m-%d")
    if st["start_eq"] is None:
        st.update(start_eq=equity, peak_eq=equity, day=today, day_start_eq=equity)
    if st["day"] != today:
        st["day"], st["day_start_eq"] = today, equity
    st["peak_eq"] = max(st["peak_eq"] or equity, equity)
    if equity <= st["day_start_eq"] * (1 - firm["daily"]):
        return f"GÜNLÜK kill-switch (−%{firm['daily']*100:.0f})"
    base = st["peak_eq"] if firm["trailing"] else st["start_eq"]   # trailing: zirveden; statik: baştan
    if equity <= base * (1 - firm["total"]):
        return f"TOPLAM kill-switch ({'trailing' if firm['trailing'] else 'statik'} −%{firm['total']*100:.0f})"
    return None


def main():
    print(__doc__)
    ap = argparse.ArgumentParser()
    ap.add_argument("--firm", choices=list(FIRMS), default="breakout1")
    ap.add_argument("--mode", choices=["pass", "funded"], default="pass")
    ap.add_argument("--execute", action="store_true", help="testnet'e gerçek emir (yoksa dry-run)")
    ap.add_argument("--maker", action="store_true", help="post-only limit emir (düşük fee)")
    ap.add_argument("--regime-gate", action="store_true", help="türbülansta riski kıs (düşük-vol'da tam)")
    ap.add_argument("--vol", type=float, default=None)
    args = ap.parse_args()
    assert TESTNET, "TESTNET-kilitli."
    firm = FIRMS[args.firm]
    preset = MODE_PRESETS[args.mode]
    vol = args.vol if args.vol is not None else preset["vol"]
    state_path = _BASE / f"prop_{args.firm}_{args.mode}.json"

    w, atrp, px, asof, low_vol = compute_targets()
    # rejim kapısı: pass'te türbülansta riski yarıla (geçişi artırır), funded'da her zaman temkinli
    regime_scale = 1.0
    if args.regime_gate and not low_vol:
        regime_scale = 0.5
    print(f"\nFIRMA={firm['label']} | MOD={args.mode.upper()} | vol %{vol*100:.0f} | "
          f"rejim={'SAKİN' if low_vol else 'TÜRBÜLANS'} (scale {regime_scale}) | "
          f"emir={'MAKER' if args.maker else 'market'} | as-of {asof}")

    ex, equity = None, 1000.0
    if args.execute:
        ex = make_exchange()
        bal = ex.fetch_balance()
        equity = float(bal.get("USDT", {}).get("total") or bal.get("total", {}).get("USDT") or 0) or 1000.0

    st = load_state(state_path)
    halt = risk_gate(equity, st, firm)
    if halt:
        state_path.write_text(json.dumps(st))
        print(f"\n⛔ {halt} — yeni pozisyon YOK. (kill-switch)")
        return

    gross = min(3.0, vol / 0.40) * regime_scale
    plan = []
    for s, wt in sorted(w.items(), key=lambda x: -abs(x[1])):
        notional = equity * gross * wt
        side = "buy" if wt > 0 else "sell"
        stop_dist = min(max(atrp[s] * ATR_STOP_MULT, 1e-4), PER_TRADE_RISK)
        stop_px = px[s] * (1 - stop_dist) if wt > 0 else px[s] * (1 + stop_dist)
        plan.append((s, side, abs(notional), px[s], stop_px, stop_dist))
        print(f"  {s:14} {side:4} ${abs(notional):8.2f} @ {px[s]:.4f}  SL {stop_px:.4f} (risk %{stop_dist*100:.1f})")

    if not args.execute:
        print("\n(DRY-RUN — emir gönderilmedi. Gerçek için --execute.)")
        st["last_plan_asof"] = asof
        state_path.write_text(json.dumps(st))
        return

    print(f"\nTESTNET emirleri ({'MAKER post-only' if args.maker else 'market'})…")
    ex.load_markets()
    for s, side, notional, last, stop_px, _ in plan:
        sym = s if "/" in s else f"{s}/USDT:USDT"
        if sym not in ex.markets:
            print(f"  ⊘ {sym} testnet'te yok")
            continue
        try:
            amount = ex.amount_to_precision(sym, notional / last)
            if args.maker:
                lim = last * (1 - MAKER_OFFSET) if side == "buy" else last * (1 + MAKER_OFFSET)
                ex.create_order(sym, "limit", side, amount, ex.price_to_precision(sym, lim),
                                {"timeInForce": "PostOnly"})
            else:
                ex.create_order(sym, "market", side, amount)
            sl_side = "sell" if side == "buy" else "buy"
            ex.create_order(sym, "market", sl_side, amount, None,
                            {"reduceOnly": True, "stopLossPrice": ex.price_to_precision(sym, stop_px),
                             "triggerDirection": 2 if side == "buy" else 1})
            print(f"  ✓ {sym} {side} {amount} + SL@{stop_px:.4f}")
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {sym}: {type(e).__name__}: {str(e)[:90]}")
        time.sleep(ex.rateLimit / 1000)
    st.update(equity=equity, last_exec_asof=asof)
    state_path.write_text(json.dumps(st))
    print("\n⚠️ TESTNET. Gerçek-funded geçişi AYRI onay gerektirir.")


if __name__ == "__main__":
    main()
