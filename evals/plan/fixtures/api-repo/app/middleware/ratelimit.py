"""The rate limiter we have today.

Fixed window, one counter per client IP, held in process memory.

Known problems, in the order they bite:
  - Process-local. We run 4 uvicorn workers across 3 tasks, so the effective
    ceiling is 12x whatever RATE_LIMIT_RPS says.
  - Keyed by IP. Customers behind one NAT share a bucket; customers on many
    egress IPs get a bucket each.
  - One global number. A free-tier script can exhaust the window that an
    enterprise customer is trying to use.
"""

import time
from collections import defaultdict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.settings import settings

_WINDOW_SECONDS = 1.0


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._counts: dict[str, int] = defaultdict(int)
        self._window_start = time.monotonic()

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        now = time.monotonic()
        if now - self._window_start > _WINDOW_SECONDS:
            self._counts.clear()
            self._window_start = now

        client = request.client.host if request.client else "unknown"
        self._counts[client] += 1
        if self._counts[client] > settings.rate_limit_rps:
            return Response(status_code=429, content="rate limit exceeded")

        return await call_next(request)
