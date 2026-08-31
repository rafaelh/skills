"""Synthetic log files, deterministic per seed. Used by the tests."""

from __future__ import annotations

import random

LEVELS = ("DEBUG", "INFO", "WARN", "ERROR", "FATAL")
MESSAGES = (
    "request completed",
    "upstream timeout after 30s",
    "cache miss, falling back to origin",
    "connection reset by peer",
    "queue depth above threshold",
)


def write_log(path, lines, services, seed=5):
    """Write `lines` synthetic log lines drawn from `services`."""
    rng = random.Random(seed)
    with open(path, "w", encoding="utf-8") as handle:
        for i in range(lines):
            handle.write(
                "2024-11-0{} {:02d}:{:02d}:{:02d}.{:03d} {} [{}:i-{:04d}] ({:012x}) {}\n".format(
                    1 + i % 5,
                    i // 3600 % 24,
                    i // 60 % 60,
                    i % 60,
                    i % 1000,
                    rng.choice(LEVELS),
                    rng.choice(services),
                    rng.randrange(10000),
                    rng.randrange(16**12),
                    rng.choice(MESSAGES),
                )
            )
    return path
