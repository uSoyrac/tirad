import unittest

import helpers  # noqa: F401  (import yolunu kurar)
from pa.risk import leverage_plan, position_size, MAX_RATIO


class TestRisk(unittest.TestCase):
    def test_stop_2pct_example(self):
        # workflow örneği: stop %2 → max 40x, önerilen 30x
        plan = leverage_plan(2.0)
        self.assertTrue(plan.feasible)
        self.assertEqual(plan.max_leverage, 40)
        self.assertEqual(plan.recommended, 30)
        self.assertLess(plan.max_leverage * plan.stop_pct, MAX_RATIO)

    def test_rule_strictly_below_90(self):
        for stop in [0.5, 1.0, 1.5, 2.0, 3.3, 5.0, 9.0]:
            plan = leverage_plan(stop)
            if plan.feasible:
                self.assertLess(plan.max_leverage * stop, MAX_RATIO)

    def test_infeasible_wide_stop(self):
        plan = leverage_plan(95.0)
        self.assertFalse(plan.feasible)
        self.assertEqual(plan.max_leverage, 0)

    def test_position_size_loss_equals_risk(self):
        ps = position_size(portfolio=1000, stop_pct=2.0, leverage=30, risk_pct=1.0)
        self.assertEqual(ps.risk_amount, 10.0)
        self.assertAlmostEqual(ps.notional * 0.02, ps.risk_amount)
        self.assertAlmostEqual(ps.margin, ps.notional / 30)


if __name__ == "__main__":
    unittest.main()
