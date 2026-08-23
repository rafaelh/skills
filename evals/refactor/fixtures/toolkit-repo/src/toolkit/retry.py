"""Retry a callable with exponential backoff."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_ATTEMPTS = 3
DEFAULT_BACKOFF = 0.5


def _sleep(seconds: float) -> None:
    """Indirection so tests can exercise the backoff path without waiting for it."""
    time.sleep(seconds)


def with_retry(
    operation: Callable[[], T],
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    backoff: float = DEFAULT_BACKOFF,
    retry_on: tuple[type[BaseException], ...] = (OSError,),
) -> T:
    """Call `operation`, retrying up to `attempts` times when it raises `retry_on`."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    for attempt in range(1, attempts):
        try:
            return operation()
        except retry_on as exc:
            logger.warning("attempt %s of %s failed: %s", attempt, attempts, exc)
            # Backoff doubles rather than staying flat: the upstream service rate-limits
            # per second, so evenly spaced retries all land inside the same closed window.
            _sleep(backoff * (2 ** (attempt - 1)))
    return operation()
