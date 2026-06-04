from quantlab.config import RiskConfig
from quantlab.risk.sizing import fixed_fractional_units


def test_risk_scales_with_stop_distance():
    cfg = RiskConfig(bankroll=10_000, risk_per_trade=0.01, max_leverage=100)
    wide = fixed_fractional_units(10_000, 100.0, 10.0, cfg)
    tight = fixed_fractional_units(10_000, 100.0, 5.0, cfg)
    # Half the stop distance => double the units (same dollar risk).
    assert abs(tight - 2 * wide) < 1e-9


def test_dollar_risk_is_fixed_fraction():
    cfg = RiskConfig(bankroll=10_000, risk_per_trade=0.02, max_leverage=100)
    units = fixed_fractional_units(10_000, 100.0, 4.0, cfg)
    # Loss if stopped = units * stop_distance should equal 2% of equity.
    assert abs(units * 4.0 - 0.02 * 10_000) < 1e-9


def test_leverage_cap_binds():
    cfg = RiskConfig(bankroll=10_000, risk_per_trade=0.5, max_leverage=3)
    units = fixed_fractional_units(10_000, 100.0, 1.0, cfg)
    notional = units * 100.0
    assert notional <= 3 * 10_000 + 1e-6


def test_no_martingale_independent_of_history():
    # Sizing must depend ONLY on (equity, price, stop) — never on prior outcomes.
    cfg = RiskConfig(bankroll=10_000, risk_per_trade=0.01, max_leverage=100)
    a = fixed_fractional_units(8_000, 100.0, 5.0, cfg)
    b = fixed_fractional_units(8_000, 100.0, 5.0, cfg)
    assert a == b  # identical inputs -> identical size, no "recover the loss" bump


def test_degenerate_inputs_zero():
    cfg = RiskConfig()
    assert fixed_fractional_units(0, 100, 5, cfg) == 0.0
    assert fixed_fractional_units(10_000, 100, 0, cfg) == 0.0
