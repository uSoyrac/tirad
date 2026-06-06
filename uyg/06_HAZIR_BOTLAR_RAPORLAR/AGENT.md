# AGENT.md — 06 HAZIR BOTLAR: agent başlangıç + çalıştırma & bakım

Bu klasör çok-kollu compound operasyonunun deploy-hazır botlarını içerir. Bir agent
(Gemini/Claude) bunu soğuktan okuyup sürdürebilmeli. Tüm anahtarlar env'den; canlı emir öncesi onay.

---

## 🧭 AGENT BAŞLANGICI (Gemini, buradan başla)

1. **Önce `README.md`** — operasyonun haritası, iki ana bot, panel-optimal config'ler, edge hiyerarşisi.
2. **Sonra `botlar/compound_engine.py`** — paylaşılan beyin. `PASS_CONFIGS` + `FUNDED_SURVIVAL`
   sözlükleri panelin doğruladığı SAYILARI kodlu tutar; `intraday_halt()` + `profit_bank()` + `kill_switch()`.
   `python compound_engine.py` → self-test "OK" vermeli (config'ler yüklü).
3. **Sayıların kaynağı `raporlar/`** — her iddianın arkasında bir backtest .md'si var
   (firm_montecarlo, propfirm_sizing, funded_survival, profit_extraction, report_8month).
4. **Değişmez disiplin** — bu dosyanın en altı. Bunları İHLAL ETME.
5. **Sonraki adım her zaman:** para riske etmeden testnet/paper forward-validasyon. Backtest ≠ canlı.

> **Altın kural:** %100 geçen bot yok. Dürüst tavan hissede ~%66-73, crypto'da ~%42-48. Bir agent
> bunu "garanti geçer" diye sunarsa YANLIŞ yapıyordur. Edge gerçek ama büyüklüğü rejim+survivorship-şişkin.

---

## Ortak çekirdek — `compound_engine.py`
Pür, test-edilebilir fonksiyonlar (tüm executor'lar import eder):
- `fractional_kelly_gross(target_vol, kelly_frac, conviction)` — vol-hedefli brüt kaldıraç (≤¼-Kelly).
- `kelly_risk_pct(base, conviction)` — işlem-başı risk, meta-proba ile ölçekli.
- `kill_switch(eq, peak, day_start, firm)` — günlük + toplam (trailing/statik) DD halt.
- `intraday_halt(eq, day_start, halt=0.03)` — **−%3 gün-içi self-halt (funded'da ZORUNLU).**
- `profit_bank(eq, baseline, trigger=0.03, split=0.80)` — funded payout + trailing-DD hayatta-kalma kolu.
- `regime_scale(low_vol)` — sakin %100 / türbülans kıs.
- `FIRMS` profilleri: hyro2 / breakout1 / ttp_flex / **ttp_safe** / **ttp_max** / binance.
- `PASS_CONFIGS`, `FUNDED_SURVIVAL`: panel-optimal config'ler (rakamlar README §1).
- Self-test: `python compound_engine.py` → "self-test OK ... pass/funded configs loaded".

Zekâ çekirdeği: `_botlib.load_universe()` (mktdata + TIRAD_LIVE top-up) → combo sinyali.

---

## KOL A — Geçiş botu (Prop Hisse, Trade The Pool) ← EN KOLAY GEÇİŞ
- `TIRAD_LIVE=1 python equity_signal.py` → `paper/equity_signal.json` + dashboard /hisse.
- Çıktı: Top-5 momentum LONG, **risk-bütçesi boyutlandırma** (toplam stop-riski ≤ %70×DD-bütçe),
  kesirli hisse adedi + stop + risk $. Signal Stack / manuel uygula (ham otomatik bot firmada yasak).
- **Optimal config: `ttp_safe`** (+%8 hedef / static −%6 / günlük −%3 @ %10 vol → P(geç) ~%66, IS%69/OOS%67).
  Daha agresif: `ttp_max` (+%10/static−%10/%15 vol → ~%73 ama intraday-uçurum riski yüksek).
- Cron: günlük 06:30.

## KOL B — Funded-survival botu (HyroTrader, funded olunca) ← BATMA, payout çek
```
. /root/tirad/.hyro_env   # BYBIT_TESTNET_KEY/SECRET (repo'da DEĞİL)
TIRAD_LIVE=1 python hyro_executor.py --firm hyro2 --mode funded --execute --maker --regime-gate
```
- **Optimal: vol %10 + bankala +%3 + −%3 intraday halt → P(6ay hayatta-kal) %96.7, ~$31/ay ($5K).**
- **COMPOUND ETME** (trailing floor). `profit_bank()` ile +%3 high-water üstünü çek. `intraday_halt()` hep açık.
- ⚠️ Bybit kişisel testnet'te `retCode 10024` (bölge/KYC) olabilir — HyroTrader funded hesabı ONLARIN
  entity'sini kullanır, kişisel engel geçerli değil.

## KOL C — Geçiş botu (Prop Crypto, HyroTrader)
- Aynı executor `--mode pass` (combo @ %15 vol, challenge geç). Crypto geçiş tavanı ~%41-48 (zor).
- `python bot_hyro.py [vol]` → strateji görünümü (sinyal + boyut, dry-run mantığı).
- Modlar: `--mode pass` / `--mode funded`. Firma: hyro2 / breakout1. ATR-stop ≤%3, kill-switch açık.

## KOL D — Binance (kendi sermaye, compound)
- `hyro_executor.py --kelly 0.25` ama firma=binance profili (gevşek DD, %100 kâr).
  (Şimdilik Bybit-testnet-kilitli; Binance live executor AYRI onayla yazılır.)
- Compound: canlı equity üzerinden fractional-Kelly → büyüdükçe pozisyon büyür. **Yalnız combo'da.**

## TREND KOLU (opportunistic, Binance)
- Çalışan bot: `/root/tirad/uyg/src/live_bot.py` (PM2 tirad-bot). Geliştirme: per-coin ADX≥30 (OOS −0.02→+0.08).
  Detay: `botlar/TREND_BOTU_NOTU.md`. Rol: combo YANINDA. **Compound etme** (rejim-bağımlı).

## FX-carry (diversifikasyon)
- `python fx_carry_signal.py` → /forex. Haftalık cron. Manuel forex. Modest (0.9).

---

## RAPORLARI YENİDEN ÜRETME (quantlab/.venv)
```
cd quantlab
.venv/bin/python scripts/run_firm_montecarlo.py        # firma×yapı geçiş MC (panel BOT A)
.venv/bin/python scripts/run_propfirm_sizing.py        # vol-seviye tavanı + path-shaping (panel)
.venv/bin/python scripts/run_funded_survival.py        # funded hayatta-kalma frontier (panel BOT B)
.venv/bin/python scripts/run_profit_extraction.py      # compound-vs-çek funded politikası (panel)
.venv/bin/python scripts/run_8month_report.py          # 8-ay konsolide
```
Tüm rapor .md'leri `raporlar/` altında (kopyalar). Kaynak: quantlab/reports_out/.

---

## DİSİPLİN (DEĞİŞMEZ — agent İHLAL ETMEZ)
1. **Canlı emir/gerçek-para öncesi KULLANICI ONAYI.** Testnet/paper önce. Mainnet ayrı onay.
2. **≤¼-Kelly.** Kill-switch + intraday-halt hep açık. Compound yalnız GERÇEK edge'de (combo/hisse), trend'de değil.
3. **Funded'da compound YOK** (trailing floor) — bankala-erken/küçük (+%3), −%3 intraday halt zorunlu.
4. **Anahtar rotasyonu:** sunucu root + panel + eski testnet anahtarları KULLANICI tarafından yenilenmeli.
   Anahtarları asla repo'ya yazma; yalnız server env (`.hyro_env` chmod 600) veya ephemeral Bash env.
5. **Forward kanıt > backtest.** 8-ay rakamları haircut'lı taban; %100 geçiş imkânsız; gerçek = canlı-forward.
6. **Dürüstlük:** her sayının arkasında `raporlar/`'da bir backtest olmalı. "Garanti kazanır" deme.
