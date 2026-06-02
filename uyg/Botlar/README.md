# 🤖 BOTLAR — Doğrulanmış Optimal Trading Botları

Bu klasör, projedeki **tüm araştırmanın damıtılmış sonucu** olan, walk-forward
doğrulanmış 3 botu içerir. Hepsi aynı **doğrulanmış edge'i** kullanır
(Donchian40 + SuperTrend → XGBoost kalite-kapısı → TP+5%/SL−2.5%); **fark sadece sizing**
(risk yelpazesi). Detaylı istihbarat: `../../INTELLIGENCE.md`.

## Botlar (risk yelpazesi)

| Bot | Sizing | $250→ | CAGR | MaxDD | MAR | Kime |
|---|---|---|---|---|---|---|
| **bot_kararli.py** | düz %60 | $480 | +%31 | %17 | 1.84 | En stabil, düşük drawdown |
| **bot_dengeli.py** | düz 1.25x | ~$786 | +%60 | ~%30 | ~2.0 | Denge |
| **bot_optimal.py** ⭐ | güven-bazlı (≤2.5x) | $1003 | +%77.7 | %31 | **2.50** | En iyi risk-ayarlı |

(OOS 2024-2026 walk-forward, gerçekçi maliyet, tek-pozisyon, top5 1H)

## Çalıştırma
```bash
cd uyg/Botlar
python3 bot_kararli.py     # veya bot_dengeli.py / bot_optimal.py
```
İlk çalıştırma birkaç dakika (sinyaller + walk-forward model); sonra cache'li.

## Gereksinimler
- Python paketleri: `xgboost scikit-learn pandas numpy ta scipy`
- Veri: `bot/engine/data_v31/*.csv` (1H OHLCV, repo'da mevcut)
- Bağımlılık: `uyg/src/` (signal_lab, live_strategy, compound_engine — repo'da mevcut)

## ⚠️ ACIMASIZ GERÇEKLER (oku, yoksa para kaybedersin)
1. **Bunlar BACKTEST.** Deflated Sharpe ~%31 → edge istatistiksel olarak kesin değil
   (~40 deney selection-bias). Gerçek parada önce **PAPER-TRADE** (1-2 ay), backtest'le
   tutarsa küçük gerçek sermaye.
2. **Kaldıraç = dayanabileceğin MaxDD.** Kelly tepesi 2.5x; ÖTESİ compound'u DÜŞÜRÜR (drag).
3. **Martingale YASAK.** "Kaybedince büyüt" = iflas (8-13 ardışık kayıp gerçeği).
   Bu botların hiçbiri martingale kullanmaz; sizing GÜVEN-bazlıdır (anti-martingale).
4. **Edge = asimetri + ML kalite-filtresi + disiplin**, yön-tahmini DEĞİL (yön ~%52 = yazı-tura).
5. Compound gerçeği: ~%31-78 CAGR (sizing'e göre), yıllarla. "Ayda 100→1000" = yok.

## ❌ Bunları KULLANMA (test edildi, çürütüldü)
`bot/engine/run_v62-v72` (martingale/10x/holy_grail), TP%2-SL%10, pyramiding,
orderflow 2.türev, çoklu-pozisyon → hepsi ya iflas ya inferior ya null. Detay INTELLIGENCE.md.
