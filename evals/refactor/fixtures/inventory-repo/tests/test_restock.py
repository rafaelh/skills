from __future__ import annotations

from decimal import Decimal

from inventory.restock import plan, top_up


def item(sku, on_hand, reorder_point, pack_size=1, unit_cost="10.00"):
    return {
        "sku": sku,
        "on_hand": on_hand,
        "reorder_point": reorder_point,
        "pack_size": pack_size,
        "unit_cost": Decimal(unit_cost),
    }


def order(sku, qty, status="open"):
    return {"sku": sku, "qty": qty, "status": status}


def test_stock_above_the_reorder_point_is_left_alone():
    assert plan([item("A", 10, 5)], []) == []


def test_stock_below_the_reorder_point_is_ordered():
    result = plan([item("A", 1, 5)], [])
    assert result == [{"sku": "A", "qty": 4, "cost": Decimal("40.00")}]


def test_open_orders_count_towards_the_shortfall():
    assert plan([item("A", 1, 5)], [order("A", 4)]) == []


def test_cancelled_orders_do_not_count():
    result = plan([item("A", 1, 5)], [order("A", 4, status="cancelled")])
    assert result[0]["qty"] == 4


def test_quantities_round_up_to_a_whole_pack():
    result = plan([item("A", 0, 5, pack_size=4)], [])
    assert result[0]["qty"] == 8


def test_a_shortfall_smaller_than_a_pack_orders_one_pack():
    result = plan([item("A", 0, 2, pack_size=6)], [])
    assert result[0]["qty"] == 6


def test_orders_below_the_minimum_value_are_dropped():
    assert plan([item("A", 4, 5, unit_cost="1.00")], []) == []


def test_the_budget_stops_further_orders():
    items = [item("A", 0, 5), item("B", 0, 5)]
    result = plan(items, [], budget=Decimal("50.00"))
    assert [row["sku"] for row in result] == ["A"]


def test_a_line_over_budget_does_not_block_a_later_cheaper_one():
    items = [item("A", 0, 10), item("B", 0, 3)]
    result = plan(items, [], budget=Decimal("50.00"))
    assert [row["sku"] for row in result] == ["B"]


def test_an_empty_plan_costs_nothing():
    assert plan([], []) == []


def test_top_up_returns_zero_when_already_at_target():
    assert top_up(item("A", 10, 5), 10) == 0


def test_top_up_rounds_to_whole_packs():
    assert top_up(item("A", 1, 5, pack_size=4), 6) == 8


def test_top_up_orders_a_full_pack_for_a_small_gap():
    assert top_up(item("A", 5, 5, pack_size=4), 6) == 4
