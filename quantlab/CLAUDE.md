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
- **Engine bug fixed in passing (`signals/mtf.py`):** pandas-3 `merge_asof` now enforces
  matching datetime resolution; ccxt data is `[ms]`, resample yields `[us]/[ns]` → the MTF
  merge raised `MergeError`. Coerced both keys to `ns` (`.as_unit("ns")`) — robust to any
  data source (ccxt/yfinance/resample), all 69 tests still pass.

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
