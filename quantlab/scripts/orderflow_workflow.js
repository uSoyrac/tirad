export const meta = {
  name: 'orderflow-derivative-research',
  description: 'Test velocity/acceleration order-flow feature families for OOS trend decision-quality lift, adversarially verify, synthesize a composite',
  phases: [
    { title: 'Test', detail: 'one agent per feature family runs feature_lab.py and reports OOS AUC lift + gate curve' },
    { title: 'Verify', detail: 'adversarially re-check each family that claims a lift (overfit / single-coin / IS-OOS gap)' },
    { title: 'Synthesize', detail: 'combine the verified-real features into a composite recommendation' },
  ],
}

const LAB = 'cd /Users/uygar/trade/quantlab && .venv/bin/python scripts/feature_lab.py'
const FAMILIES = ['volume', 'price_action', 'cvd_proxy', 'vwap', 'volatility', 'funding', 'oi_ls_taker', 'exhaustion']

const FAM_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['family', 'oos_auc', 'oos_lift', 'best_gate_win', 'best_gate_exp', 'real_lift', 'note'],
  properties: {
    family: { type: 'string' },
    oos_auc: { type: 'number', description: 'baseline+family OOS AUC' },
    oos_lift: { type: 'number', description: 'OOS AUC lift over baseline (can be negative)' },
    best_gate_win: { type: 'number', description: 'best OOS win-rate % from the gate curve' },
    best_gate_exp: { type: 'number', description: 'best OOS expectancy (ATR) from the gate curve' },
    real_lift: { type: 'boolean', description: 'true only if OOS lift > +0.01 AND IS/OOS gap not blown out (not overfit)' },
    note: { type: 'string', description: 'one-line honest read' },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['family', 'confirmed_real', 'reason'],
  properties: {
    family: { type: 'string' },
    confirmed_real: { type: 'boolean' },
    reason: { type: 'string' },
  },
}

phase('Test')
const tested = await parallel(FAMILIES.map((f) => () =>
  agent(
    `You are testing whether the order-flow feature family "${f}" raises out-of-sample trend decision quality.\n` +
    `Run EXACTLY this command and read its output:\n  ${LAB} ${f}\n\n` +
    `The output shows baseline vs baseline+family OOS AUC, the OOS AUC lift, family-alone AUC, the IS/OOS gap, and a gate curve (win% and expectancy at top-X% predicted P(win)).\n` +
    `Report the numbers. real_lift=true ONLY if OOS lift > +0.01 AND the IS/OOS AUC gap for baseline+family is not dramatically worse than baseline (i.e. not just in-sample overfit). Be skeptical and honest.`,
    { label: `test:${f}`, phase: 'Test', schema: FAM_SCHEMA },
  ),
)).then((r) => r.filter(Boolean))

const lifters = tested.filter((t) => t && t.real_lift)
log(`Families claiming a real OOS lift: ${lifters.map((l) => l.family).join(', ') || '(none)'}`)

phase('Verify')
let verdicts = []
if (lifters.length) {
  verdicts = await parallel(lifters.map((l) => () =>
    agent(
      `Adversarially verify the claim that order-flow family "${l.family}" gives a REAL out-of-sample edge (claimed OOS AUC lift ${l.oos_lift}).\n` +
      `Re-run both:\n  ${LAB} ${l.family}\n  ${LAB} base\n` +
      `Try to REFUTE the lift. A lift is NOT real if: (a) OOS AUC lift <= +0.01, (b) the IS/OOS AUC gap for baseline+family is much larger than baseline (in-sample overfit), or (c) the family-ALONE OOS AUC is ~0.50 (no standalone signal). Default to confirmed_real=false if uncertain.`,
      { label: `verify:${l.family}`, phase: 'Verify', schema: VERDICT_SCHEMA },
    ),
  )).then((r) => r.filter(Boolean))
}

const confirmed = verdicts.filter((v) => v && v.confirmed_real).map((v) => v.family)
log(`Confirmed-real families after adversarial check: ${confirmed.join(', ') || '(none)'}`)

phase('Synthesize')
const summary = await agent(
  `Synthesize the order-flow derivative research into an honest recommendation.\n\n` +
  `Per-family test results (JSON): ${JSON.stringify(tested)}\n\n` +
  `Adversarial verdicts (JSON): ${JSON.stringify(verdicts)}\n\n` +
  `Confirmed-real families: ${JSON.stringify(confirmed)}\n\n` +
  `Write a concise markdown report: (1) a table of every family with OOS AUC lift, best gate win%/expectancy, and real/overfit verdict; (2) which derivative/acceleration features (if any) genuinely separate true vs false trends OOS — explicitly evaluate the user's "Orderflow Exhaustion" (2nd-derivative) thesis; (3) a concrete recommendation: which features to add to the pooled meta-label gate, or an honest "none beat the price baseline". Be brutally honest — if nothing lifts OOS, say so plainly and explain why (these features overfit in-sample / no OOS signal). Do NOT oversell.`,
  { label: 'synthesize', phase: 'Synthesize' },
)

return { tested, verdicts, confirmed, summary }
