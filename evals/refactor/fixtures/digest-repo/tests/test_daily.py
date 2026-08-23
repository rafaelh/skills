from __future__ import annotations

from notify.daily import SUBJECT, daily_email


def test_the_email_is_addressed_and_titled():
    mail = daily_email([{"subject": "build failed", "priority": 1, "actor": "ada"}], "ada@example")
    assert mail["to"] == "ada@example"
    assert mail["subject"] == SUBJECT
    assert "body" in mail
