"""Assemble the daily digest email."""

from __future__ import annotations

from notify.digest import format_digest

SUBJECT = "Your daily digest"


def daily_email(events, recipient):
    # The daily mail is the whole day's activity — the five-line cap belongs to the
    # in-app digest, and 0 turns it off.
    body = format_digest(events, limit=0)
    return {"to": recipient, "subject": SUBJECT, "body": body}
