from __future__ import annotations

from decimal import Decimal

from ledger.reconcile import reconcile, summary


def row(ref, account, amount, day):
    return {"ref": ref, "account": account, "amount": Decimal(amount), "day": day}


def test_an_exact_match_is_matched():
    result = reconcile([row("S1", "cash", "10.00", 5)], [row("E1", "cash", "10.00", 5)])
    assert len(result["matched"]) == 1
    assert result["matched"][0]["entry"]["ref"] == "E1"
    assert result["unmatched_statement"] == []
    assert result["unmatched_entries"] == []


def test_amounts_inside_the_tolerance_still_match():
    result = reconcile([row("S1", "cash", "10.01", 5)], [row("E1", "cash", "10.00", 5)])
    assert len(result["matched"]) == 1


def test_amounts_outside_the_tolerance_do_not_match():
    result = reconcile([row("S1", "cash", "10.05", 5)], [row("E1", "cash", "10.00", 5)])
    assert result["matched"] == []
    assert len(result["unmatched_statement"]) == 1
    assert len(result["unmatched_entries"]) == 1


def test_a_different_account_never_matches():
    result = reconcile([row("S1", "cash", "10.00", 5)], [row("E1", "bank", "10.00", 5)])
    assert result["matched"] == []


def test_the_date_window_is_inclusive():
    result = reconcile([row("S1", "cash", "10.00", 8)], [row("E1", "cash", "10.00", 5)])
    assert len(result["matched"]) == 1


def test_beyond_the_date_window_does_not_match():
    result = reconcile([row("S1", "cash", "10.00", 9)], [row("E1", "cash", "10.00", 5)])
    assert result["matched"] == []


def test_the_window_works_in_both_directions():
    result = reconcile([row("S1", "cash", "10.00", 2)], [row("E1", "cash", "10.00", 5)])
    assert len(result["matched"]) == 1


def test_the_closest_date_wins():
    entries = [row("FAR", "cash", "10.00", 2), row("NEAR", "cash", "10.00", 4)]
    result = reconcile([row("S1", "cash", "10.00", 5)], entries)
    assert result["matched"][0]["entry"]["ref"] == "NEAR"


def test_a_tie_on_distance_goes_to_the_earlier_entry():
    entries = [row("FIRST", "cash", "10.00", 4), row("SECOND", "cash", "10.00", 6)]
    result = reconcile([row("S1", "cash", "10.00", 5)], entries)
    assert result["matched"][0]["entry"]["ref"] == "FIRST"


def test_an_entry_is_only_consumed_once():
    statement = [row("S1", "cash", "10.00", 5), row("S2", "cash", "10.00", 5)]
    result = reconcile(statement, [row("E1", "cash", "10.00", 5)])
    assert len(result["matched"]) == 1
    assert len(result["unmatched_statement"]) == 1


def test_an_unmatched_row_is_logged(caplog):
    import logging

    with caplog.at_level(logging.INFO):
        reconcile([row("S9", "cash", "10.00", 5)], [])
    assert "S9" in caplog.text


def test_a_custom_window_widens_the_search():
    result = reconcile([row("S1", "cash", "10.00", 20)], [row("E1", "cash", "10.00", 5)], window=30)
    assert len(result["matched"]) == 1


def test_empty_inputs_reconcile_to_nothing():
    assert reconcile([], []) == {
        "matched": [],
        "unmatched_statement": [],
        "unmatched_entries": [],
    }


def test_summary_counts_and_totals_the_drift():
    statement = [row("S1", "cash", "10.01", 5), row("S2", "cash", "20.00", 5)]
    entries = [row("E1", "cash", "10.00", 5), row("E2", "cash", "20.00", 5)]
    result = reconcile(statement, entries)
    assert summary(result) == {"matched": 2, "drift": Decimal("0.01"), "open": 0}


def test_summary_counts_open_rows():
    result = reconcile([row("S1", "cash", "10.00", 5)], [])
    assert summary(result)["open"] == 1
