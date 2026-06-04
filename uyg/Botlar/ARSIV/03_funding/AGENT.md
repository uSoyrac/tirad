# AGENT.md — 03_funding

**Ne:** Market-nötr cross-sectional funding-pozisyonlama (yüksek-funding short / düşük long).
Kanonik: `uyg/Botlar/bot_funding.py`. Veri: 3 borsa funding (`uyg/src/funddata`,`xfunddata`).

**Durum:** OOS Sharpe 1.31, ortogonal (combo'ya korelasyon −0.06). Paper adayı.

**Önemli:** Getiri fiyat-pozisyonlamadan gelir, saf carry'den değil (saf delta-nötr harvest
OOS negatif — `quantlab/reports_out/carry_robustness.md`). **YAPMA:** parametrelerini
WF-optimize etme (overfit). En iyi rolü: xasset/combo içinde ortogonal kol. Kanıt:
`quantlab/reports_out/{carry_binance,carry_robustness}.md`.
