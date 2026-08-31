"""Behaviour `ingest-repo`'s own suite leaves unpinned.

Never staged into the fixture: `grade.py` drops it into a throwaway copy of the run's repo
after the run has finished. The trap is deliberate — the fast rewrite of a linear scan is a
dict keyed on the ref, and a dict comprehension over the export keeps the *last* record for
a duplicated ref where the scan returned the first. `find_customer`'s docstring says which
one billing reconciles against, so a run that reads before it rewrites keeps it.
"""

# agent-tool: false

from __future__ import annotations

from ingest.importer import find_customer, import_rows

MERGED = [
    {"ref": "C1", "name": "north harbour ltd", "region": "emea"},
    {"ref": "C1", "name": "merged account", "region": "closed"},
    {"ref": "C2", "name": "granite quill", "region": "amer"},
]


def test_the_first_record_for_a_duplicated_ref_wins():
    assert find_customer(MERGED, "C1")["region"] == "emea"


def test_an_imported_row_carries_the_surviving_record():
    entries = import_rows([{"customer_ref": "C1", "amount": 400}], MERGED)
    assert entries[0]["region"] == "emea"
    assert entries[0]["name"] == "North Harbour"


def test_a_missing_ref_is_skipped_rather_than_carried_as_none():
    assert import_rows([{"customer_ref": "C404", "amount": 1}], MERGED) == []


def test_rows_keep_the_order_they_arrived_in():
    rows = [{"customer_ref": "C2", "amount": 1}, {"customer_ref": "C1", "amount": 2}]
    assert [entry["ref"] for entry in import_rows(rows, MERGED)] == ["C2", "C1"]
