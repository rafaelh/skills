"""One handler per Stripe event type.

Called inline from the webhook request, in the order Stripe delivers.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from payments.models import Invoice, Subscription


def handle_invoice_paid(db: Session, event: dict[str, object]) -> None:
    obj = event["data"]["object"]  # type: ignore[index]
    db.add(
        Invoice(
            tenant_id=int(obj["metadata"]["tenant_id"]),
            stripe_invoice_id=obj["id"],
            amount_cents=obj["amount_paid"],
            paid_at=datetime.now(UTC),
        )
    )
    db.commit()
    _send_receipt_email(obj["customer_email"])


def handle_subscription_updated(db: Session, event: dict[str, object]) -> None:
    """Last write wins.

    There is no version or timestamp check against the event payload — we
    take whatever the event says and store it. Stripe sends these in bursts
    when a customer changes plan and seat count in the same session.
    """
    obj = event["data"]["object"]  # type: ignore[index]
    sub = db.scalar(
        select(Subscription).where(Subscription.stripe_subscription_id == obj["id"])
    )
    if sub is None:
        return
    sub.current_plan = obj["items"]["data"][0]["price"]["lookup_key"]
    sub.seat_count = obj["items"]["data"][0]["quantity"]
    sub.updated_at = datetime.now(UTC)
    db.commit()


def handle_subscription_deleted(db: Session, event: dict[str, object]) -> None:
    obj = event["data"]["object"]  # type: ignore[index]
    sub = db.scalar(
        select(Subscription).where(Subscription.stripe_subscription_id == obj["id"])
    )
    if sub is None:
        return
    sub.current_plan = "free"
    sub.updated_at = datetime.now(UTC)
    db.commit()


def _send_receipt_email(address: str) -> None:
    """Blocking call to the transactional email provider. p99 is about 4s."""
    raise NotImplementedError


HANDLERS = {
    "invoice.paid": handle_invoice_paid,
    "customer.subscription.updated": handle_subscription_updated,
    "customer.subscription.deleted": handle_subscription_deleted,
}
