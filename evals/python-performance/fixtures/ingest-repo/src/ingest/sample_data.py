"""Synthetic CRM exports and transaction rows, deterministic per seed. Used by the tests."""

from __future__ import annotations

import random

REGIONS = ("emea", "amer", "apac")
WORDS = ("north", "harbour", "vellum", "orchid", "granite", "tally", "quill", "moss")


def make_customers(n, seed=11):
    """`n` customer records. Every twentieth ref also carries a superseded duplicate."""
    rng = random.Random(seed)
    customers = []
    for i in range(n):
        ref = "C{:07d}".format(i)
        customers.append(
            {
                "ref": ref,
                "name": "{} {}  ltd".format(rng.choice(WORDS), rng.choice(WORDS)),
                "region": rng.choice(REGIONS),
            }
        )
        if i % 20 == 0:
            customers.append({"ref": ref, "name": "merged account", "region": "closed"})
    return customers


def make_rows(n, customers, seed=13):
    """`n` transaction rows drawn from the refs in `customers`."""
    rng = random.Random(seed)
    refs = [customer["ref"] for customer in customers]
    return [
        {"customer_ref": rng.choice(refs), "amount": rng.randrange(100, 90_000)} for _ in range(n)
    ]
