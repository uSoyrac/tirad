"""
Renkli konsol çıktısı — her sinyal için terminal raporu.
"""
from datetime import datetime

from analysis.composite_scorer import CompositeScore
from signals.trade_setup import TradeSetup
from signals.position_sizer import PositionSize

# ANSI renk kodları
R = "\033[0m"
BOLD = "\033[1m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
DIM = "\033[2m"


def _score_color(score: float) -> str:
    if score >= 8.0:
        return RED + BOLD
    elif score >= 6.0:
        return YELLOW
    elif score >= 4.0:
        return CYAN
    return DIM


def print_signal(
    score: CompositeScore,
    setup: TradeSetup | None = None,
    pos: PositionSize | None = None,
    claude_text: str = "",
):
    sc = _score_color(score.composite)
    now = datetime.utcnow().strftime("%H:%M UTC")
    dir_str = (
        f"{GREEN}LONG ▲{R}" if score.direction in ("BULLISH", "LONG")
        else f"{RED}SHORT ▼{R}" if score.direction in ("BEARISH", "SHORT")
        else f"{DIM}NÖTR{R}"
    )

    print(f"\n{'━'*60}")
    print(f"{sc}{'🚨' if score.signal_level=='STRONG' else '📊'} {score.symbol} — {score.signal_level}{R}  [{now}]")
    print(f"  Yön: {dir_str}   Skor: {sc}{score.composite:.1f}/10{R}")
    print(f"  SMC:{score.smc_score:.1f} | Klasik:{score.classic_score:.1f} | Kurumsal:{score.institutional_score:.1f} | MTF:{score.mtf_score:.1f} | Sosyal:{score.social_score:.1f}")

    if score.smc_details:
        print(f"\n  {CYAN}SMC:{R}")
        for v in score.smc_details.values():
            print(f"    {v}")

    if score.classic_details:
        print(f"\n  {CYAN}Klasik:{R}")
        for v in score.classic_details.values():
            print(f"    {v}")

    if setup and setup.valid:
        print(f"\n  {YELLOW}Trade Setup:{R}")
        print(f"    Giriş:  {setup.entry_low:.4f} — {setup.entry_high:.4f}")
        print(f"    SL:     {RED}{setup.stop_loss:.4f}{R} (-%{setup.sl_pct*100:.1f})")
        print(f"    TP1:    {GREEN}{setup.tp1:.4f}{R} (+%{setup.tp1_pct*100:.1f}) → %40 kapat")
        print(f"    TP2:    {GREEN}{setup.tp2:.4f}{R} (+%{setup.tp2_pct*100:.1f}) → %35 kapat")
        print(f"    TP3:    {GREEN}{setup.tp3:.4f}{R} (+%{setup.tp3_pct*100:.1f}) → %25 kapat")
        if pos:
            print(f"    Kaldıraç: {pos.leverage}x  |  Pozisyon: ${pos.position_size:,.0f}  (Risk: ${pos.risk_amount:.0f})")
    elif setup and not setup.valid:
        print(f"\n  {DIM}Setup geçersiz: {setup.invalid_reason}{R}")

    if claude_text:
        print(f"\n  {MAGENTA}Claude Analizi:{R}")
        for line in claude_text.split("\n")[:10]:
            print(f"    {line}")

    print(f"{'━'*60}")
