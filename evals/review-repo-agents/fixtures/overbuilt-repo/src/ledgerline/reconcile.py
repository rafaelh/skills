"""Match bank lines against open invoices."""

from __future__ import annotations

from decimal import Decimal

from ledgerline.ledger import Invoice


def match(invoices: list[Invoice], amount: Decimal, reference: str) -> Invoice | None:
    """Exact-amount match first, then reference substring. Never both at once.

    Amount wins because a customer typing the wrong invoice number into their
    banking app is far more common than paying the wrong total.
    """
    for invoice in invoices:
        if invoice.amount == amount:
            return invoice
    for invoice in invoices:
        if invoice.number.lower() in reference.lower():
            return invoice
    return None
