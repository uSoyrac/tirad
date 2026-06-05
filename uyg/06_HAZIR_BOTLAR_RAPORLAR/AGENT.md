# AGENT.md — 06 HAZIR BOTLAR çalıştırma & bakım (agent/insan için)

Bu klasör 3-kollu compound operasyonunun deploy-hazır botlarını içerir. Aşağıda her botun
NE yaptığı, NASIL çalıştırıldığı, NEYE bağlı olduğu. Tüm anahtarlar env'den; canlı emir öncesi onay.

## Ortak çekirdek
- `compound_engine.py` — paylaşılan risk/sizing. Fonksiyonlar:
  `fractional_kelly_gross(target_vol,kelly_frac,conviction)`, `kill_switch(eq,peak,day_start,firm)`,
  `kelly_risk_pct(base,conviction)`, `regime_scale(low_vol)`. FIRMS profilleri: hyro2/breakout1/ttp_flex/binance.
  Self-test: `python compound_engine.py` → "self-test OK".
- Zekâ çekirdeği: `_botlib.load_universe()` (mktdata + TIRAD_LIVE top-up) → combo sinyali.

## KOL 1 — Prop Crypto (HyroTrader)
- Strateji görünümü: `python bot_hyro.py [vol]` (sinyal + boyut, dry-run mantığı).
- Canlı (Bybit testnet, TESTNET-kilitli):
  ```
  . /root/tirad/.hyro_env   # BYBIT_TESTNET_KEY/SECRET (repo'da DEĞİL)
  TIRAD_LIVE=1 python hyro_executor.py --firm hyro2 --mode pass --execute --maker --regime-gate
  # compound için:  ... --kelly 0.25   (canlı equity üzerinden, büyüdükçe büyür)
  ```
- Modlar: `--mode pass` (%15 vol, challenge geç) / `--mode funded` (%8 vol, koru). Firma: hyro2/breakout1.
- Bağımlı: ccxt, _botlib, quantlab, compound_engine. Kill-switch + per-trade ATR-stop ≤%3.
- ⚠️ Bybit kişisel testnet'te `retCode 10024` (bölge/KYC) olabilir — HyroTrader funded hesabı ONLARIN
  Bybit entity'sini kullanır, kişisel engel geçerli değil.

## KOL 2 — Prop Hisse (Trade The Pool)
- `TIRAD_LIVE=1 python equity_signal.py` → `paper/equity_signal.json` + dashboard /hisse.
- Çıktı: Top-5 momentum LONG, **risk-bütçesi boyutlandırma** (toplam stop-riski ≤ %70×DD-bütçe),
  kesirli hisse adedi + stop + risk $. Manuel/Signal Stack uygula (ham bot yasak).
- Firma: ttp_flex (6% hedef / 2% günlük / 4% statik DD / %70 split). Cron: günlük 06:30.

## KOL 3 — Binance (kendi sermaye, compound)
- Aynı `hyro_executor.py --kelly 0.25` ama firma=binance profili (gevşek DD, %100 kâr).
  (Şimdilik Bybit-testnet-kilitli; Binance live executor ayrı onayla yazılır.)
- Compound: canlı equity üzerinden fractional-Kelly → büyüdükçe pozisyon büyür.

## TREND KOLU (opportunistic, Binance)
- Çalışan bot: `/root/tirad/uyg/src/live_bot.py` (PM2 tirad-bot). Geliştirme: per-coin ADX≥30 filtresi
  (OOS −0.02→+0.08). Detay: `botlar/TREND_BOTU_NOTU.md`. Rol: combo YANINDA, trend-yakalama.

## FX-carry (diversifikasyon)
- `python fx_carry_signal.py` → /forex. Haftalık cron. Manuel forex. Modest (0.9).

## RAPORLARI YENİDEN ÜRETME (quantlab/.venv)
```
cd quantlab
.venv/bin/python scripts/run_8month_report.py      # 8-ay konsolide (raporlar/report_8month.md)
.venv/bin/python scripts/run_compound_engine.py     # compound trajektori
.venv/bin/python scripts/run_firm_compare.py        # firma geçiş karşılaştırması
.venv/bin/python scripts/run_equity_prop_stats.py   # hisse prop rakamları
```
Tüm rapor .md'leri `raporlar/` altında (kopyalar). Kaynak: quantlab/reports_out/.

## DİSİPLİN (değişmez)
1. Canlı emir/gerçek-para öncesi KULLANICI ONAYI. Testnet/paper önce.
2. ≤¼-Kelly. Kill-switch hep açık. Compound yalnız GERÇEK edge'de (combo/hisse), trend'de değil.
3. Anahtar rotasyonu: sunucu root + panel + eski testnet anahtarları kullanıcı tarafından yenilenmeli.
4. Forward kanıt > backtest. 8-ay rakamları haircut'lı taban; gerçek = canlı-forward.
