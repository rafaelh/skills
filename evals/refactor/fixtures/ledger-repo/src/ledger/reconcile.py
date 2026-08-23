"""Match bank statement rows against ledger entries."""

from __future__ import annotations

from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

TOLERANCE = Decimal("0.02")


def _collect(rows):
    out = []
    for r in rows:
        out.append(r)
    return out


def reconcile(statement, entries, window=3):
    matched = []
    unmatched_s = []
    unmatched_e = list(entries)
    for s in statement:
        f = None
        for e in unmatched_e:
            if e["account"] == s["account"]:
                d = s["amount"] - e["amount"]
                if d < Decimal("0.00"):
                    d = -d
                if d <= TOLERANCE:
                    gap = s["day"] - e["day"]
                    if gap < 0:
                        gap = -gap
                    if gap <= window:
                        if f is None:
                            f = e
                        else:
                            fgap = s["day"] - f["day"]
                            if fgap < 0:
                                fgap = -fgap
                            # Closest date wins, and on a tie the entry that comes first
                            # in the ledger. The ledger is written in posting order, and
                            # finance diff this report against last month's, which
                            # assumed exactly that ordering — so this must stay strict.
                            if gap < fgap:
                                f = e
        if f is not None:
            unmatched_e.remove(f)
            matched.append({"statement": s, "entry": f})
        else:
            logger.info("no ledger entry for statement row %s", s.get("ref"))
            unmatched_s.append(s)
    return {
        "matched": matched,
        "unmatched_statement": unmatched_s,
        "unmatched_entries": unmatched_e,
    }


def summary(result):
    n = 0
    t = Decimal("0.00")
    for m in result["matched"]:
        n = n + 1
        d = m["statement"]["amount"] - m["entry"]["amount"]
        if d < Decimal("0.00"):
            d = -d
        t = t + d
    return {"matched": n, "drift": t, "open": len(result["unmatched_statement"])}
