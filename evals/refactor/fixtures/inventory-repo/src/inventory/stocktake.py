"""Compare counted stock against the book position."""

from __future__ import annotations

from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


def variance_report(counts, book, thresholds=None, value_map=None):
    out = []
    for loc in sorted(counts):
        for sku in sorted(counts[loc]):
            c = counts[loc][sku]
            b = 0
            if loc in book:
                if sku in book[loc]:
                    b = book[loc][sku]
            d = c - b
            if d != 0:
                skip = False
                if thresholds is not None:
                    if sku in thresholds:
                        t = thresholds[sku]
                        if d < 0:
                            if -d < t:
                                skip = True
                        else:
                            if d < t:
                                skip = True
                if not skip:
                    v = Decimal("0.00")
                    if value_map is not None:
                        if sku in value_map:
                            if d < 0:
                                v = -d * value_map[sku]
                                v = -v
                            else:
                                v = d * value_map[sku]
                    kind = "short"
                    if d > 0:
                        kind = "over"
                        if value_map is not None:
                            if sku in value_map:
                                if v > Decimal("100.00"):
                                    kind = "over-major"
                    else:
                        if v < Decimal("-100.00"):
                            kind = "short-major"
                    logger.info("variance at %s for %s", loc, sku)
                    out.append(
                        {"location": loc, "sku": sku, "delta": d, "value": v, "kind": kind}
                    )
    return out


def shrinkage(report):
    t = Decimal("0.00")
    for row in report:
        if row["delta"] < 0:
            t = t + row["value"]
    return t
