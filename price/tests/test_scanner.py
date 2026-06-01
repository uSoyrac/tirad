import unittest

from helpers import c, make
from pa.scanner import scan
from test_setup import LONG_CHAIN  # tam bir geçerli LONG zinciri


def long_candles():
    return make([c(*r) for r in LONG_CHAIN])


def flat_candles():
    # konsolidasyon -> setup yok
    return make([c(100 + (i % 2), 100.5 + (i % 2), 99.5 + (i % 2),
                   100 + (i % 2)) for i in range(40)])


class TestScanner(unittest.TestCase):
    def test_finds_valid_setup(self):
        def fetcher(symbol, tf, limit):
            return long_candles()
        rep = scan(["BTC/USDT"], htf=None, fetcher=fetcher)
        self.assertEqual(len(rep.valid_setups), 1)
        self.assertEqual(rep.valid_setups[0].symbol, "BTC/USDT")

    def test_flat_market_no_setup(self):
        def fetcher(symbol, tf, limit):
            return flat_candles()
        rep = scan(["BTC/USDT"], htf=None, fetcher=fetcher)
        self.assertEqual(rep.valid_setups, [])

    def test_fetch_error_isolated(self):
        # bir sembol patlar, diğeri geçerli — tarama devam eder
        def fetcher(symbol, tf, limit):
            if symbol == "BAD/USDT":
                raise OSError("Host not in allowlist")
            return long_candles()
        rep = scan(["BAD/USDT", "BTC/USDT"], htf=None, fetcher=fetcher)
        self.assertEqual(len(rep.errors), 1)
        self.assertEqual(rep.errors[0].symbol, "BAD/USDT")
        self.assertEqual(len(rep.valid_setups), 1)

    def test_htf_fetched_when_set(self):
        calls = []
        def fetcher(symbol, tf, limit):
            calls.append(tf)
            return long_candles()
        scan(["BTC/USDT"], entry_tf="1h", htf="4h", fetcher=fetcher)
        self.assertIn("1h", calls)
        self.assertIn("4h", calls)


if __name__ == "__main__":
    unittest.main()
