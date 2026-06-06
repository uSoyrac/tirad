# PROP-PASS sizing maximization — best constant vol vs best adaptive path-shaping

Edge = 2-sleeve combo (crypto_trend+crypto_funding, inverse-vol). Raw ALL-pool ann Sharpe 1.69; haircut x0.6 -> sim Sharpe ~1.01. Block-bootstrap (block=5, 25000 paths, seed 20260606), positive skew preserved. EOD-only (intraday breach risk understated -> DAILY_GOV models a self-halt).

## Card: ONE-STEP (target(s) 10%, daily -4%, total -6% TRAILING)

### Residual pool: OOS

- **Best CONSTANT vol = 11% -> P(pass) = 42.8%** (the ceiling).
- Best adaptive per family (own params optimized):
  - RAMP_UP: P=44.6% (params (0.16, 0.08, 0.02))
  - DERISK: P=42.9% (params (0.12, 0.16, 0.02))
  - LOCK_NEAR: P=30.9% (params 0.25)
  - DAILY_GOV: P=42.8% (params (np.float64(0.11), -0.025))
- CONST vol curve (P% by vol): 5%:15  7%:31  9%:40  11%:43  13%:42  15%:41  17%:40  19%:39  21%:38  23%:37  25%:36  27%:36  29%:35

### Residual pool: IS

- **Best CONSTANT vol = 12% -> P(pass) = 47.2%** (the ceiling).
- Best adaptive per family (own params optimized):
  - RAMP_UP: P=47.2% (params (0.12, 0.12, 0.02))
  - DERISK: P=47.7% (params (0.24, 0.08, 0.04))
  - LOCK_NEAR: P=32.1% (params 0.26)
  - DAILY_GOV: P=49.3% (params (np.float64(0.13), -0.025))
- CONST vol curve (P% by vol): 5%:10  7%:28  9%:41  11%:47  13%:47  15%:45  17%:43  19%:42  21%:42  23%:41  25%:38  27%:34  29%:35

### Residual pool: ALL

- **Best CONSTANT vol = 12% -> P(pass) = 44.0%** (the ceiling).
- Best adaptive per family (own params optimized):
  - RAMP_UP: P=44.0% (params (0.12, 0.12, 0.02))
  - DERISK: P=44.0% (params (0.12, 0.12, 0.02))
  - LOCK_NEAR: P=30.6% (params 0.27)
  - DAILY_GOV: P=44.8% (params (np.float64(0.12), -0.025))
- CONST vol curve (P% by vol): 5%:12  7%:28  9%:39  11%:44  13%:43  15%:42  17%:40  19%:40  21%:39  23%:38  25%:36  27%:36  29%:34

## Card: TWO-STEP (target(s) 10%/5%, daily -5%, total -10% TRAILING)

### Residual pool: OOS

- **Best CONSTANT vol = 15% -> P(pass) = 44.9%** (the ceiling).
- Best adaptive per family (own params optimized):
  - RAMP_UP: P=45.6% (params (0.24, 0.12, 0.02))
  - DERISK: P=44.7% (params (0.16, 0.16, 0.02))
  - LOCK_NEAR: P=25.1% (params 0.29)
  - DAILY_GOV: P=44.9% (params (np.float64(0.15), -0.025))
- CONST vol curve (P% by vol): 5%:7  7%:20  9%:32  11%:40  13%:44  15%:45  17%:44  19%:43  21%:41  23%:40  25%:38  27%:37  29%:36

### Residual pool: IS

- **Best CONSTANT vol = 16% -> P(pass) = 53.1%** (the ceiling).
- Best adaptive per family (own params optimized):
  - RAMP_UP: P=53.4% (params (0.12, 0.16, 0.06))
  - DERISK: P=53.4% (params (0.16, 0.12, 0.06))
  - LOCK_NEAR: P=28.3% (params 0.3)
  - DAILY_GOV: P=59.2% (params (np.float64(0.25), -0.025))
- CONST vol curve (P% by vol): 5%:5  7%:18  9%:33  11%:43  13%:50  15%:53  17%:53  19%:51  21%:45  23%:45  25%:44  27%:44  29%:43

### Residual pool: ALL

- **Best CONSTANT vol = 16% -> P(pass) = 47.6%** (the ceiling).
- Best adaptive per family (own params optimized):
  - RAMP_UP: P=47.6% (params (0.12, 0.16, 0.06))
  - DERISK: P=47.6% (params (0.16, 0.12, 0.06))
  - LOCK_NEAR: P=26.1% (params 0.3)
  - DAILY_GOV: P=49.9% (params (np.float64(0.18), -0.025))
- CONST vol curve (P% by vol): 5%:6  7%:18  9%:31  11%:40  13%:45  15%:48  17%:47  19%:46  21%:42  23%:42  25%:41  27%:40  29%:39

## Verdict (honest)

- **ONE-STEP (OOS pool):** best constant vol 11% -> P(pass)=42.8%; best adaptive (RAMP_UP) P=44.6% -> RAMP_UP beats constant by +1.7 pts.
- **TWO-STEP (OOS pool):** best constant vol 15% -> P(pass)=44.9%; best adaptive (RAMP_UP) P=45.6% -> RAMP_UP beats constant by +0.7 pts.

- The ONLY reliable lever is the VOL LEVEL: P(pass) rises with vol up to a peak, then falls as daily/total breaches dominate. Path-shaping (ramp/derisk/lock/governor) is compared at its OWN best params, not vs a fixed baseline.
- Why de-risk/lock typically can't beat constant: the target is HIGH vs the edge, so you must compound at full risk to reach it before time/path runs out; trailing total-DD floor rises with the peak so a built buffer doesn't lower breach risk.
- A DAILY_GOV (intraday -g% self-halt) is the one tweak that can help on EOD-understated daily risk: it converts would-be -5% closes into capped losses, letting you run slightly higher vol. Check the OOS numbers above for whether the lift clears noise on THIS edge.
- ALL/IS pools cross-check regime: OOS (2025-26) is the kind window; the IS/ALL ceiling is the more conservative deployable expectation.
- ⚠️ EOD-only understates -5%/-4% intraday daily breaches; 0.6 haircut; survivorship-capped universe; favorable OOS regime. 100% pass is impossible — these are ceilings.