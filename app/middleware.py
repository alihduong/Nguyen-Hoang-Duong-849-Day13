from __future__ import annotations

import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from structlog.contextvars import bind_contextvars, clear_contextvars


class CorrelationIdMiddleware(BaseHTTPMiddleware):
   async def dispatch(self, request: Request, call_next):
        clear_contextvars()

        # FIX: use x-correlation-id
        correlation_id = request.headers.get("x-correlation-id")

        if not correlation_id:
            correlation_id = f"req-{uuid.uuid4().hex[:8]}"

        bind_contextvars(correlation_id=correlation_id)

        request.state.correlation_id = correlation_id

        start = time.perf_counter()

        response = await call_next(request)

        process_time_ms = round((time.perf_counter() - start) * 1000, 2)

        # FIX: return same header name
        response.headers["x-correlation-id"] = correlation_id
        response.headers["x-response-time-ms"] = str(process_time_ms)

        return response
