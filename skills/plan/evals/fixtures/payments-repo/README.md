# Ledger

Billing service. Owns Stripe integration and the subscription state our app reads.

- Python 3.12, FastAPI, Postgres 15 (SQLAlchemy 2.x)
- Deployed on ECS alongside the main API, 2 tasks
- No queue infrastructure today. No Celery, no SQS, no Redis.

Stripe webhooks are verified and processed inline, in the request. Stripe
gives us 20 seconds before it treats the delivery as failed and retries.

| Path | What |
|---|---|
| `payments/webhooks.py` | the Stripe webhook endpoint |
| `payments/handlers.py` | one function per event type |
| `payments/models.py` | webhook + subscription tables |
| `payments/client.py` | Stripe SDK setup |
