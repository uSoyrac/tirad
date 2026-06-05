# HH/LL PİYASA YAPISI (pivot k=5, BoS) — dip/tepe yakalama

20 coin, swing-pivot + break-of-structure, long+short. Maliyet 7bps.

## Tek başına

| pencere | Sharpe | CAGR | MaxDD |
|---|---|---|---|
| Tüm | 0.09 | -11% | -78% |
| IS (≤2024) | 0.39 | +5% | -74% |
| OOS (2025-26) | -0.85 | -46% | -65% |

## Yıl-bazı

| yıl | Sharpe | getiri |
|---|---|---|
| 2021 | 0.23 | -12% |
| 2022 | -0.14 | -27% |
| 2023 | 1.00 | +39% |
| 2024 | 0.90 | +39% |
| 2025 | -0.91 | -49% |
| 2026 | -0.67 | -17% |

## Combo'ya sleeve olarak (Donchian trend bozmuştu — yapı farklı mı?)

- hhll korelasyon: {'crypto_trend': 0.28, 'crypto_funding': 0.03, 'hhll': 1.0}
- combo OOS Sharpe: **2.23** → +hhll: **1.11**

## Yorum (dürüst)

**HH/LL zayıf: tek-başına OOS -0.85, combo 2.23→1.11.** Yapı-takibi de trend-takip ailesinden — chop'ta sahte-kırılım whipsaw'ı. Donchian/Supertrend ile aynı kader. Dip/tepe 'yakalama' gecikmeli pivot yüzünden geç + chop'ta yanıltıcı.
- ⚠️ pivot k=5 bar gecikmeli (tepeyi k-bar sonra onaylar). Farklı k denenebilir; tek-dönem; yapı-takibi de rejim-bağımlı olabilir.