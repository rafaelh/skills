"""Stripe SDK setup."""

import os

import stripe

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
WEBHOOK_SIGNING_SECRET = os.environ["STRIPE_WEBHOOK_SECRET"]

# Set in the Stripe dashboard, one endpoint, all event types.
CONFIGURED_ENDPOINT = "https://api.example.com/webhooks/stripe"
