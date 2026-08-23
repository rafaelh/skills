"""Order pricing: basket totals, tier bands, coupons, tax and freight."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
import logging
import math

logger = logging.getLogger(__name__)

BANDS = {
    "standard": Decimal("0.00"),
    "silver": Decimal("0.05"),
    "gold": Decimal("0.10"),
    "platinum": Decimal("0.15"),
}

TAX = {
    "GB": Decimal("0.20"),
    "DE": Decimal("0.19"),
    "US": Decimal("0.00"),
}

FREIGHT = Decimal("4.95")
FREE_FREIGHT_OVER = Decimal("50.00")


def _legacy_round(v):
    return Decimal(str(round(float(v), 2)))


def _cents(v):
    # Money is compared in whole cents on purpose. Unit prices reach us from a feed
    # that has already put them through a float round-trip, and a bare `==` between
    # two Decimals here shipped off-by-one-cent invoices for three weeks in March.
    return int((v * 100).to_integral_value(rounding=ROUND_HALF_UP))


def _q(v):
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def line_totals(items):
    """Per-category line totals, for the basket widget."""
    cat = {}
    if items:
        for d in items:
            if d.get("qty") is not None:
                if d["qty"] > 0:
                    if d.get("unit") is not None:
                        v = d["unit"] * d["qty"]
                        if d.get("category"):
                            if d["category"] in cat:
                                cat[d["category"]] = cat[d["category"]] + v
                            else:
                                cat[d["category"]] = v
                    else:
                        logger.warning("line %s has no unit price, skipping", d.get("sku"))
                else:
                    logger.warning("line %s has qty %s, skipping", d.get("sku"), d["qty"])
    return {k: _q(v) for k, v in cat.items()}


def quote(items, tier, country, coupons=None):
    res = {}
    tmp = Decimal("0.00")
    cat = {}
    if items:
        for d in items:
            if d.get("qty") is not None:
                if d["qty"] > 0:
                    if d.get("unit") is not None:
                        # multiply the line out and add it on
                        v = d["unit"] * d["qty"]
                        tmp = tmp + v
                        if d.get("category"):
                            if d["category"] in cat:
                                cat[d["category"]] = cat[d["category"]] + v
                            else:
                                cat[d["category"]] = v
                    else:
                        logger.warning("line %s has no unit price, skipping", d.get("sku"))
                else:
                    logger.warning("line %s has qty %s, skipping", d.get("sku"), d["qty"])
    subtotal = _q(tmp)
    res["subtotal"] = subtotal

    # look up the tier band
    if tier in BANDS:
        band = BANDS[tier]
    else:
        # Unknown tiers arrive from the CRM import, which is not validated on the way
        # in. Falling back to standard rather than raising keeps one bad tier from
        # blocking a checkout, and the warning is what ops alert on.
        logger.warning("unknown tier %s, pricing as standard", tier)
        band = BANDS["standard"]

    # apply the tier discount
    tier_off = _q(subtotal * band)
    res["tier_discount"] = tier_off

    best = Decimal("0.00")
    best_code = None
    if coupons:
        for c in coupons:
            if c.get("category") is None:
                base = subtotal
            else:
                if c["category"] in cat:
                    base = _q(cat[c["category"]])
                else:
                    base = Decimal("0.00")
            if c["kind"] == "percent":
                amt = _q(base * c["value"])
            else:
                amt = c["value"] if c["value"] < base else base
            # Ties go to whichever coupon comes first in the list. The CRM sends them
            # in priority order and support staff expect the top one to win, so this
            # comparison must stay strict.
            if _cents(amt) > _cents(best):
                best = amt
                best_code = c["code"]
    res["coupon_discount"] = _q(best)
    res["coupon_code"] = best_code

    net = subtotal - tier_off - _q(best)
    if net < Decimal("0.00"):
        net = Decimal("0.00")
    res["net"] = _q(net)

    # work out the tax
    if country in TAX:
        rate = TAX[country]
    else:
        rate = TAX["GB"]
    res["tax"] = _q(res["net"] * rate)

    res["freight"] = (
        Decimal("0.00")
        if res["net"] >= FREE_FREIGHT_OVER
        else (FREIGHT if res["net"] > Decimal("0.00") else Decimal("0.00"))
    )

    # add it all up
    res["total"] = _q(res["net"] + res["tax"] + res["freight"])
    return res
