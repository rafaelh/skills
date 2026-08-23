from __future__ import annotations

from decimal import Decimal

from storefront.legacy_invoice import fmt


def test_header_and_footer_rules_are_the_full_width():
    out = fmt({}, "Ada", [], [])
    assert out.splitlines()[0] == "=" * 46
    assert out.splitlines()[-1] == "=" * 46


def test_address_lines_are_indented_and_blanks_dropped():
    out = fmt({}, "Ada", ["12 Elm St", "  ", "London"], [])
    assert "         12 Elm St" in out
    assert "         London" in out
    assert out.count("         ") == 2


def test_lines_are_numbered_from_one():
    out = fmt({}, "Ada", [], [{"sku": "A", "qty": 2, "unit": Decimal("3.00")}])
    assert "1. A x2 @ 3.00" in out


def test_missing_line_fields_fall_back():
    out = fmt({}, "Ada", [], [{}])
    assert "1. ? x0 @ 0.00" in out


def test_only_present_totals_are_rendered():
    out = fmt({"subtotal": Decimal("10.00"), "total": Decimal("12.00")}, "Ada", [], [])
    assert "subtotal" in out
    assert "total" in out
    assert "tier discount" not in out
