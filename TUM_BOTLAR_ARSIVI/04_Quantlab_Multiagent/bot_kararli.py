#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════
BOT 1 — KARARLI (Muhafazakâr / En Stabil)
═══════════════════════════════════════════════════════════════════
En düşük drawdown, en sağlam. "Para kazanmaktan önce kaybetmemek."
Mimari: Donchian40+SuperTrend → XGBoost kalite-kapısı → TP+5%/SL-2.5%
Sizing: DÜZ %60 notional (kaldıraçsıza yakın, martingale YOK).

DOĞRULANMIŞ (OOS walk-forward): $250→$480 · +%31 CAGR · MaxDD %17 · WR %44 · MAR 1.84

Çalıştır:  cd uyg/Botlar && python3 bot_kararli.py
═══════════════════════════════════════════════════════════════════
"""
import _engine_path as B

def main():
    print(__doc__)
    print("Hazırlanıyor (sinyaller + walk-forward model)...")
    rows, P = B.prepare()
    B.E.GATE_TOP = 0.20
    r = B.E.backtest(rows, P, bankroll=250.0, sizing="fixed", notional_cap=0.6)
    B.report("BOT KARARLI — düz %60 notional", r,
             "En stabil · düşük drawdown · uzun-vade compound için ideal başlangıç")

if __name__ == "__main__":
    main()
