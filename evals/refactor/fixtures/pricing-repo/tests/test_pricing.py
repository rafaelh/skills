from __future__ import annotations

from decimal import Decimal
import logging

from storefront.pricing import line_totals, quote


def line(sku, unit, qty, category="furniture"):
    return {"sku": sku, "unit": Decimal(unit), "qty": qty, "category": category}


def test_empty_basket_is_all_zeros():
    q = quote([], "gold", "GB")
    assert q["subtotal"] == Decimal("0.00")
    assert q["net"] == Decimal("0.00")
    assert q["tax"] == Decimal("0.00")
    assert q["freight"] == Decimal("0.00")
    assert q["total"] == Decimal("0.00")


def test_none_basket_is_all_zeros():
    assert quote(None, "gold", "GB")["total"] == Decimal("0.00")


def test_subtotal_multiplies_each_line_out():
    q = quote([line("A", "10.00", 3), line("B", "2.50", 2)], "standard", "US")
    assert q["subtotal"] == Decimal("35.00")


def test_tier_discount_applies_to_subtotal():
    q = quote([line("A", "100.00", 1)], "gold", "US")
    assert q["tier_discount"] == Decimal("10.00")
    assert q["net"] == Decimal("90.00")


def test_unknown_tier_falls_back_to_standard_and_warns(caplog):
    with caplog.at_level(logging.WARNING):
        q = quote([line("A", "100.00", 1)], "diamond", "US")
    assert q["tier_discount"] == Decimal("0.00")
    assert "unknown tier" in caplog.text
    assert "diamond" in caplog.text


def test_non_positive_quantity_is_skipped_and_warned(caplog):
    with caplog.at_level(logging.WARNING):
        q = quote([line("A", "10.00", 2), line("B", "99.00", 0)], "standard", "US")
    assert q["subtotal"] == Decimal("20.00")
    assert "B" in caplog.text


def test_line_without_unit_price_is_skipped_and_warned(caplog):
    with caplog.at_level(logging.WARNING):
        q = quote([line("A", "10.00", 2), {"sku": "B", "qty": 1}], "standard", "US")
    assert q["subtotal"] == Decimal("20.00")
    assert "no unit price" in caplog.text


def test_line_missing_qty_entirely_is_skipped():
    q = quote([line("A", "10.00", 2), {"sku": "B", "unit": Decimal("99.00")}], "standard", "US")
    assert q["subtotal"] == Decimal("20.00")


def test_percent_coupon_applies_to_whole_basket():
    coupons = [{"code": "TEN", "kind": "percent", "value": Decimal("0.10"), "category": None}]
    q = quote([line("A", "100.00", 1)], "standard", "US", coupons)
    assert q["coupon_discount"] == Decimal("10.00")
    assert q["coupon_code"] == "TEN"


def test_category_coupon_only_sees_its_own_category():
    coupons = [{"code": "LIGHT", "kind": "percent", "value": Decimal("0.50"), "category": "lighting"}]
    items = [line("A", "100.00", 1, "furniture"), line("B", "20.00", 1, "lighting")]
    q = quote(items, "standard", "US", coupons)
    assert q["coupon_discount"] == Decimal("10.00")


def test_category_coupon_for_absent_category_is_worth_nothing():
    coupons = [{"code": "LIGHT", "kind": "percent", "value": Decimal("0.50"), "category": "lighting"}]
    q = quote([line("A", "100.00", 1, "furniture")], "standard", "US", coupons)
    assert q["coupon_discount"] == Decimal("0.00")
    assert q["coupon_code"] is None


def test_flat_coupon_is_capped_at_the_basket_value():
    coupons = [{"code": "BIG", "kind": "flat", "value": Decimal("500.00"), "category": None}]
    q = quote([line("A", "30.00", 1)], "standard", "US", coupons)
    assert q["coupon_discount"] == Decimal("30.00")
    assert q["net"] == Decimal("0.00")


def test_best_coupon_wins():
    coupons = [
        {"code": "SMALL", "kind": "flat", "value": Decimal("5.00"), "category": None},
        {"code": "LARGE", "kind": "flat", "value": Decimal("25.00"), "category": None},
    ]
    q = quote([line("A", "100.00", 1)], "standard", "US", coupons)
    assert q["coupon_code"] == "LARGE"


def test_a_tie_goes_to_the_earlier_coupon():
    coupons = [
        {"code": "FIRST", "kind": "flat", "value": Decimal("10.00"), "category": None},
        {"code": "SECOND", "kind": "percent", "value": Decimal("0.10"), "category": None},
    ]
    q = quote([line("A", "100.00", 1)], "standard", "US", coupons)
    assert q["coupon_discount"] == Decimal("10.00")
    assert q["coupon_code"] == "FIRST"


def test_zero_value_coupon_never_becomes_the_chosen_code():
    coupons = [{"code": "NOTHING", "kind": "flat", "value": Decimal("0.00"), "category": None}]
    q = quote([line("A", "100.00", 1)], "standard", "US", coupons)
    assert q["coupon_code"] is None


def test_net_never_goes_below_zero():
    coupons = [{"code": "BIG", "kind": "flat", "value": Decimal("999.00"), "category": None}]
    q = quote([line("A", "10.00", 1)], "platinum", "GB", coupons)
    assert q["net"] == Decimal("0.00")
    assert q["tax"] == Decimal("0.00")
    assert q["total"] == Decimal("0.00")


def test_tax_uses_the_country_rate():
    q = quote([line("A", "100.00", 1)], "standard", "DE")
    assert q["tax"] == Decimal("19.00")


def test_unknown_country_is_taxed_at_the_gb_rate():
    q = quote([line("A", "100.00", 1)], "standard", "ZZ")
    assert q["tax"] == Decimal("20.00")


def test_freight_is_charged_below_the_threshold():
    q = quote([line("A", "20.00", 1)], "standard", "US")
    assert q["freight"] == Decimal("4.95")
    assert q["total"] == Decimal("24.95")


def test_freight_is_free_at_the_threshold_exactly():
    q = quote([line("A", "50.00", 1)], "standard", "US")
    assert q["freight"] == Decimal("0.00")


def test_freight_is_not_charged_on_an_empty_net():
    coupons = [{"code": "BIG", "kind": "flat", "value": Decimal("999.00"), "category": None}]
    q = quote([line("A", "10.00", 1)], "standard", "US", coupons)
    assert q["freight"] == Decimal("0.00")


def test_rounding_is_half_up_at_the_cent():
    q = quote([line("A", "0.125", 1)], "standard", "US")
    assert q["subtotal"] == Decimal("0.13")


def test_line_totals_groups_by_category():
    items = [
        line("A", "10.00", 2, "furniture"),
        line("B", "5.00", 1, "lighting"),
        line("C", "1.00", 3, "furniture"),
    ]
    assert line_totals(items) == {
        "furniture": Decimal("23.00"),
        "lighting": Decimal("5.00"),
    }


def test_line_totals_ignores_uncategorised_lines():
    items = [line("A", "10.00", 1, "furniture"), {"sku": "B", "unit": Decimal("9.00"), "qty": 1}]
    assert line_totals(items) == {"furniture": Decimal("10.00")}


def test_line_totals_of_an_empty_basket_is_empty():
    assert line_totals([]) == {}
