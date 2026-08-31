"""Synthetic events, deterministic per seed. Used by the tests."""

from __future__ import annotations

import random

SERVICES = ("checkout", "billing", "search", "auth", "media", "notify", "ledger")
KINDS = ("deploy", "rollback", "incident", "page", "heartbeat")
TEAMS = {
    "checkout": "payments",
    "billing": "payments",
    "search": "discovery",
    "auth": "platform",
    "media": "discovery",
    "notify": "platform",
}


def make_events(n, seed=7):
    rng = random.Random(seed)
    events = []
    for i in range(n):
        events.append(
            {
                "at": "{:02d}:{:02d}:{:02d}".format(i // 3600 % 24, i // 60 % 60, i % 60),
                "service": rng.choice(SERVICES),
                "kind": rng.choice(KINDS),
            }
        )
    return events
