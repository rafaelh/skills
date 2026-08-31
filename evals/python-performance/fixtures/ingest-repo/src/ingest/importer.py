"""Join the night's transaction rows against the customer export."""

from __future__ import annotations

from collections import defaultdict

from ingest.textutil import normalize_name


def import_rows(rows, customers):
    """One ledger entry per row whose customer appears in the export."""
    imported = []
    for row in rows:
        customer = find_customer(customers, row["customer_ref"])
        if customer is None:
            continue
        imported.append(
            {
                "ref": row["customer_ref"],
                "name": normalize_name(customer["name"]),
                "region": customer["region"],
                "amount": row["amount"],
            }
        )
    return imported


def find_customer(customers, ref):
    """The surviving record for `ref`, or None if the export does not carry it.

    First match wins. The export still carries the superseded rows for customers
    who were merged, and the earliest one is the record billing reconciles
    against — the later duplicates are the accounts that were folded into it.
    """
    for customer in customers:
        if customer["ref"] == ref:
            return customer
    return None


def region_totals(imported):
    """Total amount per region, for the summary line at the end of the run."""
    totals = defaultdict(int)
    for entry in imported:
        totals[entry["region"]] += entry["amount"]
    return dict(totals)
