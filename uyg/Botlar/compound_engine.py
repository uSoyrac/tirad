#!/usr/bin/env python3
"""COMPOUND MOTORU — paylaşılan risk/boyutlandırma çekirdeği (tüm track'ler kullanır).

Kullanıcı vizyonu: kâr-al-çık → büyümüş bankroll'la yeniden-deploy = geometrik büyüme.
Mekaniği: CANLI equity üzerinden boyutlandır (equity büyüdükçe pozisyon büyür = compound),
fractional-Kelly (conviction-ölçekli) + kill-switch (compound DD'yi büyütür → emniyet kemeri).

GERÇEK edge (combo) için tasarlandı; trend/HH-LL (OOS-negatif) için DEĞİL — onları compound
etmek mirage'ı büyütür. Pür fonksiyonlar, test-edilebilir, hem crypto hem hisse executor'ı kullanır.
"""
from __future__ import annotations



# firma DD profilleri (track'e göre). trailing=zirveden takip (zor), statik=sabit taban (kolay).
FIRMS = {
    "hyro2":     {"daily": 0.05, "total": 0.10, "trailing": True,  "label": "HyroTrader 2-step trailing"},
    "breakout1": {"daily": 0.04, "total": 0.06, "trailing": False, "label": "Breakout 1-step STATİK"},
    "ttp_flex":  {"daily": 0.02, "total": 0.04, "trailing": False, "label": "Trade The Pool hisse Flex (+%6)"},
    "ttp_safe":  {"daily": 0.03, "total": 0.06, "trailing": False, "label": "TTP +%8/static-%6 (EN GÜVENLİ geçiş)"},
    "ttp_max":   {"daily": 0.05, "total": 0.10, "trailing": False, "label": "TTP +%10/static-%10 (EN YÜKSEK geçiş)"},
    "binance":   {"daily": 0.10, "total": 0.25, "trailing": True,  "label": "Binance kendi-sermaye"},
}

# ── PANEL-OPTİMAL CONFIG'LER (10-ajan paneli; block-bootstrap 25-30k yol, haircut ×0.6) ──
# Kaynak: reports_out/{firm_montecarlo,propfirm_sizing,funded_survival,profit_extraction_*}.md
# DÜRÜST: %100 geçiş İMKÂNSIZ — aşağıdakiler tavan. İki AYRI bot, iki AYRI edge:
#   • Hisse (TTP, us_momentum, STATİK DD) geçişte KOLAY → ~%66-73 (IS≈OOS, rejim-sağlam).
#   • Crypto (HyroTrader, combo, TRAILING DD) geçişte ZOR → ~%42-48 (trailing floor zirveyi kovalar).
# Birinin rakamını diğerine yamama. Geçiş kolu için TTP'yi kullan; crypto'yu funded-survival'da yaşat.
PASS_CONFIGS = {
    "ttp_safe":   {"firm": "ttp_safe", "edge": "us_momentum", "target": 0.08, "vol": 0.10,
                   "p_pass_full": 0.66, "p_pass_is": 0.69, "p_pass_oos": 0.67,
                   "note": "EN GÜVENLİ: EOD ≤−%3 olasılığı düşük → intraday-uçurum riski ~0"},
    "ttp_max":    {"firm": "ttp_max",  "edge": "us_momentum", "target": 0.10, "vol": 0.15,
                   "p_pass_full": 0.73, "p_pass_is": 0.74, "p_pass_oos": 0.73,
                   "note": "EN YÜKSEK geçiş ama EOD ≤−%3 olasılığı %34 → biraz daha riskli"},
    "hyro_2step": {"firm": "hyro2",    "edge": "combo",       "target": 0.10, "vol": 0.15,
                   "p_pass_full": 0.41, "p_pass_is": 0.35, "p_pass_oos": 0.48,
                   "note": "Crypto, trailing-%10, +%10/+%5 2-faz — yapısal olarak ZOR"},
}

# Funded-survival: hedef YOK → 6+ ay batma, payout çek. COMPOUND ETME (trailing floor zirveyi
# kovalar → normal geri-çekilme öldürür). Bankala-erken/küçük + −%3 intraday halt ZORUNLU.
FUNDED_SURVIVAL = {
    "hyro_2step": {"firm": "hyro2", "vol": 0.10, "bank_trigger": 0.03, "intraday_halt": 0.03, "split": 0.80,
                   "p_survive_6mo_all": 0.967, "blowup_all": 0.033, "payout_5k_mo": 31, "payout_25k_mo": 153,
                   "note": "ALL-pool muhafazakâr (OOS %95.3). Bankalama = hayatta-kalma kolu."},
    "hyro_1step": {"firm": "breakout1", "vol": 0.07, "bank_trigger": 0.03, "intraday_halt": 0.03, "split": 0.80,
                   "p_survive_6mo_all": 0.918, "blowup_all": 0.082, "payout_5k_mo": 22, "payout_25k_mo": 108,
                   "note": "1-step trailing-%6 daha sıkı → daha düşük vol gerekir."},
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


def intraday_halt(equity, day_start_eq, halt=0.03):
    """Intraday self-halt: gün-içi −halt%'e değerse o gün DUR (EOD daily-limite ASLA değme).
    EOD-verinin gün-içi uçurumu hafife almasına karşı ZORUNLU emniyet. Sebep (str) ya da None."""
    if day_start_eq and equity <= day_start_eq * (1 - halt):
        return f"INTRADAY self-halt (−%{halt*100:.1f}) — gün kapandı"
    return None


def profit_bank(equity, baseline, trigger=0.03, split=0.80):
    """Funded payout: equity, baseline×(1+trigger) üstündeyse tamponu çek (trader split'i alır).
    TRAILING-DD'de bankalama yalnız gelir DEĞİL HAYATTA-KALMA kolu: realize-peak'i düşürür →
    floor tırmanmayı durdurur. Döner: (çekilen_brüt, trader_eline_geçen, yeni_equity)."""
    if not baseline or equity <= baseline * (1 + trigger):
        return 0.0, 0.0, equity
    gross = equity - baseline
    return gross, gross * split, baseline


def compound_note(equity, start_eq, kelly_frac):
    growth = (equity / start_eq - 1.0) * 100 if start_eq else 0.0
    return (f"COMPOUND: canlı equity ${equity:.0f} (başlangıç ${start_eq:.0f}, {growth:+.0f}%) üzerinden "
            f"boyutlandır → büyüdükçe pozisyon büyür. {kelly_frac:.2f}-Kelly. Kâr realize → bankroll → tekrar.")


if __name__ == "__main__":   # hızlı kendi-testi
    assert kill_switch(940, 1000, 1000, "ttp_flex") and not kill_switch(985, 1000, 1000, "ttp_flex")
    assert fractional_kelly_gross(0.15, 0.25, 1.0) > 0
    assert kelly_risk_pct(0.015, 0.5) > 0 and kelly_risk_pct(0.015, 0.2) == 0.0
    # intraday halt: −%3'e değince halt, üstünde temiz
    assert intraday_halt(970, 1000, 0.03) and not intraday_halt(975, 1000, 0.03)
    # profit_bank: +%3 tetik üstü çeker (split sonrası), altında çekmez
    g, t, neweq = profit_bank(1050, 1000, 0.03, 0.80)
    assert g == 50.0 and abs(t - 40.0) < 1e-9 and neweq == 1000
    assert profit_bank(1020, 1000, 0.03)[0] == 0.0
    # panel config'leri bütün mü
    assert FIRMS["ttp_safe"]["total"] == 0.06 and not FIRMS["ttp_safe"]["trailing"]
    assert PASS_CONFIGS["ttp_max"]["p_pass_full"] == 0.73
    assert FUNDED_SURVIVAL["hyro_2step"]["p_survive_6mo_all"] == 0.967
    print("compound_engine self-test OK:", round(fractional_kelly_gross(0.15, 0.25, 1.0), 3),
          round(kelly_risk_pct(0.015, 0.5), 4), "| pass/funded configs loaded")
