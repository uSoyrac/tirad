export const meta = {
  name: 'winc-corpus-mining',
  description: 'Deep-read the Winning Circle corpus in parallel, extract only testable rule-based hypotheses, flag what our 4h/funding/OI data can validate, synthesize',
  phases: [
    { title: 'Read', detail: 'one agent per concept-cluster reads the extracted text and pulls testable hypotheses' },
    { title: 'Synthesize', detail: 'rank by testability-with-our-data × novelty vs already-tested; pick what to build' },
  ],
}

const TXT = '/tmp/winc_txt'
const CLUSTERS = [
  { key: 'sessions_killzone', glob: 'kz*.txt SSBSS* spacemakro* *Vadeli*' },
  { key: 'smt_divergence', glob: 'SMT*' },
  { key: 'orderflow_heatmap', glob: '*Isi_Harita* *Likidite* *Comulative* *oi_cvd* *Footprint* *Hacim_Profili* Order_Block* indik*' },
  { key: 'onchain_macro_valuation', glob: 'On*hain* *Mayer* *URPD* *Makro* *Haftalik* Analysis_of_Bitcoin* Market_Analizi*' },
  { key: 'winc_setups', glob: 'RektProof* Trapped* Spartan* Columns* Auctions* Multibook* Fibonacci* *Arbitraji* Terimler* PA_Terimleri*' },
]

const FINDING_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['cluster', 'concepts'],
  properties: {
    cluster: { type: 'string' },
    concepts: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        required: ['name', 'summary', 'testable', 'hypothesis', 'how_to_test'],
        properties: {
          name: { type: 'string' },
          summary: { type: 'string', description: 'the rule/concept in 1-2 sentences' },
          testable: { type: 'string', enum: ['yes_our_data', 'needs_finer_data', 'needs_L2_orderbook', 'discretionary_no'],
            description: 'can it be backtested with 4h/1d OHLCV + funding(3 exch) + OI/LS(2024+) for BTC/ETH/20 alts?' },
          hypothesis: { type: 'string', description: 'a falsifiable hypothesis, or "" if untestable' },
          how_to_test: { type: 'string', description: 'concrete test design with our data, or why it cannot be tested' },
        },
      },
    },
  },
}

phase('Read')
const found = await parallel(CLUSTERS.map((c) => () =>
  agent(
    `Read the Winning Circle (Turkish crypto-trading mentorship) materials for the "${c.key}" cluster.\n` +
    `Run: cd ${TXT} && for f in ${c.glob}; do echo "=== $f ==="; cat "$f" 2>/dev/null | head -400; done\n` +
    `(Files are pdftotext output; some are sparse because the source was image slides — note that.)\n\n` +
    `Extract every distinct CONCEPT/STRATEGY. For each, judge honestly whether it is backtestable with OUR data: ` +
    `4h+1d OHLCV+volume (full history, 20 coins incl BTC/ETH), 8h funding rates (binance/bybit/okx), ` +
    `OI + long/short + taker-buy/sell ratio (2024-06+). We do NOT have: tick/1m data, level-2 order book, ` +
    `liquidation heatmaps, footprint, or true CVD. Be skeptical — most ICT/Wyckoff/price-action ideas are ` +
    `discretionary and NOT systematically testable. Only mark 'yes_our_data' if you can write a concrete ` +
    `rule-based test with the data we have. Give a falsifiable hypothesis for the testable ones.`,
    { label: `read:${c.key}`, phase: 'Read', schema: FINDING_SCHEMA },
  ),
)).then((r) => r.filter(Boolean))

phase('Synthesize')
const summary = await agent(
  `Synthesize the Winning Circle corpus mining into an honest, actionable report for a quant who already has a ` +
  `validated diversified book (trend Top-3 momentum + funding-positioning, OOS Sharpe ~1.74) and has ALREADY ` +
  `tested and REJECTED (no OOS edge) these: order-flow 1st/2nd derivatives, exhaustion, CVD proxy, funding/OI as ` +
  `ML features, single-asset trend, mean-reversion, asymmetric leveraged sniper.\n\n` +
  `All cluster findings (JSON): ${JSON.stringify(found)}\n\n` +
  `Produce: (1) a table of every concept with testable-flag; (2) the SHORT-LIST of hypotheses that are BOTH ` +
  `testable-with-our-data AND genuinely novel vs what we already tested (e.g. session/killzone time-of-day filter, ` +
  `SMT BTC/ETH divergence, Mayer-multiple/on-chain valuation regime filter) — for each give the exact test design ` +
  `and how it would integrate with the existing combo; (3) a blunt list of what is NOT testable (needs L2/tick/` +
  `liquidation data or is discretionary) so we don't waste effort. Be brutally honest: if the corpus offers no ` +
  `new testable edge beyond what we have, say so. No holy-grail hype.`,
  { label: 'synthesize', phase: 'Synthesize' },
)

return { found, summary }
