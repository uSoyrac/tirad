# 06 — HAZIR BOTLAR & RAPORLAR (çok-kollu compound trading operasyonu)

**Tek zekâ-çekirdeği (combo edge) → birden çok kol → paylaşılan compound motoru.**
Felsefe (projenin başından beri): **kâr-al-çık → büyümüş bankroll'a ekle → yeniden-deploy = geometrik büyüme.**

Bu klasör kendi-kendine yeten arşivdir: tüm deploy-hazır botlar + her birinin AMACI + NASIL
çalıştığı + son-8-ay sonuçları + 10-ajan panelinin doğruladığı **optimal config'ler**. Bir agent
(Gemini/Claude) bunu soğuktan okuyup operasyonu sürdürebilmeli. Çalıştırma detayı: **AGENT.md**.

---

## 0) HIZLI YÖN — "hangi bot ne işe yarar"

| Kol | Bot | Amaç | Edge | Firma/piyasa |
|---|---|---|---|---|
| **A. Geçiş botu (prop hisse)** | `equity_signal.py` | Prop challenge'ı GEÇ | US tek-hisse momentum | Trade The Pool (TR-OK) |
| **B. Funded-survival botu** | `hyro_executor.py --mode funded` | Funded'da BATMA, payout çek | combo (crypto) | HyroTrader (TR-OK) |
| **C. Geçiş botu (prop crypto)** | `hyro_executor.py --mode pass` | Crypto challenge'ı geç | combo | HyroTrader |
| **D. Binance compound** | `hyro_executor.py --kelly` + `compound_engine.py` | Kendi sermayeyi büyüt | combo + compound | Binance (kendi $) |
| Trend kolu (opportunistic) | `TREND_BOTU_NOTU.md` (live_bot.py) | Trend-yıllarında ekstra yakala | Donchian+ST+ADX≥30 | Binance |
| FX-carry (diversifikasyon) | `fx_carry_signal.py` | Düşük-korelasyon sinyal | FX carry (modest) | forex (manuel) |

**Paylaşılan beyin:** `compound_engine.py` — fractional-Kelly + firma-farkında kill-switch +
**`intraday_halt()`** (−%3 gün-içi self-halt) + **`profit_bank()`** (funded payout/hayatta-kalma kolu).
Panel-optimal config'ler bu dosyada `PASS_CONFIGS` ve `FUNDED_SURVIVAL` sözlüklerinde KODLU.

---

## 1) İKİ ANA BOT — panel-optimal config'ler (DÜRÜST tavanlar)

10-ajan paneli (block-bootstrap 25-30k yol, survivorship haircut ×0.6, IS/OOS/ALL rejim-çapraz).
Kaynak raporlar: `raporlar/{firm_montecarlo,propfirm_sizing,funded_survival,profit_extraction_2step_6mo}.md`.

### 🟢 BOT A — GEÇİŞ botu (challenge'ı geçer)
> **İki ayrı yol, iki ayrı edge — KARIŞTIRMA.** Hisse static-DD geçişte kolay; crypto trailing-DD zor.

| Config | Firma yapısı | Vol | P(geç) FULL | IS | OOS | Not |
|---|---|---|---|---|---|---|
| **`ttp_safe` (önerilen)** | TTP +%8 / static −%6 / günlük −%3 | %10 | **%66** | %69 | %67 | EOD ≤−%3 olasılığı düşük → intraday-uçurum ~0 |
| `ttp_max` (agresif) | TTP +%10 / static −%10 / günlük −%5 | %15 | **%73** | %74 | %73 | En yüksek ama EOD ≤−%3 olasılığı %34 |
| `hyro_2step` (crypto) | HyroTrader +%10/+%5 / trailing −%10 | %15 | **%41** | %35 | %48 | Crypto yapısal olarak ZOR |

**Tek gerçek geçiş kaldıracı = VOL SEVİYESİ** (path-shaping/ramp/lock/governor kendi optimumunda
bile sabit-vol'ü geçmedi — `propfirm_sizing.md`). Statik DD (TTP) trailing'i (HyroTrader) **yapısal
olarak** yener: floor zirveyi kovalamaz, normal geri-çekilme seni öldürmez.

> ⚠️ **%100 geçiş İMKÂNSIZ.** Dürüst tavan hissede ~%66-73, crypto'da ~%42-48. Gerisi
> hedefe-yetişememe + blowup. IS≈OOS olduğu için %73 bir rejim-artefaktı DEĞİL (hisse gerçek).

### 🔵 BOT B — FUNDED-SURVIVAL botu (funded olunca çalışır)
> Hedef YOK. İş: 6+ ay **batmadan** payout çekmek. Mantık geçiş botunun TERSİ: düşük-vol + erken-bankala.

**Optimal (HyroTrader 2-step, daily −5 / trailing −10):**
- **Vol %10 + bankala +%3 high-water + −%3 intraday halt** →
  **P(6 ay hayatta-kal) = %96.7 (ALL-pool muhafazakâr; OOS %95.3)**, blowup %3.3.
- Beklenen gelir (split %80 sonrası): **~$31/ay ($5K) · ~$153/ay ($25K)**.

**3 değişmez kural (`funded_survival.md` + `profit_extraction_2step_6mo.md`):**
1. **COMPOUND ETME.** Trailing floor zirveyi kovalar → büyüt = normal pullback öldürür.
   (Greedy-compound tuzağı: vol %15 → exp $492 AMA P(survive) sadece %47.)
2. **Bankala erken/küçük (+%3).** Trailing-DD'de bankalama yalnız gelir değil **hayatta-kalma kolu**
   (realize-peak'i düşürür → floor tırmanmayı durdurur). `profit_bank()` bunu yapar.
3. **−%3 intraday self-halt ZORUNLU.** EOD veri gün-içi −%5 uçurumu hafife alıyor; sim'de etkisi
   küçük görünse de gerçekte tek savunma bu. `intraday_halt()` bunu yapar.

---

## 2) SON-8-AY SONUÇLARI (gerçek getiriler, haircut ×0.6, dürüst)
Detay: `raporlar/report_8month.md`. ⚠️ tek-yol simülasyon, 2025-26 cömert rejim → gerçekçi TABAN.

| Kol | Challenge | Funded | İçerde kâr-al | 8-ay net/büyüme |
|---|---|---|---|---|
| Prop HyroTrader (crypto) | 2 | 1 (sonra patladı) | 0× | **−$118** |
| Prop Trade The Pool (hisse) | 1 | 1 | 0× | **−$53** |
| Binance compound (¼-Kelly) | — | — | — | **$1000 → $1,061 (+%6)** |

**Dürüst okuma:** bu pencerede funded olduk ama payout eşiğine ulaşmadan ya patladık ya pencere
bitti → net hafif-negatif; Binance +%6. Haircut'sız/full-OOS rakamları çok daha yüksek (combo
¼-Kelly +%98) — gerçek ikisinin arasında, **rejime bağlı. Funded olmak ≠ para çekmek.**

> **Operasyon-EV uyarısı:** hızlı "her seferinde $200 çek, fonu yeniden al" challenge-farming bu
> veride PARA KAYBEDİYOR; iade-edilebilir ücret ancak başa-başa getiriyor (`farm_backtest.md`).
> Bu yüzden tasarım **funded-survival (yavaş, hayatta-kalan gelir)** üzerine, farming üzerine değil.

---

## 3) DOĞRULANMIŞ EDGE HİYERARŞİSİ (ne işe yarar, ne yaramaz)
- ✅ **Crypto combo** (cross-sectional momentum + funding) — OOS ~1.85, DSR 1.00/PBO 0.01. Ana edge.
- ✅ **US hisse momentum** — OOS 1.66, crypto'ya ortogonal. **En kolay prop geçişi** (TTP ~%66-73).
- ⚠️ **FX carry** — modest (0.9), düşük-turnover; diversifikasyon sinyali.
- ⚠️ **Trend** (Donchian/ST/HH-LL) — rejim-bağımlı (trend-yılı +, chop −). ADX≥30 ile OOS +0.08;
  combo'nun YERİNE değil YANINDA opportunistic. Detay: `raporlar/trend_*.md`.
- ❌ **Futures** (TSMOM): edge yok. ❌ **Forex-ex-carry**: edge yok. ❌ **ML yön-tahmini**: yazı-tura.

---

## 4) GÜVENLİK / DİSİPLİN (değişmez)
- **Anahtarlar yalnız env** (asla repo). Canlı emir öncesi **kullanıcı onayı + testnet-önce**.
- **≤¼-Kelly tavanı** (f* survivorship-şişkin). Compound DD'yi büyütür → kill-switch + intraday-halt şart.
- **Compound yalnız COMBO'yu büyütür** (gerçek edge), trend'i DEĞİL (rejim-bağımlı → mirage'ı büyütmek ruin).
- **Funded'da compound YOK** (trailing floor) — bankala-erken.
- **Bölge:** HyroTrader / Trade The Pool TR-OK; Breakout / FundingPips TR-yasaklı + edge transfer etmez.
- **En yüksek-EV sonraki adım:** PARA RİSKE ETMEDEN testnet/paper'da forward-valide et. Forward kanıt
  survivorship'i temizleyen tek yol. **Bu geçmeden tek challenge ücreti ödeme.**

---

## 5) DASHBOARD (tirad.45.143.11.97.nip.io)
/sinyal (crypto) · /hisse (hisse, challenge-hazır) · /forex (FX carry) · /bybit (testnet) ·
/saglik · /arastirma (haftalık re-research) · /rapor · /piyasa

---

**Çalıştırma/bakım + agent başlangıç rehberi → `AGENT.md`.**
