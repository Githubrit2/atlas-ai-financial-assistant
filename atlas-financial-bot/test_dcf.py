import pytest
from dcf import dcf_value


def test_known_value():
    # 100 FCF, 0% growth, 10% discount, 0% terminal growth, 1 year:
    # 100/1.1 + (100*1/0.10)/1.1 = 90.909 + 909.09 = 1000
    assert dcf_value(100, 0, 0.10, 0.0, years=1) == pytest.approx(1000, rel=1e-6)


def test_per_share_division():
    total = dcf_value(100, 0.05, shares=1)
    assert dcf_value(100, 0.05, shares=10) == pytest.approx(total / 10)


def test_higher_growth_gives_higher_value():
    assert dcf_value(100, 0.10) > dcf_value(100, 0.02)


def test_higher_discount_rate_gives_lower_value():
    assert dcf_value(100, 0.05, discount_rate=0.12) < dcf_value(100, 0.05, discount_rate=0.08)


def test_discount_must_exceed_terminal_growth():
    with pytest.raises(ValueError):
        dcf_value(100, 0.05, discount_rate=0.03, terminal_growth=0.03)


def test_rejects_non_positive_fcf():
    with pytest.raises(ValueError):
        dcf_value(-50, 0.05)


def test_rejects_non_positive_shares():
    with pytest.raises(ValueError):
        dcf_value(100, 0.05, shares=0)