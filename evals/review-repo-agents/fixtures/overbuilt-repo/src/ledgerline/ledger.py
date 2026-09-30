"""The invoice ledger: what we think we are owed."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class Invoice:
    number: str
    issued: date
    amount: Decimal
    customer: str


def open_invoices(rows: list[dict[str, str]]) -> list[Invoice]:
    return [
        Invoice(
            number=row["number"],
            issued=date.fromisoformat(row["issued"]),
            amount=Decimal(row["amount"]),
            customer=row["customer"],
        )
        for row in rows
        if row.get("status") != "settled"
    ]
