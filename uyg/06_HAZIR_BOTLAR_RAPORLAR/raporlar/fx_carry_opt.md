# FOREX OPTIMAL SİNYAL — FX carry optimizasyonu (tek gerçek FX faktörü)

7 G10 parite, maliyet 6bps, train<2025/OOS 2025-26. Carry-crash için trend-filtresi.

| Varyant | IS Sharpe | OOS Sharpe | OOS CAGR | OOS MaxDD | +yıl |
|---|---|---|---|---|---|
| A: raw carry | 0.28 | 0.92 | 7% | -7% | 9/12 |
| B: carry-to-vol | 0.14 | 0.92 | 7% | -7% | 8/12 |
| C: carry+trend-filtre | -0.48 | -0.34 | -2% | -7% | 2/12 |
| D: C+vol-hedef %10 | -0.43 | -0.60 | -7% | -12% | 2/12 |

## Yorum (dürüst)

**En iyi varyant bile zayıf (IS 0.28/OOS 0.92, 9/12 yıl).** FX carry literatür-tipik (~0.5 Sharpe, kriz-kuyruğu) ama prop için yetersiz ve kırılgan. Trend-filtresi yardım ettiyse C/D en az kötü. Dürüst: forex'te modest carry dışında satılabilir edge yok; sinyal olarak verilebilir ama beklenti düşük tutulmalı.
- ⚠️ Carry kriz-kuyruğu taşır (risk-off'ta sert düşüş); trend-filtresi azaltır ama silmez. Tek-dönem OOS; faiz verisi yaklaşık-yıllık; gerçek FX/CFD swap firma-bazlı farklı.