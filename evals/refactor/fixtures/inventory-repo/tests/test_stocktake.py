from __future__ import annotations

from decimal import Decimal

from inventory.stocktake import shrinkage, variance_report


def test_a_matching_count_reports_no_variance():
    assert variance_report({"MAIN": {"A": 5}}, {"MAIN": {"A": 5}}) == []


def test_a_short_count_reports_a_negative_delta():
    report = variance_report({"MAIN": {"A": 3}}, {"MAIN": {"A": 5}})
    assert report[0]["delta"] == -2


def test_an_unknown_location_counts_the_whole_quantity():
    report = variance_report({"SPARE": {"A": 3}}, {})
    assert report[0]["delta"] == 3


def test_a_threshold_suppresses_a_small_variance():
    report = variance_report({"MAIN": {"A": 4}}, {"MAIN": {"A": 5}}, thresholds={"A": 3})
    assert report == []


def test_a_threshold_lets_a_large_variance_through():
    report = variance_report({"MAIN": {"A": 1}}, {"MAIN": {"A": 5}}, thresholds={"A": 3})
    assert report[0]["delta"] == -4


def test_the_value_map_prices_the_variance():
    report = variance_report(
        {"MAIN": {"A": 3}}, {"MAIN": {"A": 5}}, value_map={"A": Decimal("2.50")}
    )
    assert report[0]["value"] == Decimal("-5.00")


def test_shrinkage_totals_the_negative_lines():
    report = variance_report(
        {"MAIN": {"A": 3, "B": 7}},
        {"MAIN": {"A": 5, "B": 5}},
        value_map={"A": Decimal("2.50"), "B": Decimal("1.00")},
    )
    assert shrinkage(report) == Decimal("-5.00")
