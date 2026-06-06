# CONVICTION-GATE prop test — size UP on high-conviction combo days?

HyroTrader 2-step (P1+10%/P2+5%, daily−5%, total−10% trailing). Base vol 12%, haircut ×0.6, 20000 bootstrap paths. Conviction FIT on IS (<2025), APPLIED OOS.

## Baseline (constant-vol, no conviction gate)

- IS P(pass) **27%** | OOS P(pass) **63%** | OOS ann-vol 15%

## Conviction-gated (threshold = IS median; scale pair IS-selected)

| Feature | (lo,hi) scale | IS P(pass) | OOS P(pass) | OOS ann-vol | vs base OOS |
|---|---|---|---|---|---|
| mom10 | (0.5, 1.5) | 32% | **75%** | 19% | +13pt |
| agree | (0.5, 1.5) | 29% | **67%** | 22% | +4pt |
| trendstr | (0.0, 2.0) | 39% | **68%** | 24% | +5pt |
| calm | (1.0, 1.0) | 27% | **62%** | 15% | -0pt |

## Vol-matched honesty check

- Best gate = **mom10** scale (0.5, 1.5): OOS P(pass) 75% at 19% ann-vol.
- Constant-vol baseline RESCALED to the same 19% ann-vol: OOS P(pass) **58%**.
- Conviction-timing lift OVER vol-matched baseline: **+17 pt** (if ~0, the 'gain' is just higher vol, NOT conviction).

- Multi-seed (10) vol-matched timing lift for `mom10`: mean +18pt, min +18pt, max +18pt.

## VERDICT (honest)

- **IS vol-matched timing lift +1pt vs OOS +18pt** — the discriminator.

## VERDICT (honest)

- NOT a real conviction edge: vs a VOL-MATCHED baseline the lift is +1pt IN-SAMPLE but +18pt OOS. That huge IS/OOS gap = REGIME LUCK: 2025-26 was a persistent crypto uptrend where trailing-momentum sizing rode winners; in the choppy IS window conviction sizing adds ~0 over the same vol level. The headline OOS 75% is the higher effective vol (19% vs 15% baseline) + a kind regime, NOT a structural entry-quality edge. Consistent with CLAUDE.md: path/conviction shaping does not beat constant-vol; the only real pass lever is the VOL LEVEL.
- ⚠️ OOS 2025-26 is a favorable regime; haircut ×0.6; survivorship-capped universe; EOD-only (intraday −5% breach understated). Sleeve-level returns only (no per-name data in _sleeves3), so 'trade only strongest names' could NOT be tested directly — this tests conviction sizing of the book, which is the deployable form of the lever.