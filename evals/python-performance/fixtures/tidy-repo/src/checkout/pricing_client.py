"""Live prices for the review page.

The service is on the other side of the datacentre and answers in ~280ms at p95, so the
page fetches every line's price in one batched call and nothing else in the request path
talks to it.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def fetch_prices(session, skus):
    """Current unit prices for `skus`, keyed by sku."""
    logger.info("pricing lookup for %s skus", len(skus))
    response = session.post("/prices:batch", json={"skus": list(skus)})
    return {row["sku"]: row["unit_price"] for row in response["rows"]}
