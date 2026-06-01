# 🧠 TIRAD — İSTİHBARAT MERKEZİ (V63 Compound Engine)

> Bu doküman, projede yapılan **tüm kantitatif araştırmanın** dürüst, walk-forward
> doğrulanmış, leak-free özetidir. ~40+ deney. Hayal yok, abartı yok. Repo'yu açan
> herkesin (veya gelecekteki bir AI ajanının) tek bakışta gerçeği görmesi içindir.
>
> **Üretim:** 2026-06-01 · **Altın kural:** Backtest ≠ canlı. Gerçek karar paper-trade'de verilir.

---

## ⚡ TL;DR — Nihai Durum

| | |
|---|---|
| **Doğrulanmış sistem** | `uyg/src/compound_engine.py` |
| **Mimari** | Donchian(40)+SuperTrend(10,3) sinyal → XGBoost kalite-kapısı → TP/SL → Kelly sizing |
| **Performans (OOS walk-forward, muhafazakâr)** | $250→$480 · **+%31 CAGR** · MaxDD %17 · WR %44 |
| **Edge gerçek mi?** | ⚠️ **Deflated Sharpe %31** — istatistiksel kanıt zayıf (40 deney selection-bias). |
| **Tek eksik halka** | **Paper-trade** — gerçek slippage + forward veri. Klavyede çözülecek şey kalmadı. |

**Edge = asimetri (2:1) + ML kalite-filtresi + stop + compound.** Yüksek isabet DEĞİL (WR tavanı ~%45). ML **yön tahmininde** alfa üretmiyor (AUC ~0.52); sadece **kalite-filtresi** olarak değer katıyor.

---

## 1. Doğrulanmış Sistem ve Çalıştırma

```bash
cd uyg/src && python3 compound_engine.py     # OOS backtest + compound trajektori
```
**Config (kilitli):** top5 (BTC/ETH/SOL/BNB/XRP) · 1H · Donchian40+SuperTrend(10,3) · BTC-EMA200 rejim kapısı · XGBoost discriminator (14 feature, walk-forward) · gate top %20 · TP +%5 / SL −%2.5 · sizing düz/Kelly.

---

## 2. Compound Matematiği — Kaldıraç & Risk Menüsü

Compound oranının **matematiksel tavanı = Kelly-optimal kaldıraç.** Ötesi volatilite-drag.

| Profil | Kaldıraç | CAGR (trendli OOS) | MaxDD | Tutulabilirlik |
|---|---|---|---|---|
| Muhafazakâr | 0.6x | +%31 | %17 | ✅ rahat |
| Dengeli (yarı-Kelly) | ~1.25x | +%60 | %30 | ⚠️ zor |
| Agresif (Kelly tepesi) | 2.5x | **+%86** | %55 | ❌ çoğu kişi bırakır |
| **Aşırı (lottery)** | 5x+ | **−%4 … −%99 (iflas)** | %85+ | ☠️ drag öldürür |

- **Tepe 2.5x** (+%86 trendli / +%42 choppy). **2.5x ötesi compound oranını DÜŞÜRÜR** (5x→−%4, 10x→−%99). Lottery/aşırı-kaldıraç matematiksel olarak daha az verir.
- **Aylık $100 katkı:** sonucu domine eder + yüksek kaldıracı hayatta-kalınır yapar. Full OOS $3.050 yatırım → 2x'te $7.178. Choppy yılda kaldıraç işe yaramaz (rejim-bağımlı).
- **Agresif 2.5x hafta-hafta (2 yıl):** $250→$1.114 (4.5x) AMA ilk 5 haftada −%50, zirveden 5+ kez −%45-52, MaxDD %55. Teorik optimal ≠ psikolojik tutulabilir.

---

## 3. Edge Ne Kadar Güvenilir? (Tier-2 İstatistik)

- **Bootstrap CAGR %95 aralık:** [−%2.5, +%75.8], medyan +%31.6, P(>0)=%93.
- **Loss-streak MC:** 99. persentil **17 ardışık kayıp** → ~%24 hesap DD. Kasa bunu kaldırmalı.
- **Deflated Sharpe (López de Prado, 40 deney):** per-trade SR 0.077 < şans-eşiği 0.099 → **DSR = %31.** Edge'in gerçek olma olasılığı ~%31 (muhafazakâr; 4H 5/5-yıl robustluğu daha güçlü kanıt).

➡️ **Sonuç:** Backtest tek başına "gerçek edge mi, 40-config madenciliği mi" ayıramıyor. Paper-trade matematiksel zorunluluk.

---

## 4. NE TEST EDİLDİ ve ELENDİ (tekrar deneme — dürüstçe çürütüldü)

| Teori / Fikir | Sonuç | Neden |
|---|---|---|
| **XGBoost YÖN tahmini** (V20-V31 Komutan) | ❌ yazı-tura | AUC ~0.52, 1yıl OOS $100→$98.60 |
| **Mikroyapı türevleri** (işlem sayısı/büyüklüğü/taker-buy "smart money") | ❌ katkı yok | WR %40→%39, top-10 feature'da yok; public agregat balina≠retail ayıramıyor |
| **MTF / üst-TF / piyasa-genişliği / zamansal** | ❌ dilue | rejim kapısı zaten içeriyor; htf4h eklenince KIRILGAN (overfit) |
| **Sinyal-ekibi varyantları** (12 kombinasyon) | ❌ doygun | hepsi ~%40 WR; don55 ham-iyiydi ama uçtan-uca kötü (kuplaj) |
| **Trailing stop + Pyramiding** ("kazananı katla") | ❌ −36…−72% | 4H trendde whipsaw; sabit 3R TP daha iyi |
| **Eşzamanlı çoklu-pozisyon** | ❌ risk-ayarlı kötü | düşük-kaliteli sinyale girer (WR↓), tek-pozisyon örtük seçici |
| **Daha hızlı TF (1H/15dk/saniye)** | ❌ $100→$8 | maliyet edge'i yer; HFT = perakende avı |
| **Aylık 10x-lottery** (reset & retry) | ❌ 0/12 vurdu | reset compound'u öldürür; 10x = drag |
| **"Kaybedince betting artır" (martingale)** | ☠️ iflas | 8-13 loss-streak'te sıfırlama; P(iflas) %72-78 |
| **20-coin evren, ikinci-kol (mean-reversion)** | ❌ | alt coinler ayıda zehirli; MR net-negatif (rho−0.40 ama edge yok) |
| **Funding-carry / basis / OI-LS / pairs / StatArb** | ❌ | gerçek ama kırılgan/düşük-getiri ya da OOS negatif |

**Tek robust iyileştirme:** TP_R 2.75→3.0 (4H trend) ve XGBoost hafif-gate (q0.2-0.3). Geri kalan ~40 fikir ya curve-fit ya regresyon → **sistem optimumda.**

---

## 5. Değişmez Kurallar

1. **Recovery/martingale YASAK.** Kaybedince büyütme = iflas. Sadece düz veya anti-martingale (kazanırken büyüt).
2. **Kaldıracı getiri iştahı değil, dayanabileceğin MaxDD belirler.** Kelly tepesini (2.5x) GEÇME.
3. **Backtest ≠ canlı.** DSR %31. Önce paper-trade, sonra küçük sermaye, sonra compound.
4. **Daha fazla feature/parametre madenciliği = negatif değer** (her deney DSR'ı seyreltir). Sıradaki bilgi sadece canlı veriden.
5. **Hayal satma:** "Ayda 100→1000" = ~%0.06 olasılık = yok. Gerçek: ~%20-86 CAGR (kaldıraca göre), yıllarla.

---

## 6. Sıradaki Adım

→ `compound_engine.py` config'ini `uyg/src/live_bot.py`'ye bağla → **paper-trade** (BOT_MODE=paper) → 1-2 ay canlı veride backtest tutarlılığını izle → tutarsa küçük gerçek sermaye + $100/ay katkı + orta kaldıraç (≤2x).

---

## İlgili Dokümanlar
- `uyg/SISTEM_2026-05-31_OPTIMAL.md` — 4H trend sistemi handoff (donchian+supertrend+meta)
- `uyg/KARAR_2026-06-01.md` — yönsel + yönsüz edge araştırma kararı
- `AGENT.md` — bot/engine V31 Komutan Modu (XGBoost yön-robotu — yazı-tura, üretime sürme)
- `compound_engine.py` docstring — tam config + acımasız gerçekler
