from __future__ import annotations

from inventory.catalog import description, pack_size

CATALOG = {"A": {"pack_size": 4, "description": "widget"}}


def test_pack_size_comes_from_the_catalogue():
    assert pack_size(CATALOG, "A") == 4


def test_an_unknown_sku_falls_back_to_the_default():
    assert pack_size(CATALOG, "ZZZ", default=6) == 6


def test_description_falls_back_to_the_sku():
    assert description(CATALOG, "ZZZ") == "ZZZ"
