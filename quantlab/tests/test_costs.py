from quantlab.config import CostConfig
from quantlab.backtest import costs


def test_slippage_adverse_direction():
    c = CostConfig(slippage_bps=10.0)
    buy = costs.fill_price(100.0, +1, c.slippage_bps)
    sell = costs.fill_price(100.0, -1, c.slippage_bps)
    assert buy > 100.0 > sell  # buys fill higher, sells lower


def test_fee_positive_and_proportional():
    c = CostConfig(taker_fee=0.0004)
    assert costs.fee(10_000, c) == 4.0
    assert costs.fee(-10_000, c) == 4.0  # magnitude only


def test_funding_disabled_is_zero():
    c = CostConfig(funding_enabled=False)
    assert costs.funding_payment(50_000, c) == 0.0


def test_funding_longs_pay_when_positive():
    c = CostConfig(funding_enabled=True, flat_funding_rate=0.0001)
    long_pay = costs.funding_payment(+50_000, c)   # long notional -> pays
    short_pay = costs.funding_payment(-50_000, c)  # short notional -> receives
    assert long_pay > 0 and short_pay < 0
    assert long_pay == -short_pay
