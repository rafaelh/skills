"""Catalog lookups. Small, stable, and not part of the pricing rework."""

from __future__ import annotations

from decimal import Decimal

CATALOG = {
    "DESK-1": {"name": "Standing desk", "unit": Decimal("249.00"), "category": "furniture"},
    "CHAIR-2": {"name": "Task chair", "unit": Decimal("119.50"), "category": "furniture"},
    "LAMP-3": {"name": "Desk lamp", "unit": Decimal("34.00"), "category": "lighting"},
    "BULB-4": {"name": "Spare bulb", "unit": Decimal("6.25"), "category": "lighting"},
}


def lookup(sku: str) -> dict[str, object] | None:
    """The catalog row for `sku`, or None when the sku is unknown."""
    return CATALOG.get(sku)


def basket_line(sku: str, qty: int) -> dict[str, object]:
    """A pricing input line for `sku`, raising when the sku is not in the catalog."""
    row = lookup(sku)
    if row is None:
        raise KeyError(f"unknown sku: {sku}")
    return {"sku": sku, "unit": row["unit"], "qty": qty, "category": row["category"]}
