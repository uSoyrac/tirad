#!/usr/bin/env python3
"""COMPOUND MOTORU — paylaşılan risk/boyutlandırma çekirdeği (tüm track'ler kullanır).

Kullanıcı vizyonu: kâr-al-çık → büyümüş bankroll'la yeniden-deploy = geometrik büyüme.
Mekaniği: CANLI equity üzerinden boyutlandır (equity büyüdükçe pozisyon büyür = compound),
fractional-Kelly (conviction-ölçekli) + kill-switch (compound DD'yi büyütür → emniyet kemeri).

GERÇEK edge (combo) için tasarlandı; trend/HH-LL (OOS-negatif) için DEĞİL — onları compound
etmek mirage'ı büyütür. Pür fonksiyonlar, test-edilebilir, hem crypto hem hisse executor'ı kullanır.
"""
from __future__ import annotations



# firma DD profilleri (track'e göre)
FIRMS = {
    "hyro2":     {"daily": 0.05, "total": 0.10, "trailing": True,  "label": "HyroTrader 2-step trailing"},
    "breakout1": {"daily": 0.04, "total": 0.06, "trailing": False, "label": "Breakout 1-step STATİK"},
    "ttp_flex":  {"daily": 0.02, "total": 0.04, "trailing": False, "label": "Trade The Pool hisse Flex"},
    "binance":   {"daily": 0.10, "total": 0.25, "trailing": True,  "label": "Binance kendi-sermaye"},
}


def fractional_kelly_gross(target_vol, kelly_frac=0.25, conviction=1.0,
                           book_vol=0.40, cap=3.0):
    """Brüt kaldıraç = vol-hedef/kitap-vol × Kelly-frac × conviction, tavanlı.
    target_vol/book_vol: yıllık. conviction∈[0,1.5] (meta-proba/sinyal gücü). ≤¼-Kelly önerilir."""
    base = target_vol / max(book_vol, 1e-6)
    return float(max(0.0, min(cap, base * (kelly_frac / 0.25) * conviction)))


def kelly_risk_pct(base_risk, conviction, meta_thr=0.35, max_risk=0.03):
    """İşlem-başı risk fraksiyonu, conviction'a (meta-proba) göre ölçekli (live_bot mantığı)."""
    if conviction < meta_thr:
        return 0.0
    return float(min(max_risk, base_risk * (0.5 + conviction / meta_thr * 0.5)))


def kill_switch(equity, peak_eq, day_start_eq, firm):
    """Günlük + toplam (firma trailing/statik) kill-switch. Halt sebebi (str) ya da None.
    compound'un emniyet kemeri — DD limiti aşılırsa yeni pozisyon yok."""
    f = FIRMS[firm] if isinstance(firm, str) else firm
    if day_start_eq and equity <= day_start_eq * (1 - f["daily"]):
        return f"GÜNLÜK kill-switch (−%{f['daily']*100:.0f})"
    base = peak_eq if f["trailing"] else (day_start_eq or peak_eq)   # statik: gün/başlangıç tabanı
    if base and equity <= base * (1 - f["total"]):
        return f"TOPLAM kill-switch ({'trailing' if f['trailing'] else 'statik'} −%{f['total']*100:.0f})"
    return None


def regime_scale(low_vol, scale_in_turbulence=0.5):
    """Rejim kapısı: sakin piyasada tam risk (1.0), türbülansta kıs."""
    return 1.0 if low_vol else scale_in_turbulence


def compound_note(equity, start_eq, kelly_frac):
    growth = (equity / start_eq - 1.0) * 100 if start_eq else 0.0
    return (f"COMPOUND: canlı equity ${equity:.0f} (başlangıç ${start_eq:.0f}, {growth:+.0f}%) üzerinden "
            f"boyutlandır → büyüdükçe pozisyon büyür. {kelly_frac:.2f}-Kelly. Kâr realize → bankroll → tekrar.")


if __name__ == "__main__":   # hızlı kendi-testi
    assert kill_switch(940, 1000, 1000, "ttp_flex") and not kill_switch(985, 1000, 1000, "ttp_flex")
    assert fractional_kelly_gross(0.15, 0.25, 1.0) > 0
    assert kelly_risk_pct(0.015, 0.5) > 0 and kelly_risk_pct(0.015, 0.2) == 0.0
    print("compound_engine self-test OK:", round(fractional_kelly_gross(0.15, 0.25, 1.0), 3),
          round(kelly_risk_pct(0.015, 0.5), 4))
