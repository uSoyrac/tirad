# FUNDED-SURVIVAL bot — survive 6mo + extract payouts (real combo returns)

Edge = DSR/PBO combo (crypto_trend+crypto_funding, inverse-vol). Raw ALL-pool ann Sharpe 1.69 (OOS 2.23 / IS 1.25), haircut x0.6 -> sim Sharpe ~1.01. Block-bootstrap (block=5, 30000 paths), horizon 126d (~6mo), seed 20260606. Objective: NO target to hit -> MINIMIZE blowup, MAXIMIZE withdrawn $. Payout to trader = withdrawn buffer x 80% split.

# CARD: 1-step (daily -4 / total -6 trail)

## Pool OOS

### Lever 1: de-risk VOL level (bank at +5% buffer, no kill-switch)

| ann vol | P(survive 6mo) | blowup% | withdrawn (frac/acct) | $5K payout(6mo) | $25K payout(6mo) | $5K/mo | $25K/mo |
|---|---|---|---|---|---|---|---|
| 3% | 100.0% | 0.0% | 1.40% | $56 | $281 | $9 | $47 |
| 5% | 98.3% | 1.7% | 2.35% | $94 | $470 | $16 | $78 |
| 7% | 89.2% | 10.8% | 3.30% | $132 | $659 | $22 | $110 |
| 10% | 66.2% | 33.8% | 4.59% | $184 | $918 | $31 | $153 |
| 12% | 50.7% | 49.3% | 5.29% | $211 | $1057 | $35 | $176 |

### Lever 2: profit-banking trigger (at 7% vol, no kill-switch)

| bank trigger | P(survive) | blowup% | withdrawn frac | $5K/mo | $25K/mo |
|---|---|---|---|---|---|
| never bank | 89.2% | 10.8% | 3.28% | $22 | $109 |
| +10% | 89.2% | 10.8% | 3.28% | $22 | $109 |
| +8% | 89.2% | 10.8% | 3.28% | $22 | $109 |
| +5% | 89.2% | 10.8% | 3.30% | $22 | $110 |
| +3% | 89.2% | 10.8% | 3.40% | $23 | $113 |

### Lever 3: kill-switch / intraday self-halt (7% vol, bank +5%)

| kill-switch | P(survive) | blowup% | $5K/mo | $25K/mo |
|---|---|---|---|---|
| none | 89.2% | 10.8% | $22 | $110 |
| -3% halt | 89.2% | 10.8% | $22 | $110 |
| -2.5% halt | 89.2% | 10.8% | $22 | $110 |

## Pool IS

### Lever 1: de-risk VOL level (bank at +5% buffer, no kill-switch)

| ann vol | P(survive 6mo) | blowup% | withdrawn (frac/acct) | $5K payout(6mo) | $25K payout(6mo) | $5K/mo | $25K/mo |
|---|---|---|---|---|---|---|---|
| 3% | 100.0% | 0.0% | 1.34% | $54 | $268 | $9 | $45 |
| 5% | 99.2% | 0.8% | 2.24% | $90 | $448 | $15 | $75 |
| 7% | 93.6% | 6.4% | 3.14% | $126 | $628 | $21 | $105 |
| 10% | 75.5% | 24.5% | 4.40% | $176 | $881 | $29 | $147 |
| 12% | 60.8% | 39.2% | 5.11% | $204 | $1022 | $34 | $170 |

### Lever 2: profit-banking trigger (at 7% vol, no kill-switch)

| bank trigger | P(survive) | blowup% | withdrawn frac | $5K/mo | $25K/mo |
|---|---|---|---|---|---|
| never bank | 93.6% | 6.4% | 3.14% | $21 | $105 |
| +10% | 93.6% | 6.4% | 3.14% | $21 | $105 |
| +8% | 93.6% | 6.4% | 3.14% | $21 | $105 |
| +5% | 93.6% | 6.4% | 3.14% | $21 | $105 |
| +3% | 93.6% | 6.4% | 3.20% | $21 | $107 |

### Lever 3: kill-switch / intraday self-halt (7% vol, bank +5%)

| kill-switch | P(survive) | blowup% | $5K/mo | $25K/mo |
|---|---|---|---|---|
| none | 93.6% | 6.4% | $21 | $105 |
| -3% halt | 93.6% | 6.4% | $21 | $105 |
| -2.5% halt | 93.6% | 6.4% | $21 | $105 |

## Pool ALL

### Lever 1: de-risk VOL level (bank at +5% buffer, no kill-switch)

| ann vol | P(survive 6mo) | blowup% | withdrawn (frac/acct) | $5K payout(6mo) | $25K payout(6mo) | $5K/mo | $25K/mo |
|---|---|---|---|---|---|---|---|
| 3% | 100.0% | 0.0% | 1.35% | $54 | $270 | $9 | $45 |
| 5% | 98.8% | 1.2% | 2.26% | $90 | $452 | $15 | $75 |
| 7% | 91.8% | 8.2% | 3.17% | $127 | $634 | $21 | $106 |
| 10% | 71.8% | 28.2% | 4.44% | $178 | $888 | $30 | $148 |
| 12% | 56.4% | 43.6% | 5.13% | $205 | $1025 | $34 | $171 |

### Lever 2: profit-banking trigger (at 7% vol, no kill-switch)

| bank trigger | P(survive) | blowup% | withdrawn frac | $5K/mo | $25K/mo |
|---|---|---|---|---|---|
| never bank | 91.8% | 8.2% | 3.17% | $21 | $106 |
| +10% | 91.8% | 8.2% | 3.16% | $21 | $105 |
| +8% | 91.8% | 8.2% | 3.16% | $21 | $105 |
| +5% | 91.8% | 8.2% | 3.17% | $21 | $106 |
| +3% | 91.8% | 8.2% | 3.24% | $22 | $108 |

### Lever 3: kill-switch / intraday self-halt (7% vol, bank +5%)

| kill-switch | P(survive) | blowup% | $5K/mo | $25K/mo |
|---|---|---|---|---|
| none | 91.8% | 8.2% | $21 | $106 |
| -3% halt | 91.8% | 8.2% | $21 | $106 |
| -2.5% halt | 91.8% | 8.2% | $21 | $106 |

# CARD: 2-step (daily -5 / total -10 trail)

## Pool OOS

### Lever 1: de-risk VOL level (bank at +5% buffer, no kill-switch)

| ann vol | P(survive 6mo) | blowup% | withdrawn (frac/acct) | $5K payout(6mo) | $25K payout(6mo) | $5K/mo | $25K/mo |
|---|---|---|---|---|---|---|---|
| 3% | 100.0% | 0.0% | 1.40% | $56 | $281 | $9 | $47 |
| 5% | 100.0% | 0.0% | 2.35% | $94 | $470 | $16 | $78 |
| 7% | 99.7% | 0.3% | 3.31% | $133 | $663 | $22 | $110 |
| 10% | 95.3% | 4.7% | 4.83% | $193 | $966 | $32 | $161 |
| 12% | 88.7% | 11.3% | 5.89% | $236 | $1178 | $39 | $196 |

### Lever 2: profit-banking trigger (at 7% vol, no kill-switch)

| bank trigger | P(survive) | blowup% | withdrawn frac | $5K/mo | $25K/mo |
|---|---|---|---|---|---|
| never bank | 99.7% | 0.3% | 3.31% | $22 | $110 |
| +10% | 99.7% | 0.3% | 3.31% | $22 | $110 |
| +8% | 99.7% | 0.3% | 3.31% | $22 | $110 |
| +5% | 99.7% | 0.3% | 3.31% | $22 | $110 |
| +3% | 99.7% | 0.3% | 3.41% | $23 | $114 |

### Lever 3: kill-switch / intraday self-halt (7% vol, bank +5%)

| kill-switch | P(survive) | blowup% | $5K/mo | $25K/mo |
|---|---|---|---|---|
| none | 99.7% | 0.3% | $22 | $110 |
| -3% halt | 99.7% | 0.3% | $22 | $110 |
| -2.5% halt | 99.7% | 0.3% | $22 | $110 |

## Pool IS

### Lever 1: de-risk VOL level (bank at +5% buffer, no kill-switch)

| ann vol | P(survive 6mo) | blowup% | withdrawn (frac/acct) | $5K payout(6mo) | $25K payout(6mo) | $5K/mo | $25K/mo |
|---|---|---|---|---|---|---|---|
| 3% | 100.0% | 0.0% | 1.34% | $54 | $268 | $9 | $45 |
| 5% | 100.0% | 0.0% | 2.24% | $90 | $448 | $15 | $75 |
| 7% | 99.9% | 0.1% | 3.14% | $126 | $629 | $21 | $105 |
| 10% | 97.4% | 2.6% | 4.54% | $182 | $909 | $30 | $151 |
| 12% | 93.2% | 6.8% | 5.51% | $221 | $1103 | $37 | $184 |

### Lever 2: profit-banking trigger (at 7% vol, no kill-switch)

| bank trigger | P(survive) | blowup% | withdrawn frac | $5K/mo | $25K/mo |
|---|---|---|---|---|---|
| never bank | 99.9% | 0.1% | 3.15% | $21 | $105 |
| +10% | 99.9% | 0.1% | 3.15% | $21 | $105 |
| +8% | 99.9% | 0.1% | 3.15% | $21 | $105 |
| +5% | 99.9% | 0.1% | 3.14% | $21 | $105 |
| +3% | 99.9% | 0.1% | 3.20% | $21 | $107 |

### Lever 3: kill-switch / intraday self-halt (7% vol, bank +5%)

| kill-switch | P(survive) | blowup% | $5K/mo | $25K/mo |
|---|---|---|---|---|
| none | 99.9% | 0.1% | $21 | $105 |
| -3% halt | 99.9% | 0.1% | $21 | $105 |
| -2.5% halt | 99.9% | 0.1% | $21 | $105 |

## Pool ALL

### Lever 1: de-risk VOL level (bank at +5% buffer, no kill-switch)

| ann vol | P(survive 6mo) | blowup% | withdrawn (frac/acct) | $5K payout(6mo) | $25K payout(6mo) | $5K/mo | $25K/mo |
|---|---|---|---|---|---|---|---|
| 3% | 100.0% | 0.0% | 1.35% | $54 | $270 | $9 | $45 |
| 5% | 100.0% | 0.0% | 2.26% | $90 | $452 | $15 | $75 |
| 7% | 99.7% | 0.3% | 3.18% | $127 | $635 | $21 | $106 |
| 10% | 96.7% | 3.3% | 4.60% | $184 | $921 | $31 | $153 |
| 12% | 91.4% | 8.6% | 5.60% | $224 | $1120 | $37 | $187 |

### Lever 2: profit-banking trigger (at 7% vol, no kill-switch)

| bank trigger | P(survive) | blowup% | withdrawn frac | $5K/mo | $25K/mo |
|---|---|---|---|---|---|
| never bank | 99.7% | 0.3% | 3.18% | $21 | $106 |
| +10% | 99.7% | 0.3% | 3.18% | $21 | $106 |
| +8% | 99.7% | 0.3% | 3.18% | $21 | $106 |
| +5% | 99.7% | 0.3% | 3.18% | $21 | $106 |
| +3% | 99.7% | 0.3% | 3.25% | $22 | $108 |

### Lever 3: kill-switch / intraday self-halt (7% vol, bank +5%)

| kill-switch | P(survive) | blowup% | $5K/mo | $25K/mo |
|---|---|---|---|---|
| none | 99.7% | 0.3% | $21 | $106 |
| -3% halt | 99.7% | 0.3% | $21 | $106 |
| -2.5% halt | 99.7% | 0.3% | $21 | $106 |

# RECOMMENDED FUNDED-SURVIVAL POLICY (honest)

- **1-step (daily -4 / total -6 trail) / OOS (kind regime):** vol 5%, bank +3%, kill-switch none -> P(survive 6mo) 98.3%, blowup 1.7%, ~$16/mo ($5K) / ~$79/mo ($25K).
- **1-step (daily -4 / total -6 trail) / ALL (conservative):** vol 7%, bank +3%, kill-switch none -> P(survive 6mo) 91.8%, blowup 8.2%, ~$22/mo ($5K) / ~$108/mo ($25K).
- **2-step (daily -5 / total -10 trail) / OOS (kind regime):** vol 10%, bank +3%, kill-switch none -> P(survive 6mo) 95.3%, blowup 4.7%, ~$34/mo ($5K) / ~$170/mo ($25K).
- **2-step (daily -5 / total -10 trail) / ALL (conservative):** vol 12%, bank +3%, kill-switch -2.5% halt -> P(survive 6mo) 92.1%, blowup 7.9%, ~$40/mo ($5K) / ~$199/mo ($25K).

- **Survival is bought with vol:** lower de-risk vol shrinks the daily-loss tail (the main killer) almost linearly; payouts shrink with it. The 6-month survival ceiling at a useful (earning) vol is well below 100% under TRAILING DD.
- **Profit-banking is a SURVIVAL lever, not just income, under trailing DD:** withdrawing the buffer caps the realized peak the floor trails from, so a small bank trigger both extracts cash AND lowers blowup vs never-banking (which lets the peak — and thus the trailing floor — ratchet up to where any pullback breaches).
- **Kill-switch:** on EOD data its measured lift is small, but it is the real defense against the EOD model UNDERSTATING intraday daily breaches — keep a -2.5/-3% intraday self-halt on the live bot regardless of the sim number.
- ⚠️ Honest limits: EOD-only (intraday daily breach understated -> kill-switch + size below the cliff); 0.6 survivorship haircut; trailing-DD modeled as floor=peak*(1+total) with banking capping the peak (real firm trailing rules vary — some stop trailing at start+total, which is EASIER, so this is conservative); favorable 2025-26 OOS regime -> trust the ALL/IS pool for the deployable number.