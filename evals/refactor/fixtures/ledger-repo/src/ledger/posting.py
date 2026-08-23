"""Double-entry posting. Stable since 2021; the reconciliation work does not touch it."""

from __future__ import annotations

from decimal import Decimal


def post(book, entries):
    b = dict(book)
    for e in entries:
        if e.get("account"):
            if e.get("amount") is not None:
                a = e["account"]
                if a in b:
                    if e.get("side") == "credit":
                        b[a] = b[a] - e["amount"]
                    else:
                        b[a] = b[a] + e["amount"]
                else:
                    if e.get("side") == "credit":
                        b[a] = Decimal("0.00") - e["amount"]
                    else:
                        b[a] = e["amount"]
    return b


def trial_balance(book):
    dr = Decimal("0.00")
    cr = Decimal("0.00")
    for k in sorted(book):
        v = book[k]
        if v >= Decimal("0.00"):
            dr = dr + v
        else:
            cr = cr - v
    return {"debit": dr, "credit": cr, "balanced": dr == cr}
