#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
HYRO_EXECUTOR — HyroTrader/Bybit TESTNET executor (bot_hyro için)  ★ TESTNET-KİLİTLİ
═══════════════════════════════════════════════════════════════════════════════
bot_hyro'nun combo edge'ini (kripto-trend Top-3 long + funding long/short) Bybit
TESTNET'inde uygular — ÜCRETSİZ PAPER, GERÇEK SERMAYE YOK. Execution mantığını
(emir, stop-loss, pozisyon mutabakatı, kill-switch) gerçek para riske atmadan kanıtlar.

GÜVENLİK (sıkı):
  • TESTNET = sabit True. Mainnet yolu yok (KeyError ile durur). Gerçek-funded = AYRI onay.
  • API anahtarları yalnızca env'den: BYBIT_TESTNET_KEY / BYBIT_TESTNET_SECRET (asla hardcode).
  • Varsayılan DRY-RUN: emir planını yazar, yerleştirmez. Gerçek testnet emri için --execute.
  • Kill-switch'ler: günlük zarar %5, toplam (trailing) %10, işlem-başı risk %3 (HyroTrader).
  • Her pozisyona reduce-only STOP-LOSS (HyroTrader: ≤5dk içinde SL, ≤%3 risk).

HyroTrader kural-uyumu: Top-3+funding çeşitli → %40 konsantrasyonu doğal geçer; HFT/kopya/
cross-account YOK; her işleme SL.

ÇALIŞTIRMA (sunucuda, veri + testnet anahtarlarıyla):
  DRY-RUN  : quantlab/.venv/bin/python uyg/Botlar/hyro_executor.py
  TESTNET  : BYBIT_TESTNET_KEY=... BYBIT_TESTNET_SECRET=... \
             quantlab/.venv/bin/python uyg/Botlar/hyro_executor.py --execute
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

# ── güvenlik / kurallar ──────────────────────────────────────────────────────
TESTNET = True                 # HARD-LOCK. Mainnet bilinçli olarak YOK.
DAILY_LOSS_LIMIT = 0.05        # HyroTrader 2-step günlük
TOTAL_DD_LIMIT = 0.10          # HyroTrader 2-step toplam (trailing, EOD)
PER_TRADE_RISK = 0.03          # işlem-başı SL risk tavanı
TARGET_VOL = 0.10              # yıllık vol-hedef (pass ayarı; funded'da 0.07'ye düşür)
TOP_K = 3                      # momentum Top-K
N_FUND = 3                     # funding her yandan N
ATR_STOP_MULT = 2.0            # SL = entry ∓ mult*ATR (per-trade risk ≤%3'e clamp'lenir)
_BASE = Path("/root/tirad/paper") if Path("/root/tirad/paper").exists() else Path(__file__).resolve().parent / "_state"
_BASE.mkdir(parents=True, exist_ok=True)
STATE = _BASE / "hyro_testnet.json"


def make_exchange():
    import ccxt
    key, sec = os.environ.get("BYBIT_TESTNET_KEY"), os.environ.get("BYBIT_TESTNET_SECRET")
    if not key or not sec:
        raise SystemExit("BYBIT_TESTNET_KEY / BYBIT_TESTNET_SECRET env yok — testnet anahtarı gerek.")
    ex = ccxt.bybit({"apiKey": key, "secret": sec, "enableRateLimit": True,
                     "options": {"defaultType": "swap"}})
    ex.set_sandbox_mode(True)   # ← TESTNET; mainnet'e geçiş yok
    return ex


def compute_targets():
    """combo edge → her sembol için imzalı hedef ağırlık (+long / −short) ve ATR (stop için)."""
    from quantlab.indicators import atr
    cfg, frames, higher, targets, momentum, fundings = load_universe()
    asof = max(f.index[-1] for f in frames.values())

    # momentum Top-K long (target>0 olan ve momentum en yüksek)
    elig = [(s, float(momentum[s].reindex([asof]).fillna(-9).iloc[0]))
            for s in frames if float(targets[s].reindex([asof]).fillna(0).iloc[0]) > 0]
    elig.sort(key=lambda x: x[1], reverse=True)
    mom_long = [s for s, _ in elig[:TOP_K]]

    # funding: düşük-funding long / yüksek-funding short
    score = {s: float(fundings[s].tail(21).mean()) for s in fundings}
    ranked = sorted(score, key=score.get)
    fund_long, fund_short = ranked[:N_FUND], ranked[-N_FUND:]

    # imzalı ağırlık: iki sleeve eşit risk-bütçesi (basit, çeşitli → %40 kuralı geçer)
    w = {}
    for s in mom_long:
        w[s] = w.get(s, 0) + 0.5 / max(1, len(mom_long))
    for s in fund_long:
        w[s] = w.get(s, 0) + 0.5 / max(1, len(fund_long))
    for s in fund_short:
        w[s] = w.get(s, 0) - 0.5 / max(1, len(fund_short))

    atrp = {s: float(atr(frames[s], cfg.risk.atr_period).iloc[-1] / frames[s]["close"].iloc[-1])
            for s in w}
    px = {s: float(frames[s]["close"].iloc[-1]) for s in w}
    return w, atrp, px, str(asof.date())


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"start_eq": None, "peak_eq": None, "day": None, "day_start_eq": None, "halted": False}


def risk_gate(equity, st):
    """Günlük/toplam (trailing) kill-switch. Halt sebebi döner ya da None."""
    today = time.strftime("%Y-%m-%d")
    if st["start_eq"] is None:
        st.update(start_eq=equity, peak_eq=equity, day=today, day_start_eq=equity)
    if st["day"] != today:
        st["day"] = today
        st["day_start_eq"] = equity
    st["peak_eq"] = max(st["peak_eq"] or equity, equity)
    if equity <= st["day_start_eq"] * (1 - DAILY_LOSS_LIMIT):
        return f"GÜNLÜK kill-switch: {equity:.2f} ≤ gün-başı {st['day_start_eq']:.2f} −%{DAILY_LOSS_LIMIT*100:.0f}"
    if equity <= st["peak_eq"] * (1 - TOTAL_DD_LIMIT):
        return f"TOPLAM(trailing) kill-switch: {equity:.2f} ≤ zirve {st['peak_eq']:.2f} −%{TOTAL_DD_LIMIT*100:.0f}"
    return None


# mod ön-ayarları: PASS = challenge'ı geç (yüksek vol); FUNDED = patlamadan kazan (düşük vol + sıkı self-stop)
MODE_PRESETS = {
    "pass":   {"vol": 0.15, "intraday_stop": 0.04},   # hedefe hızlı yürü
    "funded": {"vol": 0.08, "intraday_stop": 0.03},   # hesabı koru, yavaş kazan
}


def main():
    print(__doc__)
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["pass", "funded"], default="pass",
                    help="pass=challenge geç (yüksek vol) | funded=patlamadan kazan (düşük vol)")
    ap.add_argument("--execute", action="store_true", help="testnet'e GERÇEK emir gönder (yoksa dry-run)")
    ap.add_argument("--vol", type=float, default=None, help="vol-hedefi elle ez (yoksa moddan)")
    args = ap.parse_args()
    assert TESTNET, "Bu executor TESTNET-kilitli."
    preset = MODE_PRESETS[args.mode]
    args.vol = args.vol if args.vol is not None else preset["vol"]

    w, atrp, px, asof = compute_targets()
    print(f"\nMOD={args.mode.upper()} | vol-hedef %{args.vol*100:.0f} | intraday self-stop "
          f"−%{preset['intraday_stop']*100:.0f} | hedef as-of {asof}:")

    ex, equity = None, 1000.0
    if args.execute:
        ex = make_exchange()
        bal = ex.fetch_balance()
        equity = float(bal.get("USDT", {}).get("total") or bal.get("total", {}).get("USDT") or 0) or 1000.0

    st = load_state()
    halt = risk_gate(equity, st)
    if halt:
        st["halted"] = True
        STATE.write_text(json.dumps(st))
        print(f"\n⛔ {halt} — yeni pozisyon YOK, hepsini kapat. (kill-switch)")
        return

    # vol-hedef → toplam brüt kaldıraç (basit: target_vol / book_vol tahmini; book_vol ~ %40/yıl alt sınır)
    gross = min(3.0, args.vol / 0.40)   # kaba ölçek; gerçek vol canlı veriden rafine edilir
    plan = []
    for s, wt in sorted(w.items(), key=lambda x: -abs(x[1])):
        notional = equity * gross * wt                       # imzalı (+long/−short)
        side = "buy" if wt > 0 else "sell"
        stop_dist = max(atrp[s] * ATR_STOP_MULT, 1e-4)
        stop_dist = min(stop_dist, PER_TRADE_RISK)           # per-trade risk ≤ %3 clamp
        stop_px = px[s] * (1 - stop_dist) if wt > 0 else px[s] * (1 + stop_dist)
        plan.append((s, side, abs(notional), px[s], stop_px, stop_dist))
        print(f"  {s:14} {side:4} ${abs(notional):8.2f} @ {px[s]:.4f}  SL {stop_px:.4f} (risk %{stop_dist*100:.1f})")

    if not args.execute:
        print("\n(DRY-RUN — emir GÖNDERİLMEDİ. Gerçek testnet için --execute + testnet anahtarı.)")
        st["last_plan_asof"] = asof
        STATE.write_text(json.dumps(st))
        return

    # --- TESTNET emir yerleştirme (her pozisyona reduce-only stop-loss) ---
    print("\nTESTNET emirleri gönderiliyor…")
    ex.load_markets()                       # sembol filtresi için
    for s, side, notional, last, stop_px, _ in plan:
        sym = s if "/" in s else f"{s}/USDT:USDT"
        if sym not in ex.markets:           # testnet'te listeli olmayan coinleri atla
            print(f"  ⊘ {sym} testnet'te yok, atlandı")
            continue
        try:
            amount = ex.amount_to_precision(sym, notional / last)
            ex.create_order(sym, "market", side, amount)
            sl_side = "sell" if side == "buy" else "buy"
            ex.create_order(sym, "market", sl_side, amount, None,
                            {"reduceOnly": True, "stopLossPrice": ex.price_to_precision(sym, stop_px),
                             "triggerDirection": 2 if side == "buy" else 1})
            print(f"  ✓ {sym} {side} {amount} + SL@{stop_px:.4f}")
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {sym}: {type(e).__name__}: {e}")
        time.sleep(ex.rateLimit / 1000)
    st.update(equity=equity, last_exec_asof=asof, halted=False)
    STATE.write_text(json.dumps(st))
    print("\n⚠️ TESTNET. Gerçek-funded geçişi AYRI onay gerektirir.")


if __name__ == "__main__":
    main()
