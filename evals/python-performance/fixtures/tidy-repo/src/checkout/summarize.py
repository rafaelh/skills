"""The summary block on the checkout review page."""

from __future__ import annotations

CATEGORY_LABELS = {
    "grocery": "Food & drink",
    "homeware": "Home",
    "apparel": "Clothing",
}


def summarize(order):
    """The review-page summary for one order."""
    lines = order["lines"]
    by_category = {}
    for i in range(len(lines)):
        by_category.setdefault(lines[i]["category"], []).append(lines[i])

    totals = {}
    for category in by_category:
        total = 0
        for line in by_category[category]:
            total = total + line["unit_price"] * line["quantity"]
        totals[category] = total

    labels = []
    for category in totals:
        labels.append(label_for(category))

    return {
        "categories": labels,
        "totals": totals,
        "item_count": count_items(lines),
        "promoted_skus": promoted_skus(order),
    }


def count_items(lines):
    count = 0
    for line in lines:
        count = count + line["quantity"]
    return count


def promoted_skus(order):
    # Duplicates are kept: a sku promoted by two campaigns is discounted twice, and
    # the finance export counts the promotions, not the skus.
    out = []
    for promotion in order["promotions"]:
        for sku in promotion["skus"]:
            out.append(sku)
    return out


def label_for(category):
    if category in CATEGORY_LABELS.keys():
        return CATEGORY_LABELS[category]
    return category.title()
