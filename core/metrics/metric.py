from decimal import Decimal, ROUND_HALF_UP
from typing import Set

DIMENSIONS = {"length", "area", "volume", "weight", "count"}

UNIT_MULTIPLIER = {
    "length": {"mm": 1, "cm": 10, "m": 1000},
    "area": {"mm2": 1, "cm2": 100, "m2": 1_000_000},
    "volume": {"mm3": 1, "cm3": 1_000, "ml": 1_000, "l": 1_000_000, "m3": 1_000_000_000},
    "weight": {"mg": 1, "g": 1_000, "kg": 1_000_000},
    "count": {"mc": 1, "ea": 1_000},
}

BASE_UNIT_LABEL = {
    "length": "mm",
    "area": "mm2",
    "volume": "mm3",
    "weight": "mg",
    "count": "mc",
}

DEFAULT_UNIT_FOR = BASE_UNIT_LABEL


def _norm_unit(u: str) -> str:
    """
    Normalize a unit token for lookup:
    - strip, lowercase
    - replace '²' -> '2', '³' -> '3'
    - map 'L' -> 'l'
    - aliases: 'piece' -> 'ea'
    """

    normalized = (u or "").strip().lower().replace("²", "2").replace("³", "3")
    if normalized == "piece":
        return "ea"
    return normalized


def allowed_units_for(dimension: str) -> Set[str]:
    """
    Return the set of allowed unit strings for the given dimension (lowercased).
    If the dimension is unknown, return an empty set.
    """

    dim = (dimension or "").lower()
    units = UNIT_MULTIPLIER.get(dim)
    if units is None:
        return set()
    return set(units.keys())


def uom_multiplier(dimension: str, unit: str) -> int:
    """
    Return integer multiplier from the given unit to the base unit of the dimension.
    Return 0 if the (dimension, unit) pair is invalid.
    """

    dim = (dimension or "").lower()
    units = UNIT_MULTIPLIER.get(dim, {})
    mult = units.get(_norm_unit(unit))
    return mult if mult is not None else 0


def default_unit_for(dimension: str) -> str:
    """
    Return the base unit label for the dimension (e.g., 'mm' for length).
    Assumes caller passes a known dimension; KeyError is allowed if not.
    """

    return BASE_UNIT_LABEL[dimension]


def to_base_qty(value: int | float | Decimal, *, dimension: str, unit: str) -> int:
    """
    Convert a quantity expressed in 'unit' to an integer quantity in base units for 'dimension'.
    - Use Decimal(str(value)) * multiplier
    - Round HALF_UP to the nearest integer
    - On invalid unit: raise ValueError("Unsupported uom '{u}' for dimension '{d}'")
    """

    u = _norm_unit(unit)
    d = (dimension or "").lower()
    mult = uom_multiplier(d, u)
    if mult == 0:
        raise ValueError(f"Unsupported uom '{u}' for dimension '{d}'")
    qty = Decimal(str(value)) * Decimal(mult)
    return int(qty.to_integral_value(rounding=ROUND_HALF_UP))


def from_base_qty(qty_base: int, *, dimension: str, unit: str) -> Decimal:
    """
    Convert an integer base quantity to a Decimal in the requested 'unit'.
    - Divide by multiplier
    - Quantize to Decimal('0.01') using default rounding
    - On invalid unit: raise ValueError("Unsupported uom '{u}' for dimension '{d}'")
    """

    u = _norm_unit(unit)
    d = (dimension or "").lower()
    mult = uom_multiplier(d, u)
    if mult == 0:
        raise ValueError(f"Unsupported uom '{u}' for dimension '{d}'")
    return (Decimal(qty_base) / Decimal(mult)).quantize(Decimal("0.01"))


def to_base(price_per_unit: Decimal, *, dimension: str, unit: str) -> Decimal:
    """
    Convert a price per 'unit' to price per *base unit*.
    - Divide by multiplier
    - Quantize to Decimal('0.01')
    - On invalid unit: raise ValueError("Unsupported uom '{u}' for dimension '{d}'")
    """

    u = _norm_unit(unit)
    d = (dimension or "").lower()
    mult = uom_multiplier(d, u)
    if mult == 0:
        raise ValueError(f"Unsupported uom '{u}' for dimension '{d}'")
    return (price_per_unit / Decimal(mult)).quantize(Decimal("0.01"))


def from_base(price_per_base: Decimal, *, dimension: str, unit: str) -> Decimal:
    """
    Convert a price per base unit to price per requested 'unit'.
    - Multiply by multiplier
    - Quantize to Decimal('0.01')
    - On invalid unit: raise ValueError("Unsupported uom '{u}' for dimension '{d}'")
    """

    u = _norm_unit(unit)
    d = (dimension or "").lower()
    mult = uom_multiplier(d, u)
    if mult == 0:
        raise ValueError(f"Unsupported uom '{u}' for dimension '{d}'")
    return (price_per_base * Decimal(mult)).quantize(Decimal("0.01"))


__all__ = [
    "DIMENSIONS",
    "UNIT_MULTIPLIER",
    "BASE_UNIT_LABEL",
    "DEFAULT_UNIT_FOR",
    "_norm_unit",
    "allowed_units_for",
    "uom_multiplier",
    "default_unit_for",
    "to_base_qty",
    "from_base_qty",
    "to_base",
    "from_base",
]
