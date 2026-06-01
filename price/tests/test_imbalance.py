import unittest

from helpers import c, make
from pa.imbalance import find_fvgs
from pa.types import Bias


class TestFVG(unittest.TestCase):
    def test_bullish_fvg(self):
        # mum0 high=10; agresif yükseliş; mum2 low=11 > 10 → gap [10,11]
        candles = make([
            c(9, 10, 8, 9.5),
            c(9.5, 13, 9.5, 12.8),
            c(12, 14, 11, 13.5),
        ])
        bull = [f for f in find_fvgs(candles) if f.bias == Bias.BULLISH]
        self.assertEqual(len(bull), 1)
        self.assertEqual(bull[0].bottom, 10.0)
        self.assertEqual(bull[0].top, 11.0)

    def test_bearish_fvg(self):
        candles = make([
            c(11, 12, 10, 10.5),
            c(10.5, 10.5, 7, 7.2),
            c(8, 9, 6, 6.5),
        ])
        bear = [f for f in find_fvgs(candles) if f.bias == Bias.BEARISH]
        self.assertEqual(len(bear), 1)
        self.assertEqual(bear[0].bottom, 9.0)
        self.assertEqual(bear[0].top, 10.0)

    def test_no_fvg_overlap(self):
        candles = make([
            c(10, 11, 9, 10.5),
            c(10.5, 11.5, 9.5, 11),
            c(11, 12, 10, 11.5),
        ])
        self.assertEqual(find_fvgs(candles), [])


if __name__ == "__main__":
    unittest.main()
