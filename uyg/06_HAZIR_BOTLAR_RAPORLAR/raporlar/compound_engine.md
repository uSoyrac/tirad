# COMPOUND MOTORU — kâr-al-çık → yeniden-deploy (GERÇEK edge: combo, OOS Sharpe ~1.85)

OOS 273 gün. Compound = realize + büyümüş bankroll'la tekrar deploy. fractional-Kelly + kill-switch (−%20 DD'de risk yarıla). $1000 başlangıç.

## Tek hesap — compound seviyesine göre

| sizing | terminal $ | CAGR | MaxDD | Sharpe |
|---|---|---|---|---|
| flat (compound yok, ~1x) | $1,411 | +58% | -12% | 2.23 |
| ¼-Kelly compound | $1,665 | +98% | -18% | 2.21 |
| ½-Kelly compound | $2,174 | +182% | -29% | 1.96 |
| full-Kelly (riskli) | $3,922 | +522% | -43% | 2.09 |

## Çok-kol (aynı zekâ, 2 hesap: prop + binance, her biri ¼-Kelly)

- Tek hesap ¼-Kelly: $1,665  →  2 hesap toplam: **$3,331** (lineer ölçek)
- (prop = başkasının sermayesi/split; binance = kendi sermaye — ikisi de aynı combo sinyali)

## Yorum (dürüst)

- **Compound senin vizyonunu GERÇEK edge'de büyütüyor:** ¼-Kelly ile flat'ten belirgin yüksek terminal servet, kill-switch DD'yi sınırlar. Kâr-al-çık = her gün büyümüş bankroll'la yeniden-deploy (mekaniği bu).
- **Kelly fraksiyonu = risk kadranı:** ¼ güvenli-agresif, ½ agresif (yüksek DD), full = ruin riski (fat-tail). Combo gerçek edge olduğu için compound MEŞRU; trend olsaydı patlardı.
- ⚠️ f* OOS-μ ile şişkin (survivorship + 2025-26 iyi) → gerçek f* düşük; **≤¼-Kelly tavanı.** Çok-kol lineer ölçek (her hesap ayrı edge çalıştırır); prop'ta split %70-80, binance'te %100.
- **Mimari: tek combo sinyali → compound motoru (Kelly+kâr-al+kill-switch) → N hesap.** Her hesap kendi firma kuralına/sermayesine göre boyutlanır; motor paylaşılır.