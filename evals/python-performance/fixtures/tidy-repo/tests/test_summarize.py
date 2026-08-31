from __future__ import annotations

from checkout.summarize import count_items, label_for, promoted_skus, summarize


def line(sku="a", category="grocery", unit_price=250, quantity=1):
    return {"sku": sku, "category": category, "unit_price": unit_price, "quantity": quantity}


def order(lines=None, promotions=None):
    return {"lines": lines or [line()], "promotions": promotions or []}


def test_totals_are_summed_per_category():
    summary = summarize(order([line(quantity=2), line(sku="b", category="apparel")]))
    assert summary["totals"] == {"grocery": 500, "apparel": 250}


def test_categories_carry_their_display_labels():
    assert summarize(order())["categories"] == ["Food & drink"]


def test_an_unknown_category_falls_back_to_a_title_case_label():
    assert label_for("garden") == "Garden"


def test_item_count_sums_quantities():
    assert count_items([line(quantity=3), line(quantity=4)]) == 7


def test_promoted_skus_keeps_a_sku_promoted_twice():
    promotions = [{"skus": ["a", "b"]}, {"skus": ["a"]}]
    assert promoted_skus(order(promotions=promotions)) == ["a", "b", "a"]
