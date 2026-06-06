# FİRMA × YAPI prop geçiş Monte-Carlo (Türkiye-uygun; Breakout HARİÇ)

Block-bootstrap (5-gün blok), 30000 yol, haircut ×0.6. Her firma KENDİ uygulanabilir edge'inde: HyroTrader=combo(crypto), TradeThePool=us_momentum(hisse).

Sim Sharpe (yıllık, haircut'lı) edge başına: combo full 1.01, us full 0.94

## P(geç) — firma/yapı × vol-hedef (FULL-örneklem bootstrap)

| Firma/yapı | DD | vol 6% | vol 8% | vol 10% | vol 12% | vol 15% |
|---|---|---|---|---|---|---|
| HyroTrader 1-step (trailing 6%) | trailing 6% | **21%** | **35%** | **42%** | **44%** | **42%** |
| HyroTrader 2-step (trailing 10%) | trailing 10% | **4%** | **12%** | **22%** | **31%** | **41%** |
| TradeThePool +6% (static 4% / daily 2%) | static 4% | **60%** | **58%** | **59%** | **52%** | **44%** |
| TradeThePool +8% (static 6% / daily 3%) | static 6% | **47%** | **61%** | **66%** | **62%** | **62%** |
| TradeThePool +10% (static 10% / daily 5%) | static 10% | **32%** | **51%** | **62%** | **69%** | **73%** |

## Rejim-dürüstlüğü: IS-bootstrap vs OOS-bootstrap (her firmanın en iyi vol'ü)

| Firma/yapı | en iyi vol | P(geç) FULL | P(geç) IS-only | P(geç) OOS-only |
|---|---|---|---|---|
| HyroTrader 1-step (trailing 6%) | 12% | 44% | 40% | 50% |
| HyroTrader 2-step (trailing 10%) | 15% | 41% | 35% | 48% |
| TradeThePool +6% (static 4% / daily 2%) | 6% | 60% | 62% | 62% |
| TradeThePool +8% (static 6% / daily 3%) | 10% | 66% | 69% | 67% |
| TradeThePool +10% (static 10% / daily 5%) | 15% | 73% | 74% | 73% |

## En iyi config

- **TradeThePool +10% (static 10% / daily 5%) @ vol 15% → P(geç) 73% (full-bootstrap).**
- Bu config'te bir EOD günü ≤−%3 olma olasılığı: **34%** (intraday'in günlük 5% uçurumunu kırma proxy'si; düşükse güvenli marj).

## Yorum (dürüst)

- **STATİK DD (Trade The Pool) trailing'i (HyroTrader) geçiş-kolaylığında yener:** zirveden geri-çekilme cezalandırılmaz, floor sabit → hedefe daha rahat tırmanırsın. TTP'nin küçük hedefi (+%6/+%8) de combo'nun +%10'undan kolay.
- **AMA edge eşleşmesi şart:** TTP yalnız us_momentum'da geçerli (hisse), HyroTrader combo'da (crypto perp+funding). İki ayrı bot, iki ayrı edge — birini diğerinin rakamıyla karıştırma.
- **Vol kaldıracı:** hedef sabitken vol↑ → P(geç)↑ ama günlük-uçurum/DD riski de↑. TTP'nin SIKI günlük −%2'si düşük vol'ü zorlar; HyroTrader'ın −%4/−%5'i daha toleranslı.
- ⚠️ **Rejim:** OOS-bootstrap (müşfik 2025-26) IS-bootstrap'ten yüksek geçiş verir; gerçek beklenti IS-seviyesi ya da altı. Yukarıdaki FULL kolonu ikisinin ortası.
- ⚠️ **Survivorship:** her iki evren de bugünün hayatta-kalanları (crypto 27-coin, US büyük-cap). Büyüklük şişkin; literatür haircut (~%15-22/yıl) MAGNITUDE'a uygulanmalı.
- ⚠️ **Intraday:** EOD veri günlük-kayıp uçurumunu HAFİFE alır. −%3 self-stop bota kodlanmalı (intraday −daily limite asla değme).
- ⚠️ **%100 geçiş imkânsız:** dürüst tavan yukarıdaki rakam; geri kalanı blowup/yetişememe.