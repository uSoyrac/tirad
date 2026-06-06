# Çok-Kollu Compound Trading Operasyonu — Tasarım

## Vizyon
Tek zekâ-çekirdeği → 2 track → compound motoru. "Kâr-al-çık → bankroll'a ekle →
yeniden-deploy" = geometrik büyüme. (Kullanıcının baştan beri istediği.)

## Mimari
ZEKÂ ÇEKİRDEĞİ (paylaşılan, mevcut): combo sinyali = cross-sectional momentum Top-3 +
funding-positioning carry + meta-model + rejim bağlamı → her coin için yön + conviction.
DSR 1.00 / PBO 0.01, OOS Sharpe ~1.85. (Trend/HH-LL DEĞİL — 7 test, hepsi OOS-negatif/chop-felaket.)

TRACK 1 — PROP (başkasının sermayesi): HyroTrader (crypto, Türkiye-OK, API+testnet) +
Trade The Pool (hisse, Türkiye-OK, Signal Stack). Firma kurallarına boyutlandır (bot_hyro,
equity_signal). Compound = tekrarlı payout (split %70-80).

TRACK 2 — BİNANCE (kendi sermaye, max büyüme): combo + compound motoru tam devrede,
%100 kâr. (live_bot.py altyapısı; testnet-önce.)

COMPOUND MOTORU (paylaşılan, run_compound_engine.py):
  1. Sinyalden pozisyon aç.
  2. Kâr-al kuralı: hedefte realize et (chop-dayanıklı; combo'nun doğal rebalance'ı + opsiyonel hızlı-TP).
  3. fractional-Kelly boyutlandırma: conviction × ≤¼-Kelly, büyümüş bankroll üzerinden → geometrik.
  4. Kill-switch: −%20 DD'de risk yarıla (compound'un emniyet kemeri; gerçek edge'de büyür, DD'yi de büyütür).

## Doğrulanmış sayılar (OOS 2025-26, $1000)
flat +58% · ¼-Kelly +98% (DD −18%) · ½-Kelly +182% (DD −29%). 2 hesap (track1+2) ¼-Kelly → ~2x.
≤¼-Kelly tavanı (f* survivorship-şişkin). Çok-kol lineer ölçek.

## Neyin İÇİNDE DEĞİL (dürüstçe elendi)
Yönsel/yapısal trend (Donchian/Supertrend/HH-LL): trend-yıllarında kârlı, chop'ta felaket (2025
−%49), combo'yu bozar (2.23→1.11). Compound TREND'i değil COMBO'yu büyütür. Futures: edge yok.
Forex-ex-carry: edge yok.

## Yürütme
Sinyaller dashboard'da: /sinyal (crypto) · /hisse (hisse) · /forex (FX-carry). Compound motoru
her track'in boyutlandırmasını yönetir. Canlı emir öncesi kullanıcı onayı + testnet-önce (non-negotiable).

## Riskler / sınırlar
2025-26 cömert rejim (haircut uygula). f* şişkin → ≤¼-Kelly. Compound DD'yi büyütür → kill-switch şart.
Prop firma bölge/KYC (HyroTrader/TTP Türkiye-OK; FundingPips/Breakout yasaklı). Forward kanıt eksik.
