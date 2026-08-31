from __future__ import annotations

from ingest.importer import find_customer, import_rows, region_totals

CUSTOMERS = [
    {"ref": "C1", "name": "north  harbour ltd", "region": "emea"},
    {"ref": "C2", "name": "granite quill", "region": "amer"},
]


def test_a_row_becomes_a_ledger_entry():
    entries = import_rows([{"customer_ref": "C1", "amount": 250}], CUSTOMERS)
    assert entries == [{"ref": "C1", "name": "North Harbour", "region": "emea", "amount": 250}]


def test_a_row_with_no_matching_customer_is_skipped():
    assert import_rows([{"customer_ref": "C9", "amount": 250}], CUSTOMERS) == []


def test_find_customer_returns_the_record():
    assert find_customer(CUSTOMERS, "C2")["region"] == "amer"


def test_region_totals_sums_per_region():
    entries = import_rows(
        [{"customer_ref": "C1", "amount": 250}, {"customer_ref": "C2", "amount": 100}],
        CUSTOMERS,
    )
    assert region_totals(entries) == {"emea": 250, "amer": 100}
