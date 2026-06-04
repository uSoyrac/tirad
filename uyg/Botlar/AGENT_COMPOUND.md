# 🧠 AGENT RAPORU — Compound Engine Ailesi (Claude Opus 4.8)

Bu rapor, `bot_kararli/dengeli/optimal/rejim/quantpro` ailesinin nasıl ortaya çıktığını
ve **acımasız gerçeklerini** içerir. ~40 deneyin damıtılmış sonucu. Hayal yok.

## 🧬 Algoritma Evrimi (ne işe yaradı, ne yaramadı)

| Aşama | Denenen | Sonuç |
|---|---|---|
| 1. Yön tahmini | XGBoost ile long/short tahmini | ❌ yazı-tura (AUC ~0.52) |
| 2. Kalite-filtresi | ML'i yön değil, "gerçek vs sahte trend" kapısı yap | ✅ WR %40→%44-48 |
| 3. Çıkış | trailing/pyramiding ("kazananı katla") | ❌ whipsaw, −%36…−%72 |
| 4. Çıkış (düzelt) | sabit +%5 TP / −%2.5 SL | ✅ asimetri = edge |
| 5. Sizing | martingale ("kaybedince büyüt") | ❌ İFLAS (8-13 ardışık kayıp) |
| 6. Sizing (düzelt) | güven-bazlı Kelly (≤2.5x tavan) | ✅ MAR 1.84→2.49 |
| 7. Rejim | boğa/ayı otomatik strateji seçimi | ✅ MAR 2.74 (EN İYİ) |
| 8. Kurumsal | CPCV + SHAP stability | ✅ daha dürüst OOS + serap feature ele |

**Elenen ~30 fikir:** daha hızlı TF (1H net −%56), 20-coin, eşzamanlı pozisyon, mikroyapı
2.türev (orderflow exhaustion — NULL), MTF feature, ikinci-kol (mean-reversion), TP%2/SL%10
(geometri yanılsaması), 10x-lottery (0/12), DD-contingent (tek-poz'da MAR düşürdü).

## 🔑 Kanıtlanan Tek Gerçek Edge
```
Donchian40+SuperTrend → XGBoost kalite-kapısı → TP+5%/SL-2.5% → güven-bazlı sizing
```
**Edge = asimetri (2:1) + ML kalite-filtresi + disiplin.** Yön-isabeti DEĞİL (yön ~%52).
WR tavanı ~%45-48; "%80 isabet" bu piyasada YOK (test edildi, geometri artefaktı).

## ⚠️ ACIMASIZ GERÇEKLER (bot_xasset disiplini ile)
1. **Deflated Sharpe ~%31.** ~40 deney yaptık → "kazanan" config selection-bias taşıyor.
   CPCV (15 bağımsız yol) **medyan ~%8** [%-16, %+64], P(>0) %73. Walk-forward'ın +%31'i iyimser.
2. **Bu aile DSR/PBO kapısını tam GEÇMEDİ.** En titiz-doğrulanmış sistem `bot_xasset`
   (DSR 0.99, PBO 0.03, Sharpe 2.40) — bu aile değil. Compound/MAR'da iyi ama güven daha düşük.
3. **Boğada zayıf:** güçlü tek-yönlü boğada (BTC +%161) sistem −%11, al-tut +%252.
   `bot_rejim` bunu rejim-tespitiyle yumuşatır ama tamamen çözmez.
4. **1H stop-slippage/gap modellenmedi.** Canlıda maliyet biraz daha yüksek.
5. **Martingale ASLA.** Bu ailenin hiçbiri kaybedince büyütmez (anti-martingale/güven-bazlı).

## 🎯 Hüküm
- **Compound/risk-ayarlı açıdan en iyi: `bot_rejim` (MAR 2.74).**
- **En titiz-doğrulanmış (tüm aileler arası): `bot_xasset`** (bu aile değil — dürüstlük).
- **Hepsi PAPER-TRADE adayı.** İlk gerçek iş: `shadow_papertrade.py` ile forward doğrulama,
  backtest'i tutarsa küçük sermaye. Kör deploy = para yakma.

Detaylı tüm araştırma: `../../INTELLIGENCE.md`.
