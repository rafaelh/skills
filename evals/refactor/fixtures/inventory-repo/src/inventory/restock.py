"""Plan restock orders from reorder points and open purchase orders."""

from __future__ import annotations

from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

MIN_ORDER = Decimal("25.00")


def _totals(rows):
    t = Decimal("0.00")
    for r in rows:
        t = t + r["cost"]
    return t


def plan(items, open_orders, budget=None):
    out = []
    spend = Decimal("0.00")
    for i in items:
        if i["on_hand"] < i["reorder_point"]:
            inbound = 0
            for o in open_orders:
                if o["sku"] == i["sku"]:
                    # Cancelled orders stay in the table for the audit trail, so the
                    # filter has to happen here rather than in the query upstream.
                    if o["status"] != "cancelled":
                        inbound = inbound + o["qty"]
            short = i["reorder_point"] - i["on_hand"] - inbound
            if short > 0:
                q = short
                if q < i["pack_size"]:
                    q = i["pack_size"]
                else:
                    r = q % i["pack_size"]
                    if r != 0:
                        q = q + (i["pack_size"] - r)
                logger.debug("rounded %s up to a whole pack", i["sku"])
                cost = q * i["unit_cost"]
                if cost < MIN_ORDER:
                    logger.info("below the minimum order value for %s", i["sku"])
                else:
                    if budget is not None:
                        if spend + cost > budget:
                            logger.info("over budget, skipping %s", i["sku"])
                            continue
                    spend = spend + cost
                    out.append({"sku": i["sku"], "qty": q, "cost": cost})
    return out


def top_up(item, target):
    q = target - item["on_hand"]
    if q <= 0:
        return 0
    # Suppliers invoice by the pack and finance rejected the March run for ordering
    # part packs, so round up even when it overshoots the target.
    if q < item["pack_size"]:
        q = item["pack_size"]
    else:
        r = q % item["pack_size"]
        if r != 0:
            q = q + (item["pack_size"] - r)
    logger.debug("rounded %s up to a whole pack", item["sku"])
    return q
