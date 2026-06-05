# quantlab — project rules (lean & durable)

Multi-agent crypto **trend research** system. North-star metric: **risk-adjusted
expectancy OUT-OF-SAMPLE**. Not raw signal count, not in-sample return.

## Non-negotiables (these make the backtest tell the truth)
1. **No look-ahead.** Features at bar `t` use only data `<= t`. The harness executes
   a signal decided on bar `t` at bar **`t+1`'s open** (`signal.shift(1)`), and uses
   the **previous** bar's ATR for stops/sizing. `tests/test_no_lookahead.py` guards this.
2. **Realistic costs.** Every fill pays slippage + fee. Perp positions accrue funding
   and can be **liquidated** — a liquidation is a real bankroll loss, never skipped.
3. **Validation discipline.** Optimise on the training window only; evaluate on a
   held-out OOS window the model never saw. Walk-forward. Always report in-sample vs
   OOS **side by side**; a large gap = overfitting and must be called out.
4. **Honest metrics every run:** total return, CAGR, win rate, avg win/loss,
   expectancy, Sharpe, Sortino, max drawdown, longest losing streak, risk-of-ruin.
   Report the bad numbers too.
5. **Sizing is separate from signals.** Fixed-fractional risk only
   (`risk/sizing.py`). **No martingale / loss-doubling.** If requested, show its
   risk-of-ruin curve first.

## Ask before
- Any live-exchange / real order-execution code.
- Adding leverage > 1 or shorting on a **spot** market (forced to 1x, no liq).

## Layout
- `config.py` + `config/default.yaml` — single source of truth (pydantic).
- `data/` — ccxt fetch (`fetch.py`) + offline-safe parquet cache (`cache.py`).
- `backtest/` — `harness.py` (event-driven engine), `costs.py`, `metrics.py`, `splits.py`.
- `risk/sizing.py` — fixed-fractional sizing.
- `baselines/` — buy-and-hold + Supertrend (the floors to beat).
- `reports/` — side-by-side in-sample vs OOS tables.
- `scripts/run_baseline.py` — Phase 0 end-to-end.

## How to run
```bash
.venv/bin/python -m pytest -q            # tests must pass
.venv/bin/python scripts/run_baseline.py # produces reports_out/phase0_baseline.md
```

## Conventions
- Python 3.12 (`.venv`). pandas/numpy/pydantic v2. No `pandas-ta`; use `ta` or pure numpy.
- Canonical OHLCV: tz-naive UTC `DatetimeIndex` named `ts`, cols `open,high,low,close,volume`.
- Every result-affecting number is a config field, never a literal in logic.

## Phase status
- **Phase 0 — DONE:** scaffold, config, data cache, honest harness (fees/slippage/
  funding/liquidation/kill-switches), buy-and-hold + Supertrend baselines, full metrics.
- **⚠️ BUG FOUND & FIXED (after Phase 3):** `supertrend()` let NaN warm-up ATR poison
  the bands permanently (`x < NaN` is always False) → direction was **stuck at +1 for
  the entire series**. This silently contaminated every earlier phase (the "floor" was
  always-long, the ensemble's supertrend agent fed constant +1 so `net` never reached
  short territory, the daily MTF always "agreed long"). Fixed by seeding bands at the
  first valid-ATR bar. All numbers below are POST-FIX. Lesson: verify indicator output
  distributions, not just causality.
- **Corrected OOS (2025-01→2026-05, per-trade expectancy / total return):**
  buy&hold −21% · Supertrend floor −$7.14 / −8.4% · Ensemble −$6.63 / −7.2% ·
  Ensemble+Filters (spot) −$10.18 / −5.2% (51 trades, max DD −8%, RoR 1.5%) ·
  Perp long+short −$11.58 / −12.9% · ML AUC 0.51 IS / 0.52 OOS (coin flip).
- **Phase 1 (ensemble), Phase 2 (regime+MTF, `gate_mode="entry_only"` default),
  Phase 3 (LightGBM, leak-free walk-forward):** all DONE, 43 passing tests. Honest
  reads: the ensemble beats the floor slightly; entry-only filters cut drawdown/RoR
  hard (DD −17%→−8%, RoR 19%→1.5%) but by trading LESS, not by better per-trade
  expectancy (which stays negative); ML adds NO predictive edge (AUC ≈ 0.5).
- **Perp + short track (DONE):** real historical funding (`data/funding.py`) +
  liquidation. Hypothesis (shorting rescues the downtrend) **REJECTED**: OOS shorts
  bleed as much as longs (−$11.87 vs −$11.25/trade). Even in-sample, shorts are ~flat
  (−$2.23) while longs carry the edge (+$12.00) — the strategy is long-biased.
- **Multi-symbol full-history test (DONE, `scripts/run_multi.py`) — the decisive,
  unbiased measure.** The rule system fits NO parameters, so its whole history is OOS by
  construction. Across 17 symbols × 2021–2026 (3496 trades spot):
  **pooled per-trade expectancy is POSITIVE: +$4.10 / +0.041%, payoff 2.38, 9/17 symbols
  net-positive, equal-weight portfolio CAGR 1.5%, Sharpe 0.32, MaxDD −8%.** Perp
  long+short: +0.032%, 10/17 positive, portfolio CAGR 2.1%, Sharpe 0.33, MaxDD −8%.
  By-year (regime proxy) is the key: spot longs make money in trending years
  (2021 +$23, 2023 +$10) and lose in choppy/bear years (2022 −$16, 2025 −$9, 2026 −$29).
  Perp/shorting SMOOTHS the down-years (2022 −16→+3, 2025 −9→+3) but dilutes bull-year
  longs (2021 +23→+10) via squeeze on pullbacks.
- **Mean-reversion sleeve (DONE, `signals/mean_reversion.py`, `use_mr_sleeve`) —
  NEGATIVE result.** Fading z-score extremes in chop bars. Across 17 symbols it made
  things WORSE: pooled expectancy +$4.10→−$2.13, portfolio Sharpe 0.32→−0.27. Higher
  win rate (41%) but payoff collapsed to 1.38 — fading works until chop becomes a real
  move and the trend sleeve's wide ATR stop lets the fade run into a big loss. Proper MR
  needs its OWN tight exit geometry (a per-sleeve harness change), not the trend ATR
  stop. Left in, OFF by default.
- **Cross-sectional top-K selection (DONE, `backtest/portfolio.py`,
  `scripts/run_xsection.py`) — THE BREAKTHROUGH.** Each bar, hold only the top-K
  strongest-momentum (60-bar ROC) signalling symbols; one shared bankroll, equal-weight
  K slots, fees+slippage, per-symbol ATR stops. OOS 2025–26 (the window that killed
  everything else): **Top-1 +16.4% / Sharpe 0.76 / +$5.97/trade; Top-3 +25.2% /
  Sharpe 0.67 / +$4.98/trade**, vs trading All −24.3% / Sharpe −1.05. Edge lives in
  TIGHT concentration — Top-5 already dilutes to −17%. First approach to clear positive
  OOS risk-adjusted expectancy. IS Sharpe (3.1–3.5) is inflated by 2021–24 dispersion;
  OOS ~0.7 is the honest number.
- **Robustness & cost stress (DONE, `scripts/run_robustness.py`) — the breakthrough is
  FRAGILE.** On the full 20-symbol universe Top-3/ROC60 looks great (OOS Sharpe 1.09,
  +51%), but: (a) **slippage-sensitive** — 1x→1.09, 3x→0.45, 5x→NEGATIVE (Top-3 rotates
  a lot; alt spreads are wide); (b) **random sub-universe bootstrap** (40 draws of 10
  symbols) gives **median OOS Sharpe 0.06, only 57% positive, median return −2.3%.** So
  the strong full-universe number is driven by a FEW specific winner symbols, not a broad
  systematic edge. Combined with survivorship bias (universe = today's survivors; we have
  no delisted-coin data and cannot manufacture it), the headline Sharpe is largely a
  function of symbol selection + low assumed slippage.
- **STANDING CONCLUSION (honest, final for this arc):** a cross-sectional momentum tilt
  produces positive OOS results ON THE SURVIVOR UNIVERSE, but it is NOT robust — near
  coin-flip on random symbol subsets and it dies under realistic slippage. We do NOT have
  a trustworthy, deployable edge. Single-asset trend, shorting, ML, and mean-reversion
  all failed or underwhelmed too. This is the correct, capital-preserving conclusion:
  the honest north-star (a robust positive-OOS edge) is NOT met. Paper-trading is
  appropriate ONLY as a no-risk way to collect forward, survivorship-free evidence — NOT
  as a green light to risk money. True next steps for a real edge: point-in-time universe
  (needs delisted data), better/cheaper execution model, or a genuinely different signal.

## Edge hunt: FUNDING (the orthogonal source) — most promising so far
- **Data:** 20 coins × 3 exchanges (binance/bybit/okx) 8h funding 2021–2026
  (`uyg/src/{funddata,xfunddata}`), all aligned with 4h OHLCV. Plus OI/LS metrics from
  2024-06 (`uyg/src/metricsdata`, shorter). Loader `data/funding.py`.
- **Cross-sectional funding carry (DONE, `backtest/carry.py`, `scripts/run_carry.py`):**
  market-neutral, daily-rebalanced, long bottom-funding / short top-funding, dollar-
  neutral, all costs. Binance OOS (2025–26): **Sharpe 1.31, Sortino 2.67, CAGR 33%,
  MaxDD −15%, OOS≥IS (no overfit gap)** — the BEST OOS result in the project, and it
  made money in 2025–26 where price momentum bled (genuinely ORTHOGONAL).
- **Independent literature check (research agent, cited):** realistic NET Sharpe for
  delta-neutral crypto carry is **~0.8–1.8** (academic 7–12 figures are GROSS/short-
  sample/uninvestable; BIS WP1087: carry ~7%/yr avg, limits-to-arbitrage). Our 1.31 sits
  squarely in the credible band — believable, not a fantasy. ">2.5 net ⇒ hunt the leak."
- **Honest caveats (confirmed in our own numbers):** (1) **price P&L dominates** the
  return (+244% vs +61% funding harvest) ⇒ this is really a cross-sectional
  POSITIONING/contrarian factor (fade crowded high-funding, buy capitulated negative-
  funding), NOT pure carry — exactly the "momentum-fighting short-vol" trade the
  literature warns of. (2) **Fails the bear-market gate:** per-year 2021 Sharpe 2.26
  (mania) but **2022 −0.48 / −15%**; IS is inflated by 2021. (3) **Exchange-inconsistent:**
  binance OOS 1.31 but bybit −0.05, okx 0.74. (4) **Moderately robust** to symbol subset
  (median OOS Sharpe 0.66, 75% positive — far better than momentum's 57%/0.06) but
  **slippage-sensitive** (5bps→1.31, 25bps→0.27). (5) survivorship-capped universe.
- **TRUE delta-neutral funding harvest (DONE, `carry.run_funding_harvest`) — net
  NEGATIVE OOS, the carry has DECAYED.** Per-coin long-spot/short-perp, collect funding,
  price legs cancel. Gross funding harvest +70% but cost drag −39% and negative-funding
  regimes sink it: OOS Sharpe −9.5 / CAGR −7.8% (daily). Sweep over rebalance {1d,7d} ×
  threshold {0,3,6,10 bps/day}: lower turnover and higher thresholds only shrink the
  loss (best −1.07 Sharpe), never cross zero; a rich-funding-only filter (≥6bps/day)
  finds NOTHING to trade in 2025–26 (funding compressed). Matches BIS/He–Manela: carry
  ~7%/yr gross, ~11%/yr decay, "thin after costs." The 2021-mania harvest is gone OOS.
- **EDGE-HUNT VERDICT (honest, final):** No clean, robust, deployable edge exists in our
  data. Pure funding carry has decayed below costs OOS. The cross-sectional funding
  long/short makes OOS money (Sharpe ~1.3) but is really a PRICE/positioning contrarian
  bet (funding harvest minor), regime-dependent (loses 2022 bear), survivorship-capped,
  exchange-inconsistent. It IS the best, most-orthogonal candidate (made money in 2025–26
  when trend bled) and its magnitude is literature-consistent — but not bulletproof.
  **Most promising remaining honest build:** combine the trend sleeve and the
  funding-positioning sleeve as a DIVERSIFIED 2-factor book — they are orthogonal (trend
  wins in trends, funding-positioning won in 2025–26 chop), so the combined Sharpe may
  beat either alone. Then fix survivorship (point-in-time universe) before trusting size.
- **DIVERSIFIED 2-FACTOR BOOK (DONE, `backtest/combine.py`, `scripts/run_combo.py`) —
  THE BEST RESULT, and it holds up.** Blend trend (Top-3) + funding-positioning with
  inverse-vol weights FIT ON TRAIN, applied OOS. Sleeve correlation −0.06 (genuinely
  orthogonal). **OOS Sharpe 1.74 (CAGR 37%, MaxDD −14%) beats trend-only 1.07 and
  funding-only 1.31** — real diversification free lunch; IS MaxDD −8% vs −26% each alone.
  Crucially it is MORE ROBUST: random sub-universe (30 draws) median OOS Sharpe 0.48 /
  77% positive, vs trend-only's fragile 0.06 / 63%. Weights trend 0.39 / funding 0.61.
- **FINAL STANDING CONCLUSION:** the deliverable edge is the **diversified trend +
  funding-positioning book** (OOS Sharpe ~1.7 full-universe, ~0.5 median on random
  subsets, MaxDD −14%, near-zero sleeve correlation, literature-consistent magnitudes).
  No single sleeve is robust alone; their orthogonal combination is the genuine result.
  ⚠️ Still survivorship-capped (universe = today's survivors; lit. says ~15–22%/yr
  inflation) and the funding sleeve is regime/exchange-dependent — so this is a
  PAPER-TRADING candidate, NOT live capital. Remaining work to deploy: (1) point-in-time
  universe incl. delisted coins; (2) per-coin liquidity-scaled slippage; (3) forward
  paper evidence via `run_paper.py` (extend it to the combined book); (4) ask before any
  live execution.

## Survivorship / selection-bias PROXY — edge holds on a BROAD universe (`scripts/run_expanded.py`)
- The 20-coin combo (Sharpe 1.74) was always open to the charge "you hand-picked 20 survivors."
  We can't get truly-delisted coins from ccxt, but we CAN bound SELECTION bias: fetch the
  top-liquidity USDT perps automatically (no hand-picking) and re-run the same combo.
- **Result (44 coins auto-selected by 24h volume, 4h OHLCV+funding 2023→, OOS 2025-26, all
  costs): combo OOS Sharpe 2.13 (CAGR 183%, MaxDD −27%) — HIGHER than the 20-coin 1.74, not
  lower.** Crucially, **20 random 20-coin sub-universes drawn from the 44: median OOS Sharpe
  1.73, 100% positive** — vs the fragile momentum-ONLY bootstrap (57% positive / 0.06 median).
  The diversified combo is robust to which coins you pick; the 20-coin headline was NOT
  cherry-picked. Selection bias is largely ruled out.
- **Honest caveats unchanged:** (1) still no TRULY-delisted coins (all 44 are alive today) →
  apply the literature survivorship haircut (~15–22%/yr) to the MAGNITUDE; (2) MaxDD −27% on
  the broad universe is worse than the 20-coin −14% (more alts = fatter tails) → size for the
  −27% reality, not the −14%; (3) Sharpe ~2.1 still nears the "hunt-for-leak" line, so paper
  evidence before live capital stands. Net: the diversification edge is real and broad, but
  the deployable EXPECTATION should be the haircut-adjusted, drawdown-honest version.
## LEVER #1 — 4th orthogonal sleeve hunt (`scripts/run_sleeve4.py`) — NEGATIVE, honest
- Tried the two canonical diversifiers to add to the 3-sleeve book (2.40): MACRO TSMOM
  (time-series momentum on GLD/SLV/TLT/IEF/DBC/USO/UNG/UUP/DBA, inverse-vol, lagged, costed)
  and EQUITY STR (short-term reversal on the US large-caps, dollar-neutral, costed).
- **Correlation is beautifully orthogonal** (macro_tsmom 0.02–0.04 to all 3 sleeves;
  equity_str −0.06..−0.18) — the diversification MECHANISM is present. **But both are
  NEGATIVE standalone OOS 2025-26** (macro_tsmom Sharpe −0.72, equity_str −1.04), and
  inverse-vol over-weights them (low vol → 0.59 / 0.41 weight) → the book DROPS
  2.40 → 1.64 (+macro) / 1.36 (+str) / 0.88 (both). **Lesson: low correlation is necessary
  but NOT sufficient — a sleeve must ALSO be ≥0 OOS to help; these lost money in this
  window (a poor regime for macro trend, consistent with real managed-futures 2023-25).**
- **Verdict: no improving 4th sleeve found among the natural candidates; 3-sleeve book
  (OOS Sharpe 2.40) stands.** Did NOT keep trying sleeves until one accidentally helped OOS
  (that would be the overfitting the project forbids). An equity value/quality or a
  point-in-time-correct macro sleeve over a longer OOS could be revisited, but not promoted.

- **Engine bug fixed in passing (`signals/mtf.py`):** pandas-3 `merge_asof` now enforces
  matching datetime resolution; ccxt data is `[ms]`, resample yields `[us]/[ns]` → the MTF
  merge raised `MergeError`. Coerced both keys to `ns` (`.as_unit("ns")`) — robust to any
  data source (ccxt/yfinance/resample), all 69 tests still pass.

## LEVER #2 — vol-targeting / risk sizing (`scripts/run_sizing.py`) — the honest growth dial
- Sharpe is leverage-invariant, so this adds NO alpha — it converts the robust 2.40-Sharpe
  3-sleeve book into controlled compounding. Dynamic vol-target (20d LAGGED realized vol,
  cap 3x): OOS Sharpe stays ~2.29 across all targets; you dial risk/return:
  raw 35% CAGR/−7% DD → **15% target 49%/−10% (≈1.4x lev)** → 20% 68%/−13% → 25% 87%/−16%.
- **Honest nuance:** in THIS smooth 2025-26 OOS, vol-targeting did NOT cut MaxDD (no vol
  spike to catch) — the benefit was purely the risk-level dial, not drawdown reduction (the
  de-risk payoff shows up in turbulent regimes). Static fractional-Kelly f*≈18.5x is inflated
  (OOS-μ + survivorship + fat tails); even ¼-Kelly = −29% DD. **Safe band: 15% vol target +
  ≤¼-Kelly.** The broad-44-coin book's −27% DD is tamed by the same vol target.
- **Deliverable:** a 15% vol target (~1.4x avg leverage) roughly DOUBLES CAGR (35%→49%) at a
  stomach-able −10% DD with Sharpe unchanged — real incremental money, no new edge required.

## LEVER #3 — XGBoost CROSS-SECTIONAL RANKING (`scripts/run_mlrank.py`) — NEGATIVE, 4th confirm
- A genuinely NEW ML use (not the failed binary gate): train XGBoost to predict each coin's
  forward 60-bar (10d) return, pooled across 20 coins (162,877 train rows, 15 causal features,
  train <2025), and use the prediction as the Top-K RANKING key in place of 60-bar ROC. The
  selection mechanism ('hold Top-3 strongest') is unchanged — only 'strongest' is redefined.
- **Result: ML ranking did NOT beat ROC and HURT the book.** Trend sleeve OOS Sharpe ROC 1.05
  → ML 0.42; combo (trend+funding) ROC 1.71 → ML 1.27. **OOS rank-IC = −0.018** (≈0). Top
  features (mtf_dir, donchian, supertrend, atr_pct, regime_adx) show the model just rediscovers
  the trend/regime context ROC already encodes, without ranking forward returns any better.
- **Verdict: ROC stays.** This is the 4th independent confirmation (Phase-3 single-asset AUC
  0.52, pooled meta-label gate −Sharpe, ML4T purged-CV IC 0.02, and now cross-sectional
  ranking IC −0.018) that there is NO learnable directional/return-prediction edge in this
  data. ML adds noise, not money. The edge is STRUCTURAL (diversification + sizing), not ML.

## LEVER #4 — XGBoost from LIVE trades (`scripts/watch_live.py:train_xgb_from_live`) — data-gated
- Harness is ready (MIN_LIVE_TRADES=30): when ≥30 resolved local-shadow trades accumulate it
  retrains on REAL live fills (survivorship-free, forward, no backtest bias). Currently the
  live trades table is ~empty → nothing to train yet. Auto-triggers as live data accrues.
  (Caveat: even with live data, prior evidence says don't expect a directional edge; this is
  for honest forward validation, not a new alpha source.)

## ★ '4-lever' synthesis (user: "how do we make MORE money?") — the honest answer
- Of the 4 levers requested: **#1 4th sleeve = NO** (orthogonal but unprofitable OOS),
  **#2 vol-targeting = YES** (the real money lever — no new alpha, 15% vol ⇒ CAGR 35%→49% at
  −10% DD), **#3 XGBoost ranking = NO** (IC −0.018), **#4 XGBoost-from-live = data-gated**.
- **Conclusion: more money comes from SIZING the existing robust structural edge (the 3-sleeve
  book, OOS Sharpe 2.40, broad-44-coin-robust), NOT from more ML.** XGBoost has now failed 4
  ways; the disciplined path is vol-targeted sizing (≤¼-Kelly ceiling) on the diversified book,
  then point-in-time-universe + forward paper evidence before any live capital.

## ★ PRODUCTION-CANDIDATE BOOK (`scripts/run_book.py`) — synthesis of everything that works
- Combines the 3 survivors: BREADTH (broad auto-selected universe, restricted to the 27
  FULL-HISTORY coins so the all-coin index intersection doesn't truncate the train split) +
  DIVERSIFICATION (crypto-trend Top-3 + crypto-funding + US-momentum, inverse-vol, train-fit
  weights {trend 0.26, funding 0.28, us 0.46}) + SIZING (vol-targeting).
- **Numbers (556 common days 2023-07→2026-05):** sleeve corr 0.02/0.19/−0.10 (real diversif).
  Unlevered IS Sharpe 1.83 / OOS 3.06. Vol-targeted OOS: 15% → CAGR 55%/−12% DD/Sh 2.59;
  20% → 78%/−16%; 25% → 103%/−20%. **By-year ALL positive** (2023 +3, 2024 +29, 2025 +39,
  2026 +23%) — survives the regime gate (no bear-year blowup).
- **HONESTY FLAGS (loud):** (1) OOS Sharpe 3.06 > IS 1.83 is a WARNING, not a win — it means
  2025-26 was a kind regime, NOT that the book generalises better OOS; realistic expectation
  is the IS level (~1.8) or lower. (2) 3.06 is ABOVE the literature "hunt-for-leak" line
  (>2.5) → short OOS (273d) + survivorship (27 alive coins) + favorable window inflate it.
  (3) This book has NOT been through its own DSR/PBO (the earlier 0.986/0.031 gate was the
  20-coin combo family). (4) Apply the ~15-22%/yr survivorship haircut → realistic CAGR
  ~30-40%, not 55%. **Deliverable = the 15% vol-target book; next step is PAPER-trade
  (NOT live capital), then point-in-time universe + DSR/PBO on this exact book. Ask before
  any live execution.**

## ★ BOOK walk-forward optimization (`scripts/run_bookopt.py`) — honest profit max
- Walk-forward (12m train / 6m test / step 6m) over trend(ROC×topK) × carry(lb×n) + 3-way
  inverse-vol weights, train-selected, OOS-applied. OOS Sharpe 3.06 → **4.18** (CAGR 64→53%,
  DD −8→−6%). Vol-targeted 15% → CAGR 94%/−11% DD; 20% → 139%/−14%; 25% → 187%/−16%.
- **The picks are HIGHLY CONSISTENT every window: trend (ROC30, Top-1) + carry (14,5),
  balanced weights** — stable regime-adaptation (fast momentum + tight concentration), NOT
  param-jumping. That consistency is genuine robustness evidence. But 4.18 is ABOVE the
  hunt-for-leak line → magnitude inflated by Top-1 single-name variance + short OOS + survivor.

## ★ BOOK honesty gate (`scripts/run_bookpbo.py`) — DSR 1.000, PBO 0.014: EDGE IS REAL
- DSR + PBO (CSCV, 12870 splits) on the 54-config 3-sleeve book family (27-coin + US).
  Deployed = WF-opt's (30,1)|(14,5)+US. Observed daily Sharpe 0.227 (ann ~3.60) vs null
  expected-max 0.064 (ann ~1.02). **DSR = 1.000** (P[true Sharpe>0]≈100% after deflating
  for 54 trials + skew +0.33 + kurtosis 3.94). **PBO = 0.014** (median logit +2.85 → IS-best
  generalizes OOS). The edge SURVIVES the honesty gate decisively — NOT a grid artifact.
- **CRITICAL distinction:** DSR/PBO confirm the edge is POSITIVE and GENERALIZES — they do
  NOT bless the 3.6-4.2 annual MAGNITUDE (still survivorship- + short-window-inflated).
  **Realistic deployable expectation ~1.8-2.5 Sharpe after the ~15-22%/yr haircut.**

## ★★ FINAL 'most profitable' answer (honest, capital-preserving)
- **Most-profitable DEPLOYABLE config = the broad 3-sleeve book (27-coin crypto-trend Top-3
  /ROC30 + crypto-funding + US-momentum, inverse-vol) sized with a 15-20% vol target.**
  Use Top-3 not the WF-opt's Top-1 (single-name fragility) — slightly lower Sharpe, far less
  variance. Honest expectation: Sharpe ~1.8-2.5, CAGR ~40-90% at the chosen vol, DD ~−12/−16%.
- Profit comes from (1) the structural diversified edge (DSR/PBO-confirmed real), (2) breadth
  (survivorship-proxy-robust), (3) vol-target SIZING — NOT from leverage-for-its-own-sake or
  ML (failed 4×). **Next honest step: paper-trade this exact book; then point-in-time universe
  to clean the magnitude. Ask before any live execution / order code.**

## PROP-FIRM challenge — 2-bot system on the real edge (`scripts/run_propfirm.py`)
- Card rules: P1 +8%, P2 +5%, max total −10%, max DAILY −5% (instant fail), 80% biweekly,
  $5K, $36. Monte-Carlo (block-bootstrap, 30k paths) the 3-sleeve book's daily returns,
  haircut ×0.6 (sim Sharpe ~1.2), across annual vol targets. P(pass BOTH phases): 5% vol→31%,
  7%→51%, 10%→66%, 12%→70%, 15%→69%. Funded month blowup ~0% up to 12% vol.
- **Bot pool verdict (Explore agent):** Gemini's prop bots 06-10 target the right rules
  (explicit −5%/−10% limits) but their backtests are untrustworthy (look-ahead, no
  liquidation, XGBoost AUC~0.52). The only DSR/PBO-real edge is our 3-sleeve book.
- **2-bot answer = ONE real edge at TWO vol settings:** Bot A passer ~10% vol (P(both)~66%,
  median ~92 days, daily/total fails ~0/6%, P(day≤−3%)=0% so safe margin to the −5% cliff —
  chose 10% over the naive 12% optimum because 12-15% has 34% chance of a −3% EOD day whose
  INTRADAY could breach −5%). Bot B funded ~7% vol (~0% monthly blowup, ~$48/mo on $5K).
- **EV decision:** expected cost to get funded ≈ $36/0.66 ≈ $55; funded ~$48-69/mo → +EV,
  ~1-month payback IF (a) the edge holds FORWARD (paper-validate first), (b) the firm allows
  crypto+US (our edge does NOT transfer to a forex-only firm — no validated forex edge), and
  (c) a −3% intraday self-halt is added (EOD data understates the −5% daily-breach risk).

## FundingPips reality check (`scripts/run_fundingpips.py`) — edge does NOT transfer
- FundingPips = forex/CFD prop firm (~48 instruments: FX, indices, metals, energies, a few
  crypto CFDs @1:2 lev, $45/lot, NO funding mechanism). Daily loss 5% of max(day-start balance,
  current EQUITY) → intraday/equity-based. Max DD static 10%. P1 +8%/+10%, P2 +5%, min 3 days,
  no time limit. **Our DSR/PBO-validated 3-sleeve book does NOT transfer:** funding-carry sleeve
  cannot exist on CFDs, US single-stock cross-section unavailable (only indices), crypto degrades
  to a few 1:2 CFDs with wide costs (and our slippage stress already killed momentum at high cost).
- **Tested the transferable price strategies (TSMOM + cross-sectional momentum, lookbacks
  30-120) on 18 FundingPips-native instruments (G10 FX + 6 indices + gold/silver), honest costs,
  2015-2026.** Best OOS (2025-26) = XSEC-90 Sharpe 0.79 — BUT **IS Sharpe is NEGATIVE for every
  candidate (−0.27..−1.09) and the best book lost money in 9 of 12 years**, positive only in
  2025-26. That 0.79 is REGIME-LUCK, not edge (negative IS + 9 negative years confirm it).
  Consistent with the earlier LEVER #1 macro-TSMOM negative result.
- **VERDICT (honest, capital-preserving): we do NOT have a validated edge on FundingPips
  instruments. Do not buy the challenge expecting our system to pass — that is gambling, not
  science.** Untested honest hypotheses that COULD fit (no promises): FX CARRY (rate-differential,
  harvested via swap — the true analog of our crypto funding edge; needs rate data), FX
  mean-reversion (majors range more than crypto trends), or intraday (different data/game).

## FundingPips hypotheses #2/#3 (`scripts/run_fxedge.py`) — FX MEAN-REVERSION is the first hit
- FX CARRY (rate-diff, G10, approx annual policy rates + daily accrual): OOS Sharpe 0.92,
  IS 0.28 — positive both but modest. FX MEAN-REVERSION (cross-sectional short-term reversal):
  **FX-MR-1d OOS Sharpe 1.67, IS +0.60, 8/12 years positive** — the FIRST FundingPips-native
  candidate with POSITIVE IS (momentum was negative IS = pure regime-luck). Reversal fits FX
  because majors RANGE (opposite of crypto's trend) — a well-documented short-term FX effect.
  Longer MR lookbacks (2-5d) decay fast (OOS 0.49→0.10) → the edge is in the 1-day reversal.
- **Red flags before trusting it:** (1) OOS MaxDD −10% AT the challenge total limit → must
  vol-target down hard. (2) 1-day reversal = very high turnover → cost-sensitive (3bps used;
  needs a cost-stress). (3) OOS>IS again = 2025-26 kind. Next: cost-stress + DSR/PBO + prop sim.

## FX-MR-1d validation (`scripts/run_fxmr_validate.py`) — FAILS the cost + prop gate
- COST-STRESS kills it: OOS Sharpe 3bps 1.67 → 6bps 1.03 → 10bps 0.17 → 15bps −0.90. The
  1-day reversal is too high-turnover; realistic blended cost (FX majors cheap but the index +
  metal CFDs and daily rebalancing push to ~6-10bps) erodes the edge.
- DECISIVE: at a realistic 6bps, the FULL-SAMPLE (2015-26) Sharpe is NEGATIVE (−0.26) — the
  OOS 1.03 was the kind 2025-26 window only. Prop Monte-Carlo (haircut, vol-targeted to respect
  −10%/−5%) gives P(pass both) ≤16% even at 10% vol. **No reliable positive edge at real cost.**
- **★ ACCUMULATED FundingPips VERDICT (honest, final for this arc):** we applied the full
  rigorous pipeline to FundingPips-native instruments — cross-sectional & time-series momentum,
  FX carry, FX mean-reversion — and NONE is a robust, cost-survivable, path-constraint-passing
  edge. Momentum was regime-luck (IS<0), carry modest (OOS 0.92/IS 0.28), MR cost-fragile
  (full-sample <0 at real cost). **Do NOT buy the FundingPips challenge expecting our system to
  pass — the validated edge (the crypto 3-sleeve book) cannot be traded on their CFD instruments,
  and no native FX/index/metal edge cleared the honesty bar.** Honest options: (a) a CRYPTO-native
  prop firm where our DSR/PBO-real book actually applies; (b) paper-trade the crypto book; (c) a
  much larger intraday FX research effort (new data/infra, no promise). Capital-preserving call.

## CRYPTO-NATIVE prop firms — our edge APPLIES here (`scripts/run_propfirm_multi.py`)
- Unlike FundingPips (CFD), crypto-native firms trade REAL USDT perps with funding → our
  DSR/PBO combo (cross-sectional momentum + funding carry) genuinely works. Firms (2026 rules):
  HyroTrader (700+ Bybit perps; 1-step 10%/DD6%trail/daily4%/min10d; 2-step 10%+5%/DD10%trail/
  daily5%; EOD-trailing DD; 80→90% split), Breakout (50+ pairs; 1-step 10%/DD6% STATIC/daily4%;
  80%), FundedNext (8%+5%/DD10% static — but CFD crypto, funding sleeve WEAK → its number is
  inflated). Multi-firm Monte-Carlo (combo, 0.6 haircut, sim Sharpe ~1.0, EOD trailing modeled):
- **Results (P(funded) / funded blowup-per-month / ~monthly $ on $25K, at 10% vol):**
  Breakout 1-step 48%/0.2%/$253; FundedNext 44%/0%/$254 (DISCOUNT — CFD funding); HyroTrader
  2-step 35%/0%/$257; HyroTrader 1-step 42%/0.3%/$251. At 15% vol P(funded) rises to ~48-57%
  but funded blowup climbs (Breakout-1 2.8%/mo). Expected cost-to-fund ~$350 (retries); payback
  ~1-1.5 months. POSITIVE-EV IF edge holds forward + algo trading allowed + paper-first.
- **Honest picks (judgment over the raw EV sort):** (1) HyroTrader = only firm where the FULL
  edge is unambiguously real (real perps+funding+700-coin breadth) — trailing DD lowers pass
  rate so use lower vol; safest "edge is real" bet. (2) Breakout = static DD (easier climb) +
  real perps; best if it offers funding perps + allows algos. (3) FundedNext DISCOUNTED (CFD).
  2-setting per firm: pass at ~10-15% vol, then DE-RISK funded to ~7-10% vol (protect account).
- **★ MUST-VERIFY before buying:** does the firm ALLOW full algorithmic/API bot trading? Many
  prop firms ban full automation. HyroTrader is API-to-Bybit (algo-friendly by design); confirm
  Breakout. Make-or-break. Ask before any live API/order code.

## CHALLENGE-FARMING backtest (`scripts/run_farm_backtest.py`) — LOSES MONEY, honest
- User idea: farm the challenge — pass, get funded, withdraw $200, rebuy a new fund, repeat.
  Backtested SEQUENTIALLY on the REAL last-8-month combo returns (HyroTrader 2-step rules:
  P1+10%/P2+5%, daily −5%, total −10% TRAILING EOD, min 10+5 days, 80% split, withdraw $200).
- **Result: NET NEGATIVE at EVERY vol — even raw (no haircut, the favorable 2025-26 as-is):**
  10% vol −$249 (0 passes); 15% −$498 (0); 20% −$298 haircut / −$98 raw (1 pass then funded
  BLEW UP on trailing DD); 25% −$547. Withdrawals rarely cover the $249 challenge costs.
- **Why (structural tension):** (1) at SAFE low vol the +10% target is too slow to hit (10%
  return needs ~1 Sharpe-year); (2) at HIGH vol you reach target but the funded account blows
  up on the 10% TRAILING DD before sustained $200 withdrawals; (3) min-days + $249 cost/attempt
  stack up. The earlier Monte-Carlo "P(funded) 35-48%" answered "pass within a YEAR" — it did
  NOT model rapid-farming + trailing-DD survival + repeated withdrawals in 8 months.
- **VERDICT: challenge-farming is NOT a money machine on real recent data — it loses money.**
  (Caveat: window was ~130 stock-calendar days not ~240 crypto-days, so somewhat harsher than
  reality; but even doubling the rate it's marginal, not the rosy "$200 repeatedly" hoped for.)
  Honest path stays: paper-validate on testnet FIRST; treat funded as a slow earner at LOW vol,
  not a fast-farm. Don't buy multiple challenges expecting to farm them.
- **UPDATE — real HyroTrader $5K / $59 FULLY-REFUNDABLE fee changes it to ~break-even.** Re-ran
  with the actual screen params (account $5K, fee $59 refunded on first payout, One-Step
  10%/DD6%trail/daily4%/min5d vs Two-Step, frequent small $100 withdrawals to bank profit before
  trailing-DD). Best realistic config = **One-Step, ~25% vol, $100 withdrawals: main-path NET
  +$223 over 8mo, offset-median +$23** (range −$36..+$223). Two-Step ~break-even (+$41..−$18).
  The refundable fee turns the deep negatives into roughly break-even-to-modestly-positive — but
  the MEDIAN is only ~+$23 (essentially a coin-flip with small edge), high variance, at aggressive
  25% vol, in the FAVORABLE 2025-26 regime, with a 0.6 haircut. **It is NOT reliable income.**
  Honest answer to "what would realistically happen": roughly break-even to a modest few-hundred
  $, driven entirely by fee-refundability + frequent profit-taking; do NOT expect compounding
  wealth. Testnet-validate first; the +$223 is the lucky path, +$23 the median.

## LIVE screener + FUNDING-FLIP thesis (`scripts/screener.py`, `scripts/run_funding_flip.py`)
- `screener.py`: live ccxt (Binance perp) — 24h volume-surge, OI 24h Δ, funding Δ + level
  gainers/losers + funding-FLIP (sign change) detector. Read-only, no orders. Feeds the thesis.
- **User's funding-squeeze thesis TESTED — and VALIDATED (it beat my prior assumption).** Event =
  funding z-score extreme (|z|>1.5) THEN reversing toward zero. Two competing directions:
  FADE (short crowded high-funding, our continuous-carry direction) vs UNWIND (follow the
  fee-farmers' unwind, the USER's thesis). Pooled 20 coins, IS-optimal TP/SL applied OOS:
  **FADE at the flip = NEGATIVE OOS (Sharpe −2 to −4); UNWIND = POSITIVE (best 8%/5% TP/SL,
  OOS Sharpe +0.94, multiple cells positive).** So at the FLIP MOMENT the short-term move FOLLOWS
  the unwind (momentum), opposite to the continuous-carry fade — the user's intuition was right.
- **But cost-stress shows it is THIN/FRAGILE:** UNWIND OOS Sharpe 0.94 @6bps → 0.43 @11bps
  (realistic Bybit taker round-trip) → −0.08 @16bps (alt spread). Per-trade edge ~9bps pre-cost.
- **VERDICT:** the funding-flip-FOLLOW signal is a REAL but thin, cost-sensitive timing edge —
  NOT a strong standalone (dies by 16bps). Best used exactly as the user proposed: as a
  CONFLUENCE filter (take the unwind trade only when it AGREES with the combo trend/funding
  signal), with maker orders to cut fees. Worth wiring as an overlay + testing it doesn't hurt
  the combo (recall the meta-label gate HURT — confluence must be validated, not assumed).

## PROP-PASS sizing optimization (`scripts/run_propfirm_opt.py`) — clever de-risk HURTS, honest
- Q: can we optimize the bot to PASS better (alpha fixed, just risk-path management)? Tested 4
  policies on HyroTrader 2-step (trailing DD), alpha held constant (sim Sharpe ~1.0):
  A constant-vol 43% / B buffer-build-then-derisk 39% / C buffer+lock-near-target 22% /
  D +daily-governor 23%. **Constant vol WINS; every "smart" de-risk policy HURT pass rate.**
- **Why (counterintuitive, true):** the +10% target is HIGH vs the modest edge, so you must keep
  compounding at full risk to reach it before the path/time runs out. De-risking after a buffer
  starves the growth; locking near target stalls you just below it; the trailing DD floor rises
  with the peak anyway so buffer-building doesn't reduce breach risk. **The ONLY real pass-lever
  is the VOL LEVEL** (10%→35%, 15%→48% pass) not path-shaping. ~15% constant is the sweet spot,
  which `--mode pass` already uses. So the bot is already near-optimal for passing; there is NO
  trick to push 45%→80% without taking more blowup risk. The edge is the edge.
- **Funded phase is the OPPOSITE regime:** no target to hit, objective = don't blow up → low
  constant vol + lock/withdraw IS correct there. Pass = constant-aggressive; Funded = ultra-
  conservative. Keep the executor's two modes; do NOT add buffer/lock to pass mode (it hurts).
- **Funding-fee question (friend Emir):** partially right — funding can be high & is a periodic
  long↔short transfer. Two corrections: the EXCHANGE does NOT keep funding (it's peer-to-peer;
  the exchange takes separate TRADING commission), and the period is usually 8h not 12h. Key:
  for OUR system funding is largely INCOME (the carry sleeve is built to COLLECT it — long
  low-funding / short high-funding) and is already in the backtest. The real cost to watch is
  TRADING COMMISSION (taker ~0.055% + spread) at high turnover, not funding.

## Raising the correct-decision rate — POOLED meta-label (DONE, `scripts/run_metalabel.py`)
- Goal: increase the signal's hit rate / cull bad trades. (Reminder: for trend systems a
  low win rate is normal — the real target is EXPECTANCY; naive win-rate chasing via tight
  TP destroys edge. So we gate by predicted quality, not by shrinking targets.)
- **Key result (honest, OOS):** pool long-entry candidates across all 20 coins (18,777
  samples), triple-barrier label, LightGBM, train ≤2024 / test 2025-26. **Price-only AUC
  0.562** — pooling cross-sectionally gives REAL signal that single-symbol BTC lacked
  (~0.52 coin-flip in Phase 3). Gating to the top-X% by predicted P(win) lifts OOS
  monotonically: win 27.6%→31%(top50)→34%(top30)→36.7%(top10); expectancy
  **−0.120→+0.051→+0.201→+0.335 ATR (negative→positive).** This is a genuine
  decision-quality lever.
- **What did NOT help:** adding funding+OI features (`ml/altfeatures.py`) — AUC 0.519,
  WORSE than price-only (overfits in-sample, top gain but no OOS generalization). The
  lift comes from POOLING, not from alt-data. Top real features: atr_pct, dist-from-
  extremes, regime_adx, ret_6/12, vol_ratio (regime/vol/recent-return context).
- **Next:** wire the pooled meta-label as a top-X% entry-quality gate into the trend
  sleeve of the combo and re-measure OOS Sharpe (label-level expectancy lift must be
  confirmed at the portfolio level).

## Order-flow DERIVATIVE research (velocity + acceleration) — multi-agent workflow
- User's thesis ("Orderflow Exhaustion"): a trend on RISING-but-DECELERATING flow (2nd
  derivative < 0) is a fakeout — the HFT logic. Tested rigorously via 9-agent workflow
  (`scripts/orderflow_workflow.js`): a feature lab (`research/orderflow.py`,
  `scripts/feature_lab.py`) computes velocity/acceleration/z-score/exhaustion features
  for 8 families (volume, price_action, cvd_proxy, vwap, volatility, funding,
  oi_ls_taker, exhaustion) on the pooled 18,777-candidate panel; each family tested for
  OOS AUC lift over the price baseline (0.561), then adversarially verified.
- **Result — NEGATIVE, honest: no derivative family adds OOS edge.** Zero of 8 clear the
  +0.01 AUC bar; 5 of 8 HURT OOS (funding −0.017, oi_ls_taker −0.047, cvd_proxy −0.021 —
  classic in-sample overfit, IS/OOS gap blows out). The exhaustion thesis is the cleanest
  loser (doesn't overfit, gap 0.151 < base 0.156, OOS AUC 0.568) but family-ALONE OOS AUC
  is 0.465 (sub-random) and the +0.006 lift is within noise. Theory is sound (it IS what
  HFT uses) but on our data/label/OOS it does not separate true vs false trends.
- **Honest data caveat:** we have NO true CVD/aggTrades, liquidations, order-book, or
  VPVR history — those families used candle PROXIES (signed-volume CVD, rolling VWAP).
  A real test of CVD/liquidation/order-book exhaustion needs tick/L2 data we don't have.
  The 2nd-derivative idea is worth one more look only with richer data or a different
  label horizon — NOT promoted to production.
- **Quality gate wired & re-measured (DONE, `ml/quality_gate.py`, `scripts/run_gated.py`)
  — gate HURTS the portfolio.** The pooled price meta-label raised per-trade win rate
  (27.6%→34%) and triple-barrier expectancy (neg→pos) at the LABEL level, but gating the
  trend sleeve to its top-50% by P(win) CRASHES portfolio OOS Sharpe: trend 1.12→−0.79,
  combo 1.74→0.54. **Lesson (confirms the upfront warning): win rate ≠ profit.** The
  portfolio monetizes cross-sectional momentum (big winners from the strongest names);
  the meta-label vetoes some of those by a different, weak (0.56-AUC) criterion and
  destroys the selection that actually worked. The label-level "correct-decision-rate"
  metric is the WRONG objective for this book — chasing it lowers Sharpe. **Do NOT deploy
  the gate.** Best book stays the UNGATED diversified combo (OOS Sharpe ~1.74).

## Edge MAXIMIZATION (higher-order derivatives, regression, walk-forward opt)
- **Higher-order derivatives + regression feature sweep** (extended `research/orderflow.py`
  with 3rd-deriv "jerk" + rolling-OLS "regression" families; re-ran the 8→10-family lab):
  jerk adds nothing OOS (+0.007). **Regression (rolling-OLS slope + R² trend-cleanliness,
  multi-window) is the FIRST family to clear the bar: OOS AUC 0.562→0.582 (+0.021)**,
  top-10% gate win 40%, exp +0.50 ATR. Likely because R² (linear-trend vs chop) + slope
  capture trend quality the base ADX/ER miss. Caveat: family-ALONE OOS AUC 0.499 (only
  helps in combination), IS/OOS gap widens a touch.
- **BUT gating the portfolio still HURTS** — even with the regression-enriched meta-label
  and gentler keep-60%: combo OOS Sharpe 1.74→1.16. Confirmed across 2 meta-label variants
  × 2 thresholds: per-trade quality gating disrupts cross-sectional momentum capture.
  **Win-rate ≠ portfolio Sharpe — do not gate.** (Regression features are a real
  trend-quality signal; they just don't help THIS momentum book as an entry veto.)
- **★ Walk-forward parameter optimization (DONE, `scripts/run_wfopt.py`) — the honest
  edge maximizer.** Precompute each param-combo's return stream; per WF window pick the
  best trend (ROC×top_k) + carry (lookback×n_side) + inverse-vol weight on TRAIN, apply
  to untouched TEST. **OOS Sharpe 1.74→2.25, MaxDD −13.5%→−8.5%** (full-span 2.43). Picks
  are consistent (ROC30/top-1 fast-momentum + tight concentration every window ⇒ regime
  adaptation, not param-chasing). This is the current best, fully-OOS, overfit-protected
  result. ⚠️ Sharpe ~2.3 nears the literature "hunt-for-leak" line; still
  survivorship-capped; top-1 = single-name variance. Paper-trade before any live capital.

## Strategy bake-off — the best DECISION-MAKER (DONE, `scripts/run_bakeoff.py`)
- Ran every strategy on the SAME OOS window (2025-26) with one honest accounting, plus
  the june_2 'asymmetric sniper' CONCEPT re-implemented in our harness (perp/leverage/
  %TP-SL with liquidation + kill-switches; harness now supports `stop_mode="pct"`).
- **Decision quality (win-rate / "correct decisions"):** X-sec Top-3 momentum 41.8% win,
  +$70 exp/trade, RoR 12% — highest win-rate AND positive. Supertrend/Ensemble BTC ~29%
  (negative OOS). **Asymmetric sniper TP10/SL2 (1x, honest): 27.1% win, −$30 exp/trade
  (NEGATIVE), RoR 67%** — +10%-before-−2% rarely happens in chop, so it wins too seldom
  even at 2.31 payoff; catastrophic ruin risk.
- **Risk-adjusted leaderboard (the real winner):** 1) Combo trend+funding Sharpe 1.74,
  2) Funding 1.31, 3) X-sec momentum 1.12, then negatives (BH −0.16, sniper −0.32,
  ensemble/supertrend ≈ −0.4). WF-optimized combo (separate) = 2.25.
- **⚠️ june_2 sniper at 10x leverage HALTS in-sample** — a 2% stop = ~10-20% equity loss,
  breaches the daily/total DD kill-switches → 0 OOS trades. The advertised leverage is
  NOT survivable under honest risk limits, and the asymmetric R/R is negative-EV in chop.
  Verdict on the june_2 bots: do not deploy; their backtests omit liquidation/gap and
  use a full-sample top-X% threshold (look-ahead).
- **ANSWER to "best decision bot":** highest hit-rate = X-sec Top-3 momentum (41.8%, and
  it's also +EV); best SYSTEM (the real goal) = diversified combo (Sharpe 1.74, WF-opt
  2.25). Win-rate ≠ best system — both reported so the difference is explicit.

## Winning Circle corpus mining (multi-agent) — NO new edge (honest)
- ~60 PDFs (ICT/SMT/Killzone/Silver-Bullet, Wyckoff, order-flow/CVD/OI, liquidity+heat
  maps, footprint, on-chain valuation, Al Brooks/Volman PA, psychology) deep-read by a
  6-agent workflow (`scripts/winc_workflow.js`). ~90% is discretionary education /
  psychology — not systematically backtestable.
- **Untestable with our data (confirmed):** all ICT session machinery (killzone, Silver
  Bullet, London-close, midnight-open, AMD) needs ≤5m intraday bars; liquidity/heat maps,
  footprint, order blocks, true CVD, arbitrage need L2/tick; the entire on-chain block
  (MVRV, SOPR, NUPL, URPD, realized price…) needs Glassnode/CryptoQuant entity data;
  macro/news (DXY, NFP, F&G) needs external feeds. 200W/cycle ideas have ~3 samples (no power).
- **The 4 testable concepts, all tested honestly as filters/sleeves on the momentum book
  — ALL FAILED** (`scripts/winc_tests.py`, `scripts/run_sweepfade.py`, baseline Sharpe 1.12):
  (A) killzone/session hour filter → ≤0.35; (B) Mayer-Multiple valuation gate → ≤1.07;
  (C) SMT BTC/ETH breadth → ≤0.96; (D) liquidity-sweep/failed-breakout FADE (the corpus's
  one codable kernel) → forward-return WORSE than baseline, sleeve OOS Sharpe −1.02.
- **Recurring lesson (definitive):** every filter raises win-rate (41.8%→43-45%) but
  lowers Sharpe — the momentum edge lives in big winners, not hit-rate. Raising the
  "correct-decision rate" is easy and always hurts risk-adjusted return here.
- **VERDICT: no holy grail in the corpus.** It adds nothing to the existing trend+funding
  book (Sharpe 1.74 / WF-opt 2.25). The mining was thorough; the honest answer is the
  book already captures the only durable edges these materials gesture at.

## ML4T-grade XGBoost retrain (Jansen/de Prado methodology) — verdict holds
- Applied the Machine-Learning-for-Trading rigor our earlier runs lacked
  (`scripts/ml4t_train.py`): PURGED+EMBARGOED walk-forward CV (triple-barrier labels span
  42 bars → overlapping windows leak in naive CV), Information Coefficient (IC) evaluation,
  SHAP importance. Trained BOTH XGBoost (installed) and LightGBM on the pooled 18,777-
  candidate panel.
- **Leakage check (single 2025 split, price-only):** naive AUC 0.570 vs PURGED 0.567 —
  purging barely moves it, so our earlier ~0.56 was NOT leakage-inflated; methodology was
  sound. Single-split IC +0.10 looked promising.
- **But across ALL regimes (purged 5-fold walk-forward): IC +0.02, AUC 0.513** (XGB
  price-only); LightGBM same; **adding funding/OI/derivative features makes it WORSE
  (AUC 0.501, IC ~0)** — reconfirms feature overfitting. The 2025 IC +0.10 was
  regime-luck, not a stable signal.
- **VERDICT (now methodologically airtight): no stable learnable directional edge.**
  Best-practice ML4T CV + IC + XGBoost CONFIRMS the coin-flip finding across regimes. SHAP
  top features are regime/vol/ret context (atr_pct, dist-from-extremes, adx) — the same
  the rule system already uses. ML adds nothing; the edge is STRUCTURAL (cross-sectional
  momentum + funding), not ML prediction. Note: IC ~0.02 is too weak/unstable to use even
  as a probability-weighted size tilt (Grinold), so that path isn't pursued. The ML4T repo's
  real value to us was methodology (purged CV, IC, SHAP), which validated — not overturned —
  the existing conclusion.

## Per-bot ML/WF optimization (DONE, `scripts/run_botopt.py`)
- Optimized each quantlab bot individually via walk-forward parameter selection (train-fit
  params applied to untouched test windows — the ML-optimization that works, vs
  signal-gating which hurts). OOS 2025-26:
  - **Momentum: 1.07 → 1.86** (WF consistently picks ROC30/top-1 — fast momentum, tight
    concentration). Genuine improvement.
  - **Funding: 1.31 → 0.24** — WF-opt HURTS; its regime-sensitive params don't persist OOS.
    **Keep funding at its fixed default.**
  - **Combo: 1.74 → 2.25** (proper per-window inverse-vol blend, `run_wfopt.py`).
- **Lesson:** WF/parameter optimization is NOT universally good — it lifts momentum/combo
  but overfits funding. Optimize where it generalizes; leave regime-sensitive edges fixed.
- Other agents' bots (bot_kararli/dengeli/optimal/quantpro/rejim) use a different engine
  (1H top5 XGBoost on bot/engine/data_v31) — not faithfully runnable in our framework, so
  not re-optimized here (would be guessing at their pipeline).

## Overfitting honesty gate — Deflated Sharpe + PBO (DONE, `scripts/run_pbo.py`)
- Bailey/de Prado test of whether the combo's edge is real or a lucky grid pick, over a
  108-config combo family (trend ROC×topK blended with carry lb,n,rebal). T=1165 daily.
- **Deflated Sharpe Ratio = 0.986** (>0.95): after deflating for N=108 trials + skew
  (+1.57) + kurtosis (15.8), P(true Sharpe>0) ≈ 98.6%. Observed daily Sharpe 0.12 (ann
  ~2.30) vs null expected-max 0.06 (ann ~1.16) — comfortably above the selection-bias floor.
- **PBO = 0.031** (CSCV, S=16): in only 3% of IS/OOS splits does the IS-best config rank
  below median OOS → selection GENERALIZES (opposite of overfit). Median logit +1.91.
- **Verdict: the combo edge SURVIVES the honesty gate** — not a mirage of the grid. Caveats:
  (1) DSR deflates for the 108-config family; the session's cross-FAMILY N is larger, so
  treat DSR as upper-ish (PBO is family-internal and robust regardless — strong evidence);
  (2) survivorship still uncorrected (separate issue). Green-lights the next levers
  (min-variance weights, orthogonal 3rd sleeve, fractional-Kelly sizing) and paper-trading.

## H1 done RIGHT — breadth via EQUITIES, not shitcoins (`scripts/run_stocks.py`)
- User's correct pushback: 80 shitcoins = FAKE breadth (BTC-corr ~0.8 → effective N tiny;
  illiquid → slippage kills it; worst survivorship). Real breadth = a less-correlated,
  liquid, large universe = STOCKS. Cross-sectional momentum is the canonical equity anomaly
  (Jegadeesh-Titman), so it should transfer.
- **Result — it does, strongly.** Cross-sectional momentum on 30 liquid US large-caps
  (daily, top-5, 90d momentum): Full Sharpe 1.79, **OOS Sharpe 1.66**. Correlation to the
  crypto momentum sleeve **+0.18** (low → genuinely orthogonal). **Crypto+US momentum
  cross-asset blend: OOS Sharpe 2.13** (vs ~1.65 each alone) — real diversification breadth.
- The funding sleeve is crypto-specific (doesn't transfer); on equities the orthogonal
  partner would be a classic factor (value/low-vol/short-term-reversal) — future work.
- Caveats: yfinance is survivorship-capped (today's large caps; needs point-in-time S&P
  constituents for a clean magnitude); Sharpes are on the common (stock) trading-day
  calendar (crypto weekends dropped — correct for a cross-asset book). MTF disabled for
  the daily-stock path (yfinance datetime resolution vs merge_asof).
- **Takeaway:** the real H1/breadth lever is CROSS-ASSET (crypto + US equities momentum),
  not more crypto. BIST is a possible EM 3rd leg (momentum works in EM) but inferior on
  liquidity/cost/TRY-distortion/data — US first.

## Levers H2/H6/H4 tested on the 3-sleeve cross-asset book (`scripts/run_levers.py`)
- Sleeves (daily, common-day): crypto-trend, crypto-funding, US-momentum. Correlation
  matrix all low (−0.09..+0.18) → genuine diversification.
- **H2 (orthogonal 3rd sleeve) — WINS.** 2-sleeve (crypto) inv-vol OOS Sharpe 1.85 →
  **3-sleeve (cross-asset) 2.40, MaxDD −12%→−7%.** Adding US-momentum lifts Sharpe AND
  halves drawdown — the √N breadth is real. **New best system.**
- **H6 (weighting) — marginal.** equal/inv-vol/min-var ≈ 2.38/2.40/2.28; min-var does NOT
  beat inv-vol. Robust weighting matters more than the exact scheme; keep inverse-vol.
- **H4 (Kelly) — a sizing dial, not an edge.** f*≈17.8x (inflated by OOS-optimistic μ +
  fat tails + survivorship → true f* far lower). ¼-Kelly: CAGR 213% / MaxDD −24%;
  ½-Kelly −44%; full −72%. Sharpe is leverage-invariant. Honest ceiling ≤¼-Kelly given
  kurtosis; even that = −24% DD. Don't over-lever an inflated/survivorship-capped edge.
- **Cumulative best: 3-sleeve cross-asset book (crypto trend + crypto funding + US
  momentum), inverse-vol, OOS Sharpe ~2.40, MaxDD −7%** — up from the 2-sleeve combo.
  Caveats: 620 common-day sample (2023-03+, US/crypto overlap); survivorship in BOTH
  universes; equity funding-analog sleeve still future work.

## Fibonacci levels tested (controlled) — range-MR real, fib ratios not magic
- User thesis: in chop/range, price reverts at fib levels. Tested each level (0.236–0.786
  from 5 screenshots) on pooled chop bars (ER<0.3), range=rolling-50, vs position-matched
  NON-fib controls (`scripts/run_fib.py`). NO costs applied.
- **Position curve:** chop reversion strengthens toward the UPPER range (0.6–0.9 bins:
  +0.42% to +0.72% per 6 bars; price reverts DOWN from highs) — generic range MR, real and
  asymmetric (fade the upper range in chop is the one nugget). Lower-middle weak.
- **Fib-vs-control: MIXED/inconsistent.** 0.65 (+0.41% vs control), 0.618 (+0.13%), 0.377
  (+0.15%) beat their controls; but 0.5 (−0.05%), 0.705 (−0.07%) lose; 0.786 ~tie. No
  consistent sign → the specific Fibonacci ratios add NO edge beyond generic range
  position. "0.618 is magic" not supported (0.65, a non-classic level, scored highest).
- **Verdict:** the user's range-reversion intuition is partly real (upper-range fade in
  chop), but the edge is range POSITION, not the fib ratios — and at ~0.07%/bar pre-cost
  vs ~0.18% round-trip, it likely dies after costs (consistent with the earlier MR-sleeve
  rejection). Not promoted. Honest nugget for future: an ASYMMETRIC upper-range fade in
  chop could be explored as a sleeve, but must clear costs + correlation tests first.
- **All 7 screenshots evaluated (incl. the later 0.886 + extension levels):** 0.886 reverts
  +0.67% but its non-fib control +0.74% (control wins) → still range-position, not magic.
  EXTENSION levels (−0.377, 1.377, 1.618, 1.66, 2.618, 3.618) have ZERO samples in the chop
  regime — they are breakout/trend phenomena (price beyond the range), so they don't belong
  to the range thesis at all (they're TP-targets; trend/breakout concepts already shown to
  add no edge). Final: no Fibonacci ratio, across all configs, beats generic range position.

## Data provenance caveat
Phase 0 seeds the cache from `../uyg/src/mktdata/BTC_USDT_4h.csv` (repo's existing 4h
BTC, 2021→2026). Re-fetch via `data/fetch.py` before trusting absolute price levels.
Funding-strategy results are survivorship-capped (universe = today's survivors); the
literature estimates survivorship inflates crypto backtests ~15–22%/yr.

## PROP REGIME-TIMING (`scripts/run_propfirm_timing.py`) — the one real pass-lever beyond vol/structure
- Real-calendar test: simulate the 2-step challenge from EVERY start day, correlate pass/fail with
  the regime at start. Unconditional pass 42%. **Starting in a LOW recent-vol regime → 51% vs 40%
  in high-vol** (both mom20 & vol20 agree: calm market → smoother climb to target, fewer DD breaches).
  So regime-timing adds ~+9-11 points — a REAL, honest lever (timing the entry, not curve-fitting alpha).
- **Consolidated PASS-optimization playbook (honest, highest-EV first):**
  1. FIRM/STRUCTURE: Breakout static-DD 1-step (~48%) > HyroTrader trailing 2-step (~35%). Biggest lever.
  2. VOL LEVEL: ~15% constant (10%→35%, 15%→48%). Higher = faster to target until blowup rises.
  3. REGIME-TIMING: start the challenge when recent market vol is LOW (+~10 points). Use the screener.
  4. Smart de-risk (buffer/lock/governor) HURTS pass — do NOT use in pass mode.
  Stacking (Breakout 1-step + ~15% vol + low-vol start) could push pass toward ~55-60%.
- ⚠️ single-period (2023-26), survivorship, terciles noisy — direction credible, magnitude tentative.

## ★ OPTIMAL FUND BOT — firm head-to-head (`scripts/run_firm_compare.py`) — DECISION
- Real-calendar pass simulation, combo @15% vol, regime-timed: HyroTrader 2-step trailing 42%/52%
  (uncond/low-vol-start); HyroTrader 1-step trailing 28%/20% (tight 6% trailing = HARDER);
  **Breakout 1-step STATIC 49%/53% ← BEST.** Static DD beats trailing (no penalty for giving back
  from a peak → smoother climb to target); 1-step single-hurdle is fast.
- **OPTIMAL FUND-BOT RECIPE (final):** (1) Breakout 1-step STATIC DD (easiest pass ~53%),
  (2) combo edge + ~15% constant vol, (3) START in a low-vol regime (screener), (4) ATR-stop ≤3%
  per trade + −3% intraday self-stop, (5) Top-3 momentum + funding long/short (40%-concentration
  auto-satisfied). Do NOT add buffer/lock de-risk (proven to hurt passing).
- **Two-firm strategy:** validate forward on HyroTrader (Bybit testnet + 700 coins), then take the
  actual challenge on Breakout (static DD, easier pass). Later run both for firm-risk diversification.
- ⚠️ Testnet execute currently BLOCKED by Bybit retCode 10024 (regulatory/KYC restriction on the
  account — region/KYC gating, NOT our code/key/balance). User-side Bybit account issue to resolve.

## ★ BREAKOUT READINESS REPORT — NOT viable for us; HyroTrader is the firm (eligibility flip)
- Researched Breakout's real rules: **(1) Turkey is RESTRICTED** (KYC blocks at funded stage; recommended
  before buying), **(2) NO usable API** — browser "Breakout Terminal" (Kraken-backed, order-book from
  Binance/Bybit/OKX); our automated bot cannot connect, **(3) fee NON-refundable** (except one KYC-reject
  refund), daily loss 3% (tighter). → **Breakout is OUT for us on 3 counts (region + automation + cost).**
- **HyroTrader = the correct firm:** NO country restrictions, NO KYC for eval (KYC only at funded), full
  Bybit/Binance API for bots, real perps+funding (700 coins), testnet, 80→90% split. CRUCIALLY: on
  HyroTrader you trade THEIR Bybit entity → the personal Bybit region block (our testnet retCode 10024)
  does NOT apply to the funded account (their FAQ confirms). So Turkey is fine on HyroTrader.
- **No loss switching:** Breakout pass ~53% vs HyroTrader-2step low-vol-start ~52% — essentially equal.
  The eligibility-correct choice is also nearly as strong on pass-rate, and it's what we already built/tested.
- **10024 reframe:** that block was the USER's personal Bybit testnet (Turkey-restricted), NOT a HyroTrader
  issue. For independent forward-validation use HyroTrader's own demo, or paper (the `hyro` paper bot), or
  Binance testnet — not the personal Bybit testnet.
- **Velotrade = strong #2 (algo-native):** full REST/WebSocket API on every account, no SL-time rule, no
  daily profit cap, built for bots. Evaluate as the diversification firm after HyroTrader.
- **Executor default firm flipped breakout1 → hyro2.** Recipe unchanged (combo + ~15% vol + regime-gate +
  maker), now on HyroTrader's trailing DD.

## ★ HyroTrader vs Velotrade — 2-firm strategy comparison
- **Velotrade (researched):** crypto-only, HK-based, launched early-2026, up-to-$200K, up-to-90% split.
  Rules: 2-step 10%/5% DD10% daily5%; 1-step Classic 10% DD7% daily4%; 1-step Pro 10% DD3% STATIC daily3%.
  EOD-trailing DD (never intraday). **Full REST+WebSocket API on EVERY account, no fee/approval (best API).**
  NO per-trade SL mandate, NO consistency rule, NO daily profit cap. Crypto perps WITH funding (DXtrade,
  simulated env). Price $35 (1-step Pro $5K) up. Platform DXtrade.
- **Two open gaps for Velotrade (user must verify):** (a) Turkey in their Restricted-Territories "Schedule 1"?
  (terms/KYC — could not retrieve list), (b) tradeable coin count (breadth — DXtrade list likely 20-50, far
  fewer than HyroTrader's 700). Our cross-sectional momentum NEEDS breadth (<20 coins degrades it), so a
  small coin list weakens our edge on Velotrade despite its superior API.
- **VERDICT (2-firm):** PRIMARY = HyroTrader (Turkey-confirmed-OK, 700-coin breadth = full edge, real Bybit,
  API, testnet). SECONDARY = Velotrade IF (Turkey allowed AND coins ≥~30) — best algo rules but newer/less
  trust + likely lower breadth + simulated DXtrade. Breakout ELIMINATED (Turkey-restricted + no API).
- Both firms use EOD-trailing DD (intraday swings don't breach) — favorable for our daily-rebalance bot.

## Velotrade variants tested (`run_firm_compare.py`) — 2-step TIES HyroTrader
- Ran our edge vs Velotrade's structures (vol 15%, regime-timed, real calendar):
  Velotrade 2-step (trail 10%/daily5%) 42%/52% — IDENTICAL to HyroTrader 2-step (same rules);
  Velotrade 1-step Classic (trail 7%/daily4%) 32%/21%; Velotrade 1-step Pro (STATIC 3%/daily3%)
  32%/23% (3% DD too tight at 15% vol → needs ~6-7% vol; cheapest at $35 though).
- **Velotrade 2-step pass-rate ties HyroTrader (52%)** — so on passing they're equal. Decision
  hinges on: breadth (HyroTrader 700 coins >> Velotrade's likely 20-50 DXtrade list — our
  cross-sectional momentum NEEDS breadth, sim uses same 20-coin returns so understates this gap),
  maturity (HyroTrader established vs Velotrade new), API (Velotrade better). Net: HyroTrader stays
  primary on breadth+trust; Velotrade co-primary IF Turkey-allowed + coin-count ≥~30.

## SECOND-BOT attempt — FundingPips-native DIVERSIFIED book (`run_fpips_book.py`) — NO edge, don't integrate
- Tried the one untested approach: apply crypto's DIVERSIFICATION lesson to FX/index/metal — blend
  FX-carry + FX-MR(1d) + macro-TSMOM inverse-vol (train-fit). Cost 6bps.
- **Result: IS Sharpe −0.11 (NEGATIVE), OOS 1.08, only 6/12 years positive.** Individual sleeves OOS
  carry 0.88 / mr 0.87 / tsmom 0.03; the blend's OOS 1.08 is REGIME-LUCK (IS<0; carried by 2020 +
  2025-26; deeply negative 2017/2023). Diversification gave a small OOS lift but CANNOT manufacture a
  robust edge from weak/negative components — unlike crypto (momentum + funding were both genuinely
  positive, orthogonal-STRONG). FX/index has no orthogonal-strong sleeve in our daily toolkit.
- **VERDICT: do NOT integrate a FundingPips-native second bot — no validated edge** (IS negative =
  not deployable, OOS is luck). A real forex bot would need intraday data/infra or a genuinely
  different signal (we don't have it). Stick with: crypto edge on crypto-native firms (HyroTrader,
  auto) + the manual-signal mode (any crypto firm). Forex/CFD venues (FundingPips) stay OUT.

## ★ BOT 2 = FX CARRY (`run_fx_carry_opt.py`) — the ONE real forex factor (modest)
- Optimized FX carry on 7 G10 pairs: **raw carry IS 0.28 / OOS 0.92, 9/12 years positive** — best
  variant. carry-to-vol ~same (IS 0.14). **Trend-filter HURT badly (IS −0.48, 2/12)** — clever idea
  failed on test again; raw carry wins. Low-turnover → cost-robust. This is a GENUINE FX factor
  (canonical carry, ~0.5 Sharpe academic norm; ours in-band), 9/12 years = decent single-factor robustness.
- **Honest ceiling: MODEST.** ~0.3-0.9 Sharpe → too slow/weak to reliably pass a prop +10% target
  (NOT a challenge-passer alone); good as a slow-income / diversification SIGNAL on forex/CFD venues
  (FundingPips), manual. Carry carries crash-tail risk (risk-off). So Bot 2 = FX-carry SIGNAL, not auto-passer.
- **Two-bot final:** Bot 1 = crypto combo (strong, DSR/PBO-real) on crypto firms (auto/manual);
  Bot 2 = FX carry (modest-real) on forex/CFD firms (manual signal). FundingPips now has a real—if
  modest—signal to trade manually. Don't expect it to pass challenges fast; it's slow carry income.

## FX CARRY (Bot 2) full stats (`run_fx_carry_stats.py`)
- Risk-return 2015-26: full Sharpe 0.35 / +3%yr / -16% MaxDD; IS 0.28 /+2%; OOS 0.92 /+7% /-7%.
  Consistency: 9/12 years positive (75%), 60% positive months, 53% positive days; best/worst year
  +7%/-5%, best/worst month +6%/-6% (carry-crash tail).
- Prop pass-prob (HyroTrader 2-step, bootstrap haircut 0.6): 10% vol 16%, 15% 28%, 20% 29% —
  FAR below crypto (42-52%) because carry is slow (~3-7%/yr → can't hit +10% target fast without
  high vol that opens crash/DD risk). NOT a challenge-passer; it's a slow-income/diversification signal.
- Bottom line: Bot1 crypto ~1.8 Sharpe/42-52% pass = the funded-account engine; Bot2 FX carry
  ~0.35-0.9 Sharpe/16-29% pass = modest diversifier, hold for income/manual not for passing challenges.

## ★ OTHER MARKETS map — EQUITIES is the standout (proven edge, best pass-rate)
- **EQUITIES (US single-stock momentum, `run_equity_prop_stats.py`):** OUR ALREADY-PROVEN 3rd sleeve.
  Full Sharpe 1.57, IS 1.52, OOS 1.66, +30%/yr, 4/4 years positive, 64% months. **Prop pass 73-79%**
  (single-phase +8%/daily-5%/total-10% static) — HIGHER than crypto (42-52%) because single-phase +
  high CAGR + static DD. Orthogonal to crypto. Firm: Trade The Pool (single-stock prop, automation
  allowed ≤2req/min + approval, single-phase, 80%) or manual /sinyal. CAVEAT: 4/4 years is only
  2023-26 (AI-megacap bull + yfinance survivorship) → magnitude inflated; realistic forward ~0.8-1.2
  Sharpe. Turkey eligibility on Trade The Pool to verify.
- **FUTURES (Apex/TopStep/MyFundedFutures):** biggest/cheapest/most-accessible prop category, likely
  Turkey-OK. BUT funded accounts mostly allow only SEMI-auto (TradingView webhook / alerts), NOT full
  bots → fits our MANUAL /sinyal approach. Edge UNTESTED by us (managed-futures TSMOM was weak recently;
  needs a futures-native test on ES/NQ/CL/GC/ZB).
- **Market-by-edge ranking:** crypto (strong, ~1.8) ≈ equities (strong, 1.66 but survivorship-inflated)
  >> forex carry (modest, 0.9) > futures (untested) >> single index/metal (weak/regime-luck).
- **Best UNTAPPED move: EQUITIES** — we already have the validated edge + best pass-rate; only need a
  stock prop firm (Trade The Pool) that accepts Turkey + allows our (semi-)automation. Futures = big
  but needs a fresh edge hunt + semi-auto only.

## EQUITY pass re-test (Trade The Pool REAL rules) + FUTURES test — Q1/Q2 answers
- **Q1 EQUITIES (Trade The Pool):** Turkey NOT restricted ✅. Real Flex rules 6% target / 2% daily /
  4% max-DD (STATIC, tight) / 70% split / $53-120. Re-tested pass with REAL rules (prior 73-79% used
  loose 10% DD = misleading): **~63-66% pass at 6-8% vol** (4% vol → 43%). Still good (> crypto 42-52%).
  Execution: raw bots BANNED unless approved → **Signal Stack (semi-auto, 2mo free) or MANUAL /hisse**.
  DECIDED: signal-based, firm = Trade The Pool. Caveat: 70% split (lower), survivorship-inflated edge.
- **Q2 FUTURES (`run_futures.py`):** 13 contracts (ES/NQ/YM/GC/SI/HG/CL/NG/ZB/ZN/6E/6J/6B). TSMOM +
  cross-sectional momentum. **NO edge: best TSMOM-60 IS 0.20/OOS 0.17 (~zero), all weak/negative,
  XSEC catastrophic (-34..-48% DD), pass only 23-29%.** Consistent with macro-ETF TSMOM negative.
  VERDICT: do NOT pursue futures — no validated edge (managed-futures trend weak this regime). Futures
  props are cheap/Turkey-OK but edge-less = gambling. Focus crypto + equities.
- **FINAL market verdict:** deployable edges = CRYPTO (strong) + EQUITIES (strong, Trade The Pool,
  Turkey-OK, ~65% pass) + FX-carry (modest). Futures = NO. Single index/metal = NO. Forex-ex-carry = NO.

## 'tirad' live bot reality + directional-trend test (`run_trend_directional.py`)
- The dashboard "tirad" card (Binance Futures TESTNET, +$419/2d) = live_bot.py: multi-coin 4H
  Donchian(40)+Supertrend(10,3) AGREEMENT + BTC-200EMA align + regime-gate(≥2) + ML meta-label +
  fractional-Kelly. CORRECTION to earlier read: current 8 positions are ALL SHORT at ×1 leverage
  (NOT 20×), 0 closed trades → the +$419 is 100% UNREALIZED on a 2-day market down-move the shorts
  caught. No realized track record.
- **Why our combo didn't catch it: directional (tirad) vs cross-sectional/neutral (combo).** tirad
  takes whole-market directional bets (short everything in a downtrend); combo is Top-3 long + funding
  neutral → doesn't profit from a broad selloff by design.
- **Backtested tirad's directional logic honestly (2730 trades):** IS (≤2024) +0.131R/35% win, but
  **OOS 2025-26 −0.023R (NEGATIVE), 30% win, R-Sharpe −0.41.** By-year: 2021 +0.26R, 2022 +0.14R,
  2023 +0.13R, 2024 +0.04R, **2025 −0.063R (−36R, whipsaw)**, 2026 +0.07R. Directional crypto trend
  is REGIME-DEPENDENT: profits in trending years, bleeds in chop (2025). The +$419 is the lucky 2-day
  tail of an OOS-negative strategy. The regime-gate did NOT prevent the 2025 bleed.
- **VERDICT: do NOT optimize our disciplined bots toward the tirad wave — it's chasing the lucky tail
  of a strategy that's OOS-negative/whipsaw-prone.** Combo's neutrality is WHY it avoided the 2025 -36R
  bleed (feature, not bug). A regime-gated directional sleeve only helps IF regime-detection reliably
  avoids chop — which the existing gate failed to do in 2025. Recency/survivorship bias trap avoided.

## Safe trend entry? chop-filter test (`run_trend_filtered.py`) — can't avoid chop, but ADX helps long-run
- Tested principled chop filters on directional trend (Donchian+Supertrend+BTC-dir): base OOS -0.005R;
  **ADX≥30 → OOS +0.081R (positive!), IS +0.167R** (trend has long-run positive expectancy, strength-
  filter helps). ER≥0.3 hurt; strict ER0.4+ADX35 worst (OOS -0.070R, over-filter). **BUT 2025 stays
  NEGATIVE in EVERY variant (-14 to -50R)** — no filter avoids the chop-year bleed. Whipsaw is intrinsic
  to trend-following; "safe entry that avoids chop losses" is NOT achievable.
- **Honest synthesis:** trend-following = long-run positive expectancy (IS +0.17R, OOS +0.08R w/ ADX)
  but LOSES in chop years (2025) by nature — can't be filtered away. The way to USE it: a SMALL
  ADX-filtered directional sleeve ADDED to the diversified book (accept chop-year losses for trend-year
  gains; size small so the bleed is tolerable; diversification with the neutral combo smooths it).
  NOT a "safe always-win" trend bot. Managed-futures funds live with the same chop-year drawdowns.

## ★ FINAL trend verdict — directional-trend sleeve added to combo (`run_trend_combine.py`) — HURTS
- Built ADX≥30 directional-trend as a daily-return sleeve (standalone OOS Sharpe 0.66, corr +0.28 to
  crypto_trend = overlaps momentum, not orthogonal). Blended into combo (inverse-vol, train-fit):
  **combo 1.85 → combo+trend 1.37 (OOS Sharpe DOWN), MaxDD -12%→-15%.** By-year: trend hurt 2023
  (1.18→0.79), 2024 (0.92→-0.19), 2025 (2.18→1.23); only helped 2026 (0.91→1.70, current trend regime).
- **DEFINITIVE: directional trend does NOT add risk-adjusted value to our book — it HURTS (1.85→1.37).**
  Tested 3 ways: alone (OOS-negative), chop-filtered (can't avoid chop bleed), as a sleeve (dilutes
  + adds variance). The "tirad +42%" wave is the lucky unrealized 2-day tail of a strategy that, properly
  measured & combined, lowers our Sharpe. Combo's NEUTRALITY (1.85) beats adding trend (1.37) — "not
  catching the wave" is mathematically correct. Trend only helps IF you bet "now is a trend regime"
  (market-timing, unreliable). Closing the trend thread: combo + equities + FX-carry stays the system.
