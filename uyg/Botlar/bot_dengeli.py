#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════
BOT 2 — DENGELİ (Yarı-Kelly)
═══════════════════════════════════════════════════════════════════
Getiri ile drawdown arası denge. "Birim risk başına en çok büyüme."
Mimari: Donchian40+SuperTrend → XGBoost kalite-kapısı → TP+5%/SL-2.5%
Sizing: DÜZ ~1.25x notional (yarı-Kelly, martingale YOK, ≤2.5x tavan).

DOĞRULANMIŞ (OOS walk-forward): $250→~$786 · +%60 CAGR · MaxDD ~%30 · WR %44

Çalıştır:  cd uyg/Botlar && python3 bot_dengeli.py
═══════════════════════════════════════════════════════════════════
"""
import _engine_path as B

def main():
    print(__doc__)
    print("Hazırlanıyor (sinyaller + walk-forward model)...")
    rows, P = B.prepare()
    B.E.GATE_TOP = 0.20
    r = B.E.backtest(rows, P, bankroll=250.0, sizing="fixed", notional_cap=1.25)
    B.report("BOT DENGELİ — düz 1.25x (yarı-Kelly)", r,
             "Dengeli · MaxDD ~%30 tolere edebilenler için · orta-agresif compound")

if __name__ == "__main__":
    main()
