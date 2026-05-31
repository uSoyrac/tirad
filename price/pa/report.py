"""3-bölümlü çıktı formatı (workflow.md ile uyumlu) — stdlib.

BÖLÜM 1 — bağımsız price action analizi (motor çıktısı)
BÖLÜM 2 — veri okuması (funding/OI/whale ... erişilemezse işaretlenir)
BÖLÜM 3 — karşılaştırma ve nihai karar kartı
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from .types import Setup, Side
from .risk import LeveragePlan, position_size
from .analyze import AnalysisResult

if TYPE_CHECKING:
    from .market import DataReading


def render(result: AnalysisResult, *, reading: "Optional[DataReading]" = None,
           data_section: Optional[str] = None,
           portfolio: Optional[float] = None, risk_pct: float = 1.0) -> str:
    s = result.setup
    lines = ["BÖLÜM 1 — Price Action Analizi (bağımsız)"]
    for n in result.notes:
        lines.append(f"  • {n}")
    if s.reasons:
        for r in s.reasons:
            lines.append(f"  • {r}")
    else:
        lines.append("  • Yapısal zincir tamamlanmadı.")
    lines.append("")

    lines.append("BÖLÜM 2 — Veri Okuması")
    if reading is not None:
        lines.append(reading.render())
    elif data_section:
        lines.append(data_section)
    else:
        lines.append("  ⚠️ Canlı veri kaynakları (funding/OI/long-short/whale/"
                     "liquidation) bu çalıştırmada alınmadı — eksik olarak "
                     "işaretlendi, yokmuş gibi varsayılmadı.")
    lines.append("")

    lines.append("BÖLÜM 3 — Karşılaştırma ve Sonuç")
    confl = _confluence(s, reading)
    if confl:
        lines.append(confl)
    if not s.valid:
        lines.append(f"  ⚠️ İşlem için yeterli koşul yok. [neden: {s.rejected}]")
        return "\n".join(lines)
    lines.append(_card(s, result.plan, portfolio, risk_pct))
    return "\n".join(lines)


def _confluence(s: Setup, reading: "Optional[DataReading]") -> str:
    """Bölüm 1 (yapı) ile Bölüm 2 (veri) uyumlu mu? Veri yoksa düşük güven."""
    if reading is None or not reading.any_available:
        return ("  • Veri katmanı yok/eksik → yapı ile teyit yapılamadı; "
                "işlem güveni DÜŞÜK.")
    if not s.valid:
        return ""
    crowd = reading.crowded_side()
    if crowd is None:
        return "  • Veri karışık → net teyit yok; güven NÖTR."
    # kalabalık taraf işlem yönüyle aynıysa, kontra mantığı uyarısı
    same = (crowd == s.side.value)
    if same:
        return (f"  • Veri kalabalığı işlemle AYNI yönde ({crowd}); "
                f"squeeze/kontra riski → güven ÖLÇÜLÜ.")
    return (f"  • Veri kalabalığı ({crowd}) işleme TERS → likidite hedefiyle "
            f"uyumlu, teyit GÜÇLÜ.")


def _card(s: Setup, plan: Optional[LeveragePlan],
          portfolio: Optional[float], risk_pct: float) -> str:
    rows = [
        f"  🎯 Coin: {s.symbol or '?'}",
        f"  İşlem Yönü: {s.side.value}",
        f"  Zaman Dilimi: {s.timeframe or '?'}",
        f"  Giriş: {s.entry:.4f}",
        f"  Stop Loss: {s.stop:.4f}  (stop %{s.stop_pct:.2f})",
        f"  Take Profit: {s.target:.4f}",
        f"  Risk/Ödül: 1:{s.rr:.2f}",
    ]
    if plan is not None:
        rows.append(f"  Kaldıraç: {plan.describe()}")
        if portfolio is not None and plan.recommended:
            ps = position_size(portfolio, s.stop_pct, plan.recommended, risk_pct)
            rows.append(
                f"  Pozisyon (port. {portfolio:.0f}, risk %{risk_pct:.1f} → "
                f"{ps.risk_amount:.2f}): notional {ps.notional:.2f}, "
                f"teminat ~{ps.margin:.2f} @ {plan.recommended}x")
    rows.append("  Gerekçe özeti:")
    for r in s.reasons:
        rows.append(f"    - {r}")
    return "\n".join(rows)
