import unittest

from helpers import c, make
from pa.structure import find_swings, detect_structure
from pa.types import Bias, SwingType


def zigzag_up():
    seq = [
        (10, 11, 9, 10),
        (10, 10.5, 8, 8.5),
        (8.5, 9, 7, 7.2),
        (7.2, 8, 6.5, 7.8),
        (7.8, 12, 7.5, 11.5),
        (11.5, 13, 11, 12.5),
        (12.5, 12.8, 10.5, 11),
        (11, 14, 10.8, 13.5),
        (13.5, 14.2, 12.5, 13),
        (13, 13.5, 12, 12.2),
    ]
    return make([c(*s) for s in seq])


class TestStructure(unittest.TestCase):
    def test_swings_classified(self):
        sw = find_swings(zigzag_up(), k=1)
        kinds = {s.kind for s in sw}
        self.assertIn(SwingType.HIGH, kinds)
        self.assertIn(SwingType.LOW, kinds)

    def test_events_and_bias(self):
        events, bias = detect_structure(zigzag_up(), k=1)
        self.assertIn(bias, (Bias.BULLISH, Bias.BEARISH, Bias.NEUTRAL))
        self.assertTrue(any(e.bias == Bias.BULLISH for e in events))
        for e in events:
            self.assertIn(e.kind, ("BOS", "CHoCH"))

    def test_no_lookahead(self):
        events, _ = detect_structure(zigzag_up(), k=1)
        for e in events:
            self.assertGreater(e.index, e.swing_index)


if __name__ == "__main__":
    unittest.main()
