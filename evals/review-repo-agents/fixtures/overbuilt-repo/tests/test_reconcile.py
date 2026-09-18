from datetime import date
from decimal import Decimal

from ledgerline.ledger import Invoice
from ledgerline.reconcile import match


def invoice(number: str, amount: str) -> Invoice:
    return Invoice(number, date(2026, 1, 1), Decimal(amount), "Acme")


def test_amount_match_wins_over_reference():
    invoices = [invoice("INV-1", "100.00"), invoice("INV-2", "250.00")]
    assert match(invoices, Decimal("250.00"), "INV-1").number == "INV-2"


def test_reference_fallback():
    invoices = [invoice("INV-1", "100.00")]
    assert match(invoices, Decimal("99.00"), "payment for inv-1").number == "INV-1"


def test_no_match():
    assert match([invoice("INV-1", "100.00")], Decimal("5.00"), "cash") is None
