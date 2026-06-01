import json
import unittest

import helpers  # noqa: F401
from pa.market import (collect, DataReading, Metric,
                       fetch_funding, fetch_long_short)


def fake_http(mapping):
    """url substring -> gövde sözlüğünden HttpGet üretir; eşleşmezse hata."""
    def get(url: str) -> str:
        for key, body in mapping.items():
            if key in url:
                return body
        raise OSError(f"engellendi: {url}")
    return get


FUNDING_POS = json.dumps({"lastFundingRate": "0.0005"})   # +0.05%
FUNDING_NEG = json.dumps({"lastFundingRate": "-0.0003"})
OI_BODY = json.dumps({"openInterest": "12345.67"})
LS_LONG = json.dumps([{"longShortRatio": "1.8"}])
LS_SHORT = json.dumps([{"longShortRatio": "0.6"}])


class TestMarket(unittest.TestCase):
    def test_all_available(self):
        get = fake_http({"premiumIndex": FUNDING_POS,
                         "openInterest": OI_BODY,
                         "globalLongShort": LS_LONG})
        r = collect("BTC/USDT", http_get=get)
        self.assertTrue(r.any_available)
        self.assertTrue(all(m.available for m in r.metrics))

    def test_partial_failure_isolated(self):
        # funding çalışır, OI ve LS engellenir → biri available, ikisi değil
        get = fake_http({"premiumIndex": FUNDING_POS})
        r = collect("BTC/USDT", http_get=get)
        by = {m.name: m for m in r.metrics}
        self.assertTrue(by["Funding Rate"].available)
        self.assertFalse(by["Open Interest"].available)
        self.assertFalse(by["Long/Short Ratio"].available)
        self.assertIn("alınamadı", by["Open Interest"].line())

    def test_all_blocked_marks_unavailable(self):
        # ağ tamamen engelli (bu ortamdaki 403 durumu): hiçbir şey uydurma
        get = fake_http({})
        r = collect("BTC/USDT", http_get=get)
        self.assertFalse(r.any_available)
        self.assertIsNone(r.crowded_side())

    def test_crowded_long(self):
        get = fake_http({"premiumIndex": FUNDING_POS, "globalLongShort": LS_LONG})
        r = collect("BTC/USDT", http_get=get)
        self.assertEqual(r.crowded_side(), "LONG")

    def test_crowded_short(self):
        get = fake_http({"premiumIndex": FUNDING_NEG, "globalLongShort": LS_SHORT})
        r = collect("BTC/USDT", http_get=get)
        self.assertEqual(r.crowded_side(), "SHORT")

    def test_crowded_mixed_is_none(self):
        # funding + (long), ls < 1 (short) → karışık → None
        get = fake_http({"premiumIndex": FUNDING_POS, "globalLongShort": LS_SHORT})
        r = collect("BTC/USDT", http_get=get)
        self.assertIsNone(r.crowded_side())

    def test_funding_parsed_as_percent(self):
        m = fetch_funding("BTC/USDT", fake_http({"premiumIndex": FUNDING_POS}))
        self.assertTrue(m.available)
        self.assertAlmostEqual(m.value, 0.05)  # 0.0005 -> %0.05

    def test_long_short_empty_raises(self):
        with self.assertRaises(ValueError):
            fetch_long_short("BTC/USDT", fake_http({"globalLongShort": "[]"}))


if __name__ == "__main__":
    unittest.main()
