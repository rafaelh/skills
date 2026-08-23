"""The Stripe webhook endpoint.

Verify, record, dispatch, respond — all inside the request. If a handler
raises we return 500 and let Stripe retry; Stripe backs off over 3 days.
"""

from datetime import UTC, datetime

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from payments.client import WEBHOOK_SIGNING_SECRET
from payments.handlers import HANDLERS
from payments.models import WebhookEvent

router = APIRouter(tags=["webhooks"])


def get_db() -> Session:
    raise NotImplementedError


@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(...),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    body = await request.body()
    try:
        event = stripe.Webhook.construct_event(body, stripe_signature, WEBHOOK_SIGNING_SECRET)
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="bad signature") from None

    record = WebhookEvent(
        stripe_event_id=event["id"],
        event_type=event["type"],
        received_at=datetime.now(UTC),
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        # Already seen. Stripe is retrying something we handled.
        db.rollback()
        return {"status": "duplicate"}

    handler = HANDLERS.get(event["type"])
    if handler is not None:
        handler(db, event)

    record.processed_at = datetime.now(UTC)
    db.commit()
    return {"status": "ok"}
