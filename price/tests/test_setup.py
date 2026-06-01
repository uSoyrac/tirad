import unittest

from helpers import c, make
from pa.setup import build_setup
from pa.analyze import analyze
from pa.types import Side
from pa.risk import MAX_RATIO

# Elle tasarlanmış tam bullish ICT zinciri (make_sample.py ile aynı):
# eşit highs (BSL hedef 142) → SSL havuzu 100 → SSL sweep → BOS → OB'ye dönüş.
LONG_CHAIN = [
    (100, 101, 99, 100), (100, 102, 99, 101),
    (101, 142, 100, 140),
    (140, 141, 128, 129), (129, 131, 127, 130),
    (130, 142, 129, 140),
    (140, 141, 126, 127), (127, 129, 116, 117),
    (117, 119, 100, 101),
    (101, 108, 99.5, 107), (107, 112, 106, 111), (111, 113, 110, 112),
    (112, 114, 100, 102),
    (102, 106, 101, 105), (105, 110, 104, 109), (109, 111, 108, 110),
    (110, 111, 93, 103),
    (103, 104, 100, 101),
    (101, 118, 101, 117),
    (117, 124, 116, 123), (123, 126, 122, 125), (125, 127, 124, 126),
    (126, 127, 110, 111),
    (111, 116, 109, 115),
]


def synthetic_long():
    return make([c(*r) for r in LONG_CHAIN])


class TestSetup(unittest.TestCase):
    def test_short_series_rejected(self):
        s = build_setup(make([c(10, 11, 9, 10) for _ in range(5)]), k=2)
        self.assertFalse(s.valid)
        self.assertIsNotNone(s.rejected)

    def test_choppy_no_trade(self):
        rows = []
        for i in range(40):
            base = 100 + (i % 2)
            rows.append(c(base, base + 0.5, base - 0.5, base))
        s = build_setup(make(rows), k=2)
        self.assertFalse(s.valid)

    def test_valid_long_chain(self):
        # Bu zincir TAM olduğundan geçerli bir LONG setup ÜRETMELİ.
        candles = synthetic_long()
        s = build_setup(candles, k=2, symbol="TEST/USDT")
        self.assertTrue(s.valid, msg=f"beklenmeyen reddetme: {s.rejected}")
        self.assertEqual(s.side, Side.LONG)
        self.assertGreaterEqual(s.rr, 2.0)  # asimetri kuralı
        # stop yapısal: giriş ile target arasında olmamalı, girişin altında
        self.assertLess(s.stop, s.entry)
        self.assertGreater(s.target, s.entry)

    def test_valid_setup_leverage_feasible(self):
        candles = synthetic_long()
        res = analyze(candles, entry_tf="1h", symbol="TEST/USDT")
        self.assertTrue(res.setup.valid)
        self.assertIsNotNone(res.plan)
        self.assertTrue(res.plan.feasible)
        self.assertLess(res.plan.max_leverage * res.setup.stop_pct, MAX_RATIO)

    def test_htf_conflict_blocks_trade(self):
        # Giriş LONG ister; üst TF net bearish ise işlem engellenmeli.
        entry = synthetic_long()
        bear_rows = [
            (150, 151, 149, 150), (150, 152, 148, 149),
            (149, 151, 140, 141),
            (141, 143, 139, 142), (142, 144, 141, 143),
            (143, 145, 130, 131),
            (131, 140, 130, 139), (139, 141, 138, 140),
            (140, 142, 128, 129),
            (129, 135, 127, 134), (134, 136, 133, 135), (135, 137, 134, 136),
            (136, 138, 120, 121),
            (121, 128, 120, 127), (127, 129, 126, 128), (128, 130, 127, 129),
            (129, 131, 118, 119),
        ]
        bear = make([c(*r) for r in bear_rows])
        res = analyze(entry, bear, entry_tf="1h", htf_tf="4h", symbol="TEST/USDT")
        # giriş LONG, üst TF bearish -> çelişki -> reddedilmeli
        self.assertEqual(res.setup.side, Side.LONG)
        self.assertFalse(res.setup.valid)
        self.assertIn("TF çelişkisi", res.setup.rejected or "")


if __name__ == "__main__":
    unittest.main()
