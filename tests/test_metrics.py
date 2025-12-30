from decimal import Decimal

import pytest

from core.metrics import metric


@pytest.mark.parametrize(
    ("dimension", "unit", "value", "expected"),
    [
        ("length", "cm", Decimal("12.3"), 123),
        ("area", "m2", Decimal("1.5"), 1_500_000),
        ("volume", "l", Decimal("0.5"), 500_000),
        ("volume", "ml", Decimal("250"), 250_000),
        ("weight", "g", Decimal("2.5"), 2_500),
        ("weight", "kg", Decimal("0.001"), 1_000),
        ("count", "ea", Decimal("7"), 7_000),
    ],
)
def test_to_base_qty_round_trip(dimension, unit, value, expected):
    assert metric.to_base_qty(value, dimension=dimension, unit=unit) == expected


def test_to_base_qty_half_up_rounding():
    assert metric.to_base_qty(Decimal("1.5"), dimension="length", unit="cm") == 15
    assert metric.to_base_qty(Decimal("-1.5"), dimension="length", unit="cm") == -15


def test_from_base_qty_formatting():
    assert metric.from_base_qty(123, dimension="length", unit="cm") == Decimal("12.30")
    assert metric.from_base_qty(250_000, dimension="volume", unit="ml") == Decimal("250.00")


def test_price_conversions():
    assert metric.to_base(Decimal("10.00"), dimension="volume", unit="l") == Decimal("0.00")
    assert metric.from_base(Decimal("0.01"), dimension="weight", unit="g") == Decimal("10.00")


@pytest.mark.parametrize(
    ("func", "kwargs", "message"),
    [
        (
            metric.to_base_qty,
            {"value": 1, "dimension": "volume", "unit": "g"},
            "Unsupported uom 'g' for dimension 'volume'",
        ),
        (
            metric.from_base_qty,
            {"qty_base": 1, "dimension": "weight", "unit": "ml"},
            "Unsupported uom 'ml' for dimension 'weight'",
        ),
    ],
)
def test_invalid_pairs_raise(func, kwargs, message):
    with pytest.raises(ValueError, match=message):
        func(**kwargs)
