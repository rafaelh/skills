"""SKU catalogue lookups."""

from __future__ import annotations


def pack_size(catalog, sku, default=1):
    """The pack size for `sku`, or `default` when the catalogue has no entry."""
    entry = catalog.get(sku)
    if entry is None:
        return default
    return entry.get("pack_size", default)


def description(catalog, sku):
    """The catalogue description for `sku`, or the SKU itself when it is unknown."""
    entry = catalog.get(sku)
    if entry is None:
        return sku
    return entry.get("description", sku)
