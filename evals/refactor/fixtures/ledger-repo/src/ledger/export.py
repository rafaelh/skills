"""CSV export for the finance team. Frozen: their macros parse the exact column order."""

from __future__ import annotations

COLS = ["account", "debit", "credit"]


def to_csv(book):
    o = ""
    o = o + ",".join(COLS) + "\n"
    for k in sorted(book):
        v = book[k]
        if v >= 0:
            d = str(v)
            c = ""
        else:
            d = ""
            c = str(-v)
        r = []
        r.append(k)
        r.append(d)
        r.append(c)
        o = o + ",".join(r) + "\n"
    return o
