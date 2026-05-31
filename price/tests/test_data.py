import json
import os
import tempfile
import unittest

import helpers  # noqa: F401
from pa.data import from_records, load_csv, fetch_binance


class TestData(unittest.TestCase):
    def test_from_records(self):
        rows = [[1000, 10, 12, 9, 11, 100], [2000, 11, 13, 10, 12, 120]]
        candles = from_records(rows)
        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[-1].close, 12)

    def test_from_records_empty_raises(self):
        with self.assertRaises(ValueError):
            from_records([])

    def test_load_csv_roundtrip(self):
        content = ("timestamp,open,high,low,close,volume\n"
                   "1000,10,12,9,11,100\n"
                   "2000,11,13,10,12,120\n")
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            candles = load_csv(path)
            self.assertEqual(len(candles), 2)
            self.assertEqual(candles[0].high, 12)
        finally:
            os.unlink(path)

    def test_load_csv_missing_column(self):
        content = "timestamp,open,high,low\n1000,10,12,9\n"  # close yok
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            with self.assertRaises(ValueError):
                load_csv(path)
        finally:
            os.unlink(path)

    def test_fetch_binance_parses_klines(self):
        # Binance klines formatı; http_get enjekte edilir (ağ yok)
        klines = [
            [1000, "10", "12", "9", "11", "100", 1999, "0", 5, "0", "0", "0"],
            [2000, "11", "13", "10", "12", "120", 2999, "0", 6, "0", "0", "0"],
        ]
        body = json.dumps(klines)
        candles = fetch_binance("BTC/USDT", "1h", 2, http_get=lambda u: body)
        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[0].high, 12)
        self.assertEqual(candles[-1].close, 12)
        self.assertEqual(candles[-1].volume, 120)

    def test_fetch_binance_bad_interval(self):
        with self.assertRaises(ValueError):
            fetch_binance("BTC/USDT", "7m", 2, http_get=lambda u: "[]")


if __name__ == "__main__":
    unittest.main()
